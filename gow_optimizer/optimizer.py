"""Ottimizzatore build: inventario, upgrade chain, Pareto, solver e report."""

import logging
from collections import Counter

import pandas as pd

from gow_optimizer.scraper import STAT_COLS

logger = logging.getLogger(__name__)

ARMOR_SLOTS = {
    "Chest": "Armatura — Chest",
    "Wrist": "Armatura — Wrist",
    "Waist": "Armatura — Waist",
}
WEAPON_SLOTS = {
    "Leviathan Axe": "Arma — Leviathan Axe",
    "Blades of Chaos": "Arma — Blades of Chaos",
    "Draupnir Spear": "Arma — Draupnir Spear",
    "Shield": "Arma — Shield",
}


# ─── Normalizzazione materiali ──────────────────────────────


def normalize_mat(name, mat_aliases):
    return mat_aliases.get(name, name)


def get_available(mat_name, resource_budget, mat_aliases):
    return resource_budget.get(normalize_mat(mat_name, mat_aliases), 0)


# ─── Costruzione inventario ────────────────────────────────


def parse_inventory_from_config(cfg):
    """Converte le liste YAML in tuple (name, level, slot_type, needs_craft)."""

    def _parse(pieces, slot_type):
        return [
            (p["name"], p["level"], slot_type, p.get("craft", False)) for p in pieces
        ]

    inventory = (
        _parse(cfg.get("chest_pieces", []), "Chest")
        + _parse(cfg.get("wrist_pieces", []), "Wrist")
        + _parse(cfg.get("waist_pieces", []), "Waist")
    )
    w_inventory = (
        _parse(cfg.get("axe_attachments", []), "Leviathan Axe")
        + _parse(cfg.get("blades_attachments", []), "Blades of Chaos")
        + _parse(cfg.get("spear_attachments", []), "Draupnir Spear")
        + _parse(cfg.get("shield_attachments", []), "Shield")
    )
    return inventory, w_inventory


def build_available_df(all_pieces_df, inventory):
    """Filtra il DF armature ai soli pezzi in inventario (fino al livello posseduto)."""
    filters = []
    for piece_name, max_lvl, piece_type, _ in inventory:
        mask = (
            (all_pieces_df["Piece Name"] == piece_name)
            & (all_pieces_df["Piece Type"] == piece_type)
            & (all_pieces_df["Level"] <= max_lvl)
        )
        filters.append(mask)
    return all_pieces_df[pd.concat(filters, axis=1).any(axis=1)].copy()


def build_weapon_available_df(all_weapons_df, w_inventory):
    """Filtra il DF armi ai soli attachment in inventario."""
    if not w_inventory:
        return pd.DataFrame()
    w_filters = []
    for wname, max_lvl, cat, _ in w_inventory:
        mask = (
            (all_weapons_df["Weapon Name"] == wname)
            & (all_weapons_df["Category"] == cat)
            & (all_weapons_df["Level"] <= max_lvl)
        )
        w_filters.append(mask)
    return all_weapons_df[pd.concat(w_filters, axis=1).any(axis=1)].copy()


# ─── Build attuale ──────────────────────────────────────────


def collect_current_build(inventory, available_df, w_inventory, w_available_df):
    """Restituisce (armor_current, weapon_current) — liste di Series pandas."""
    inv_lookup = {(name, pt): (lvl, craft) for name, lvl, pt, craft in inventory}
    armor_current = []
    for (piece_name, piece_type), (max_lvl, needs_craft) in inv_lookup.items():
        if needs_craft:
            continue
        row = available_df[
            (available_df["Piece Name"] == piece_name)
            & (available_df["Piece Type"] == piece_type)
            & (available_df["Level"] == max_lvl)
        ]
        if not row.empty:
            r = row.iloc[0].copy()
            r["Slot"] = f"Armatura — {piece_type}"
            r["Item Name"] = piece_name
            r["Item Level"] = max_lvl
            armor_current.append(r)

    w_inv_lookup = {(name, cat): (lvl, craft) for name, lvl, cat, craft in w_inventory}
    weapon_current = []
    for (wname, cat), (max_lvl, needs_craft) in w_inv_lookup.items():
        if needs_craft:
            continue
        row = w_available_df[
            (w_available_df["Weapon Name"] == wname)
            & (w_available_df["Category"] == cat)
            & (w_available_df["Level"] == max_lvl)
        ]
        if not row.empty:
            r = row.iloc[0].copy()
            r["Slot"] = f"Arma — {cat}"
            r["Item Name"] = wname
            r["Item Level"] = max_lvl
            weapon_current.append(r)

    return armor_current, weapon_current


# ─── Upgrade chain / Pareto / Solver ────────────────────────


def get_upgrade_chain_with_mats(
    df, name_col, name, cat_col, cat, current_lvl, resource_budget, mat_aliases
):
    upg_cols = [
        c for c in df.columns if c.startswith("Upgrade_") and c != "Upgrade_Hacksilver"
    ]
    item_df = df[(df[name_col] == name) & (df[cat_col] == cat)].sort_values("Level")
    chain = []
    cum_hack = 0
    cum_mats = Counter()

    for _, r in item_df.iterrows():
        if r["Level"] <= current_lvl:
            continue
        hack = (
            int(r.get("Upgrade_Hacksilver", 0))
            if pd.notna(r.get("Upgrade_Hacksilver", 0))
            else 0
        )
        level_mats = {}
        for c in upg_cols:
            v = r.get(c, 0)
            if pd.notna(v) and v > 0:
                mat_name = normalize_mat(c.replace("Upgrade_", ""), mat_aliases)
                level_mats[mat_name] = level_mats.get(mat_name, 0) + int(v)

        test_mats = Counter(cum_mats)
        test_mats.update(level_mats)
        feasible = all(
            test_mats[m] <= get_available(m, resource_budget, mat_aliases)
            for m in test_mats
        )
        if not feasible:
            break

        cum_hack += hack
        cum_mats = test_mats
        chain.append((r["Level"], r["Total Stats"], cum_hack, dict(cum_mats)))

    return chain


def build_slot_options_with_mats(items_with_chains):
    current_best = max((s for _, _, s, _, _ in items_with_chains), default=0)
    options = [(0, current_best, "— nessuna azione —", {})]

    for item_name, item_lvl, item_stats, chain, needs_craft in items_with_chains:
        other_best = max(
            (s for n, _, s, _, _ in items_with_chains if n != item_name), default=0
        )
        for target_lvl, target_stats, hack, mats in chain:
            lvl_label = int(target_lvl) if target_lvl == int(target_lvl) else target_lvl
            resulting_stats = max(target_stats, other_best)
            craft_tag = "★craft+" if needs_craft else ""
            options.append(
                (
                    hack,
                    resulting_stats,
                    f"{craft_tag}{item_name} {int(item_lvl)}→{lvl_label}",
                    mats,
                )
            )
    return options


def pareto_frontier_with_mats(options):
    frontier, best_stats = [], -1
    for opt in sorted(options, key=lambda x: (x[0], -x[1])):
        if opt[1] > best_stats:
            frontier.append(opt)
            best_stats = opt[1]
    return frontier


def solve_with_resources(slot_pareto_dict, budget_hack, resource_budget, mat_aliases):
    slots = list(slot_pareto_dict.keys())
    best_total, best_choices = -1, {}

    slot_opts = []
    for slot in slots:
        feasible = [
            (h, s, l, m) for h, s, l, m in slot_pareto_dict[slot] if h <= budget_hack
        ]
        slot_opts.append(feasible)

    order = sorted(range(len(slots)), key=lambda i: len(slot_opts[i]))

    def search(idx, used_hack, used_mats, acc_stats, acc_choices):
        nonlocal best_total, best_choices
        if idx == len(slots):
            if acc_stats > best_total:
                best_total = acc_stats
                best_choices = dict(acc_choices)
            return

        si = order[idx]
        slot = slots[si]
        for hack, stats, label, mats in slot_opts[si]:
            new_hack = used_hack + hack
            if new_hack > budget_hack:
                continue
            new_mats = Counter(used_mats)
            new_mats.update(mats)
            if all(
                new_mats[m] <= get_available(m, resource_budget, mat_aliases)
                for m in new_mats
            ):
                acc_choices[slot] = (hack, stats, label, mats)
                search(idx + 1, new_hack, new_mats, acc_stats + stats, acc_choices)
                del acc_choices[slot]

    search(0, 0, Counter(), 0, {})
    return best_total, best_choices


# ─── Costruzione Pareto per tutti gli slot ──────────────────


def build_all_pareto(
    inventory, w_inventory, all_pieces_df, all_weapons_df, resource_budget, mat_aliases
):
    slot_pareto = {}

    for pt in ["Chest", "Wrist", "Waist"]:
        items = []
        for name, lvl, t, needs_craft in inventory:
            if t != pt:
                continue
            if needs_craft:
                effective_lvl = lvl - 1
                stats = 0
            else:
                effective_lvl = lvl
                row = all_pieces_df[
                    (all_pieces_df["Piece Name"] == name)
                    & (all_pieces_df["Piece Type"] == pt)
                    & (all_pieces_df["Level"] == lvl)
                ]
                stats = row.iloc[0]["Total Stats"] if not row.empty else 0
            chain = get_upgrade_chain_with_mats(
                all_pieces_df,
                "Piece Name",
                name,
                "Piece Type",
                pt,
                effective_lvl,
                resource_budget,
                mat_aliases,
            )
            items.append((name, lvl, stats, chain, needs_craft))
        slot_pareto[f"Armatura — {pt}"] = pareto_frontier_with_mats(
            build_slot_options_with_mats(items)
        )

    for cat in ["Leviathan Axe", "Blades of Chaos", "Shield"]:
        items = []
        for name, lvl, c, needs_craft in w_inventory:
            if c != cat:
                continue
            if needs_craft:
                effective_lvl = lvl - 1
                stats = 0
            else:
                effective_lvl = lvl
                row = all_weapons_df[
                    (all_weapons_df["Weapon Name"] == name)
                    & (all_weapons_df["Category"] == cat)
                    & (all_weapons_df["Level"] == lvl)
                ]
                stats = row.iloc[0]["Total Stats"] if not row.empty else 0
            chain = get_upgrade_chain_with_mats(
                all_weapons_df,
                "Weapon Name",
                name,
                "Category",
                cat,
                effective_lvl,
                resource_budget,
                mat_aliases,
            )
            items.append((name, lvl, stats, chain, needs_craft))
        if items:
            slot_pareto[f"Arma — {cat}"] = pareto_frontier_with_mats(
                build_slot_options_with_mats(items)
            )

    return slot_pareto


# ─── Report ─────────────────────────────────────────────────


def print_current_build(armor_current, weapon_current):
    logger.info("=" * 85)
    logger.info("  BUILD OTTIMALE COMPLETA (Armatura + Armi)")
    logger.info("=" * 85)

    build_items = []

    logger.info("\n  %s", "─" * 40)
    logger.info("  ARMATURA")
    logger.info("  %s", "─" * 40)
    armor_total = 0
    for pt in ["Chest", "Wrist", "Waist"]:
        candidates = [r for r in armor_current if r["Piece Type"] == pt]
        if candidates:
            best = max(candidates, key=lambda x: x["Total Stats"])
            stats_detail = ", ".join(
                f"{s[:3].upper()}:{best.get(s, 0):.0f}"
                for s in STAT_COLS
                if best.get(s, 0) > 0
            )
            logger.info(
                "    %6s: %s (LVL %d) — Total: %.0f  [%s]",
                pt,
                best["Item Name"],
                best["Item Level"],
                best["Total Stats"],
                stats_detail,
            )
            armor_total += best["Total Stats"]
            build_items.append(
                {
                    "Slot": ARMOR_SLOTS[pt],
                    "Item": best["Item Name"],
                    "Level": best["Item Level"],
                    "Total Stats": best["Total Stats"],
                }
            )

    logger.info("\n  %s", "─" * 40)
    logger.info("  ARMI")
    logger.info("  %s", "─" * 40)
    weapon_total = 0
    for cat in ["Leviathan Axe", "Blades of Chaos", "Draupnir Spear", "Shield"]:
        candidates = [r for r in weapon_current if r["Category"] == cat]
        if candidates:
            best = max(candidates, key=lambda x: x["Total Stats"])
            stats_detail = ", ".join(
                f"{s[:3].upper()}:{best.get(s, 0):.0f}"
                for s in STAT_COLS
                if best.get(s, 0) > 0
            )
            logger.info(
                "    %18s: %s (LVL %d) — Total: %.0f  [%s]",
                cat,
                best["Item Name"],
                best["Item Level"],
                best["Total Stats"],
                stats_detail,
            )
            weapon_total += best["Total Stats"]
            build_items.append(
                {
                    "Slot": WEAPON_SLOTS[cat],
                    "Item": best["Item Name"],
                    "Level": best["Item Level"],
                    "Total Stats": best["Total Stats"],
                }
            )
        else:
            logger.info("    %18s: — non sbloccata —", cat)

    grand_total = armor_total + weapon_total

    logger.info("\n  %s", "═" * 40)
    logger.info("  TOTALE ARMATURA:  %.0f", armor_total)
    logger.info("  TOTALE ARMI:      %.0f", weapon_total)
    logger.info("  %s", "─" * 40)
    logger.info("  GRAND TOTAL:      %.0f", grand_total)
    logger.info("  %s", "═" * 40)

    return grand_total, build_items


def print_craft_warnings(inventory, w_inventory):
    craft_a = [(n, l, pt) for n, l, pt, c in inventory if c]
    craft_w = [(n, l, cat) for n, l, cat, c in w_inventory if c]
    if craft_a or craft_w:
        logger.warning("\n  ⚠ Pezzi da craftare (non inclusi nel build attuale):")
        for n, l, pt in craft_a:
            logger.warning("    %s (%s) — LVL %d", n, pt, l)
        for n, l, cat in craft_w:
            logger.warning("    %s (%s) — LVL %d", n, cat, l)


def print_slot_rankings(armor_current, weapon_current):
    logger.info("\n\n%s", "=" * 85)
    logger.info("  CLASSIFICA COMPLETA PER SLOT")
    logger.info("%s", "=" * 85)

    for pt in ["Chest", "Wrist", "Waist"]:
        candidates = sorted(
            [r for r in armor_current if r["Piece Type"] == pt],
            key=lambda x: x["Total Stats"],
            reverse=True,
        )
        if candidates:
            logger.info("\n  ARMATURA — %s:", pt.upper())
            for i, r in enumerate(candidates):
                stats_detail = ", ".join(
                    f"{s[:3].upper()}:{r.get(s, 0):.0f}"
                    for s in STAT_COLS
                    if r.get(s, 0) > 0
                )
                marker = "→" if i == 0 else " "
                star = "  ★" if i == 0 else ""
                logger.info(
                    "    %s %s (LVL %.0f) — Total: %.0f  [%s]%s",
                    marker,
                    r["Item Name"],
                    r["Item Level"],
                    r["Total Stats"],
                    stats_detail,
                    star,
                )

    for cat in ["Leviathan Axe", "Blades of Chaos", "Draupnir Spear", "Shield"]:
        candidates = sorted(
            [r for r in weapon_current if r["Category"] == cat],
            key=lambda x: x["Total Stats"],
            reverse=True,
        )
        if candidates:
            logger.info("\n  ARMA — %s:", cat.upper())
            for i, r in enumerate(candidates):
                stats_detail = ", ".join(
                    f"{s[:3].upper()}:{r.get(s, 0):.0f}"
                    for s in STAT_COLS
                    if r.get(s, 0) > 0
                )
                marker = "→" if i == 0 else " "
                star = "  ★" if i == 0 else ""
                logger.info(
                    "    %s %s (LVL %.0f) — Total: %.0f  [%s]%s",
                    marker,
                    r["Item Name"],
                    r["Item Level"],
                    r["Total Stats"],
                    stats_detail,
                    star,
                )


def print_optimizer_report(slot_pareto, grand_total, resource_budget, mat_aliases):
    logger.info("=" * 85)
    logger.info("  OTTIMIZZATORE DI BUILD (con vincoli materiali)")
    logger.info("=" * 85)
    logger.info("  Grand Total attuale: %.0f", grand_total)
    logger.info("  Hacksilver disponibili: %s\n", f"{resource_budget['Hacksilver']:,}")

    logger.info("  RISORSE DISPONIBILI:")
    for mat, qty in sorted(resource_budget.items()):
        if mat != "Hacksilver":
            logger.info("    %s: %s", mat, qty)
    logger.info("")

    logger.info("  FRONTIERE DI PARETO PER SLOT:\n")
    for slot, frontier in slot_pareto.items():
        real_options = [f for f in frontier if "nessuna" not in f[2]]
        logger.info("  %s: %d upgrade possibili", slot, len(real_options))
        for hack, stats, label, mats in frontier:
            if "nessuna" in label:
                continue
            mat_str = (
                ", ".join(f"{m}:{v}" for m, v in sorted(mats.items())) if mats else "—"
            )
            logger.info(
                "    Hack %8s → Stats %6.0f  [%s]  Mat: %s",
                f"{hack:,}",
                stats,
                label,
                mat_str,
            )
        if not real_options:
            logger.info("    (nessun upgrade fattibile con i materiali attuali)")
        logger.info("")


def print_optimal_plan(slot_pareto, grand_total, resource_budget, mat_aliases):
    logger.info("\n%s", "=" * 85)
    logger.info("  PIANO OTTIMO (Hacksilver + Materiali)")
    logger.info("%s\n", "=" * 85)

    total_stats, choices = solve_with_resources(
        slot_pareto,
        resource_budget["Hacksilver"],
        resource_budget,
        mat_aliases,
    )
    total_hack = sum(h for h, _, _, _ in choices.values())
    total_mats = Counter()
    for h, s, l, m in choices.values():
        total_mats.update(m)

    gain = total_stats - grand_total
    actions = [
        (sl, h, s, l, m)
        for sl, (h, s, l, m) in sorted(choices.items())
        if "nessuna" not in l
    ]

    if gain > 0:
        logger.info("  Grand Total: %.0f (+%.0f)", total_stats, gain)
        logger.info(
            "  Hacksilver spesi: %s / %s (restano %s)",
            f"{total_hack:,}",
            f"{resource_budget['Hacksilver']:,}",
            f"{resource_budget['Hacksilver'] - total_hack:,}",
        )
        if total_mats:
            logger.info("  Materiali usati:")
            for m, v in sorted(total_mats.items()):
                avail = get_available(m, resource_budget, mat_aliases)
                logger.info("    %s: %d/%d", m, v, avail)
        logger.info("")
        for sl, h, s, l, m in actions:
            mat_str = (
                ", ".join(f"{k}:{v}" for k, v in sorted(m.items()))
                if m
                else "solo Hacksilver"
            )
            logger.info(
                "  ► %-40s  Hack: %8s  → Slot: %.0f  [%s]", l, f"{h:,}", s, mat_str
            )
    else:
        logger.info("  Nessun upgrade possibile con le risorse attuali.")


def print_blocked_slots(
    inventory, w_inventory, all_pieces_df, all_weapons_df, resource_budget, mat_aliases
):
    logger.info("\n\n%s", "=" * 85)
    logger.info("  SLOT BLOCCATI — materiali mancanti")
    logger.info("%s\n", "=" * 85)

    for pt in ["Chest", "Wrist", "Waist"]:
        for name, lvl, t, needs_craft in inventory:
            if t != pt:
                continue
            next_lvl = lvl if needs_craft else lvl + 1
            row = all_pieces_df[
                (all_pieces_df["Piece Name"] == name)
                & (all_pieces_df["Piece Type"] == pt)
                & (all_pieces_df["Level"] == next_lvl)
            ]
            if not row.empty:
                upg_cols = [
                    c
                    for c in all_pieces_df.columns
                    if c.startswith("Upgrade_") and c != "Upgrade_Hacksilver"
                ]
                blocking = []
                for c in upg_cols:
                    v = row.iloc[0].get(c, 0)
                    if pd.notna(v) and v > 0:
                        mn = normalize_mat(c.replace("Upgrade_", ""), mat_aliases)
                        avail = get_available(mn, resource_budget, mat_aliases)
                        if avail < v:
                            blocking.append(
                                f"{mn} ({int(v)} richiesti, {avail} disponibili)"
                            )
                if blocking:
                    action = f"craft LVL {lvl}" if needs_craft else f"{lvl}→{next_lvl}"
                    logger.warning(
                        "  %s %s: manca %s", name, action, ", ".join(blocking)
                    )

    for cat_w in ["Leviathan Axe", "Blades of Chaos", "Shield"]:
        for name, lvl, c, needs_craft in w_inventory:
            if c != cat_w:
                continue
            next_lvl = lvl if needs_craft else lvl + 1
            row = all_weapons_df[
                (all_weapons_df["Weapon Name"] == name)
                & (all_weapons_df["Category"] == cat_w)
                & (all_weapons_df["Level"] == next_lvl)
            ]
            if not row.empty:
                upg_cols = [
                    c2
                    for c2 in all_weapons_df.columns
                    if c2.startswith("Upgrade_") and c2 != "Upgrade_Hacksilver"
                ]
                blocking = []
                for c2 in upg_cols:
                    v = row.iloc[0].get(c2, 0)
                    if pd.notna(v) and v > 0:
                        mn = normalize_mat(c2.replace("Upgrade_", ""), mat_aliases)
                        avail = get_available(mn, resource_budget, mat_aliases)
                        if avail < v:
                            blocking.append(
                                f"{mn} ({int(v)} richiesti, {avail} disponibili)"
                            )
                if blocking:
                    action = f"craft LVL {lvl}" if needs_craft else f"{lvl}→{next_lvl}"
                    logger.warning(
                        "  %s %s: manca %s", name, action, ", ".join(blocking)
                    )


def print_step_by_step(slot_pareto, grand_total, resource_budget, mat_aliases):
    logger.info("\n\n%s", "=" * 85)
    logger.info(
        "  SEQUENZA STEP-BY-STEP (ordine per efficienza, con vincoli materiali)"
    )
    logger.info("%s\n", "=" * 85)

    remaining_slots = {slot: list(opts) for slot, opts in slot_pareto.items()}
    cur_stats = {slot: opts[0][1] for slot, opts in slot_pareto.items()}
    running_total = grand_total
    used_budget = 0
    used_mats_total = Counter()

    for step_i in range(1, 50):
        best_action = None
        best_efficiency = -1
        for slot, opts in remaining_slots.items():
            cs = cur_stats[slot]
            for hack, stats, label, mats in opts:
                if hack == 0 or stats <= cs:
                    continue
                test = Counter(used_mats_total)
                test.update(mats)
                if not all(
                    test[m] <= get_available(m, resource_budget, mat_aliases)
                    for m in test
                ):
                    continue
                if used_budget + hack > resource_budget["Hacksilver"]:
                    continue
                g = stats - cs
                eff = g / hack * 1000
                if eff > best_efficiency:
                    best_efficiency = eff
                    best_action = (slot, hack, stats, label, g, eff, mats)

        if best_action is None:
            break

        slot, hack, stats, label, gain, eff, mats = best_action
        used_budget += hack
        running_total += gain
        cur_stats[slot] = stats
        used_mats_total.update(mats)
        remaining_slots[slot] = [
            (h, s, l, m) for h, s, l, m in remaining_slots[slot] if s > stats
        ]

        mat_str = (
            ", ".join(f"{k}:{v}" for k, v in sorted(mats.items())) if mats else "—"
        )
        logger.info("  %2d. %s", step_i, label)
        logger.info(
            "      [%s]  +%.0f stats  │  Hack: %8s  │  "
            "Eff: %.2f/1k  │  GT: %.0f  │  Cum: %s",
            slot,
            gain,
            f"{hack:,}",
            eff,
            running_total,
            f"{used_budget:,}",
        )
        logger.info("      Materiali: %s", mat_str)
        logger.info("")

    logger.info("  %s", "═" * 70)
    logger.info(
        "  Grand Total finale: %.0f  (+%.0f)",
        running_total,
        running_total - grand_total,
    )
    logger.info(
        "  Hacksilver spesi:   %s / %s",
        f"{used_budget:,}",
        f"{resource_budget['Hacksilver']:,}",
    )
    logger.info(
        "  Hacksilver restanti: %s", f"{resource_budget['Hacksilver'] - used_budget:,}"
    )
    if used_mats_total:
        logger.info("  Materiali consumati:")
        for m, v in sorted(used_mats_total.items()):
            avail = get_available(m, resource_budget, mat_aliases)
            logger.info("    %s: %d/%d (restano %d)", m, v, avail, avail - v)
    logger.info("  %s", "═" * 70)
