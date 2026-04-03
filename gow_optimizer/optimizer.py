"""Ottimizzatore build: inventario, upgrade chain, Pareto, solver."""

import math
from collections import Counter

import pandas as pd

from gow_optimizer.scraper import STAT_COLS


# ─── Multi-objective scoring ────────────────────────────────


def make_score_fn(target_stats, baseline_per_slot):
    """
    Returns a scoring function for multi-objective optimization.

    Args:
        target_stats: List of stat names to optimize (subset of STAT_COLS).
        baseline_per_slot: Dict mapping stat name -> current best value in this slot.

    Returns:
        A function that takes a per_stat_dict and returns geometric mean of gains.
        Formula: ∏(1 + max(per_stat[s] - baseline[s], 0))^(1/n) for s in target_stats.

    If target_stats is empty, falls back to summing all stats (original behavior).
    """

    def score_fn(per_stat_dict):
        if not target_stats:
            # Fallback: sum all stats (original behavior)
            return sum(per_stat_dict.values())

        gains = [
            max(per_stat_dict.get(s, 0) - baseline_per_slot.get(s, 0), 0)
            for s in target_stats
        ]
        product = math.prod(1 + g for g in gains)
        return product ** (1 / len(target_stats))

    return score_fn


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

        # Extract per-stat dict for this item at this level
        per_stat = {col: r.get(col, 0) for col in STAT_COLS}

        chain.append((r["Level"], r["Total Stats"], cum_hack, dict(cum_mats), per_stat))

    return chain


def build_slot_options_with_mats(items_with_chains, score_fn=None):
    """Build upgrade options for a slot, optionally using a multi-objective score function.

    Args:
        items_with_chains: List of (name, lvl, stats, chain, needs_craft) tuples.
        score_fn: Optional function that takes per_stat dict and returns a score.
                 If None, uses Total Stats (original behavior).

    Returns:
        List of (hack, score, label, mats) tuples representing upgrade options.
    """
    current_best = max((s for _, _, s, _, _ in items_with_chains), default=0)
    options = [(0, current_best, "— nessuna azione —", {})]

    for item_name, item_lvl, item_stats, chain, needs_craft in items_with_chains:
        other_best = max(
            (s for n, _, s, _, _ in items_with_chains if n != item_name), default=0
        )
        for target_lvl, target_stats, hack, mats, per_stat in chain:
            lvl_label = int(target_lvl) if target_lvl == int(target_lvl) else target_lvl

            # Compute the resulting score
            if score_fn is not None:
                # Multi-objective: use geometric mean score of selected stat gains
                resulting_score = score_fn(per_stat)
            else:
                # Original behavior: use Total Stats, comparing against other items in same slot
                resulting_score = target_stats

            craft_tag = "★craft+" if needs_craft else ""
            options.append(
                (
                    hack,
                    resulting_score,
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
    inventory, w_inventory, all_pieces_df, all_weapons_df, resource_budget, mat_aliases, score_fns=None
):
    """Build Pareto frontier for all slots.

    Args:
        score_fns: Optional dict mapping slot_label -> score_fn for multi-objective optimization.
                  If None, uses original Total Stats-based scoring.
    """
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
        slot_label = f"Armatura — {pt}"
        score_fn = (score_fns or {}).get(slot_label)
        slot_pareto[slot_label] = pareto_frontier_with_mats(
            build_slot_options_with_mats(items, score_fn=score_fn)
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
            slot_label = f"Arma — {cat}"
            score_fn = (score_fns or {}).get(slot_label)
            slot_pareto[slot_label] = pareto_frontier_with_mats(
                build_slot_options_with_mats(items, score_fn=score_fn)
            )

    return slot_pareto
