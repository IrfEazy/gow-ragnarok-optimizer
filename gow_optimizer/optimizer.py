"""Ottimizzatore build: inventario, upgrade chain, Pareto, solver."""

import math
import re
from collections import Counter

import pandas as pd

from gow_optimizer.scraper import STAT_COLS

# ─── Column name constants ──────────────────────────────────

PIECE_NAME_COL = "Piece Name"
PIECE_TYPE_COL = "Piece Type"
WEAPON_NAME_COL = "Weapon Name"
CATEGORY_COL = "Category"
TOTAL_STATS_COL = "Total Stats"
LEVEL_COL = "Level"
UPGRADE_HACK_COL = "Upgrade_Hacksilver"

# Weapon category constants
LEVIATHAN_AXE = "Leviathan Axe"
BLADES_OF_CHAOS = "Blades of Chaos"
DRAUPNIR_SPEAR = "Draupnir Spear"
SHIELD = "Shield"

ARMOR_TYPES = ["Chest", "Wrist", "Waist"]
WEAPON_CATEGORIES = [LEVIATHAN_AXE, BLADES_OF_CHAOS, DRAUPNIR_SPEAR, SHIELD]

# ─── Multi-objective scoring ────────────────────────────────


def make_score_fn(target_stats, baseline_per_slot, weights=None):
    """
    Returns a scoring function for multi-objective optimization.

    Args:
        target_stats: List of stat names to optimize (subset of STAT_COLS).
        baseline_per_slot: Dict mapping stat name -> current best value in this slot.
        weights: Optional dict mapping stat name -> weight (1-5). Defaults to 1 for all.

    Returns:
        A function that takes a per_stat_dict and returns weighted geometric mean of gains.
        Formula: ∏(1 + gain_s)^(w_s / sum_w) for s in target_stats.

    If target_stats is empty, falls back to summing all stats (original behavior).
    """
    w = weights or {}

    def score_fn(per_stat_dict):
        if not target_stats:
            return sum(per_stat_dict.values())

        stat_weights = [w.get(s, 1) for s in target_stats]
        total_w = sum(stat_weights)
        if total_w == 0:
            total_w = len(target_stats)
            stat_weights = [1] * len(target_stats)

        gains = [
            max(per_stat_dict.get(s, 0) - baseline_per_slot.get(s, 0), 0)
            for s in target_stats
        ]
        product = math.prod(
            (1 + g) ** (sw / total_w) for g, sw in zip(gains, stat_weights)
        )
        return product

    return score_fn


# ─── Normalizzazione materiali ──────────────────────────────


def normalize_mat(name, mat_aliases):
    return mat_aliases.get(name, name)


def get_available(mat_name, resource_budget, mat_aliases):
    return resource_budget.get(normalize_mat(mat_name, mat_aliases), 0)


# ─── Costruzione inventario ────────────────────────────────


def parse_inventory_from_config(cfg):
    """Converte le liste YAML in tuple (name, level, slot_type, needs_craft).

    Esclude pezzi con locked=true (non ancora sbloccati nel gioco).
    """

    def _parse(pieces, slot_type):
        return [
            (p["name"], p["level"], slot_type, p.get("craft", False))
            for p in pieces
            if not p.get("locked", False)
        ]

    inventory = (
        _parse(cfg.get("chest_pieces", []), "Chest")
        + _parse(cfg.get("wrist_pieces", []), "Wrist")
        + _parse(cfg.get("waist_pieces", []), "Waist")
    )
    w_inventory = (
        _parse(cfg.get("axe_attachments", []), LEVIATHAN_AXE)
        + _parse(cfg.get("blades_attachments", []), BLADES_OF_CHAOS)
        + _parse(cfg.get("spear_attachments", []), DRAUPNIR_SPEAR)
        + _parse(cfg.get("shield_attachments", []), SHIELD)
    )
    return inventory, w_inventory


def build_available_df(all_pieces_df, inventory):
    """Filtra il DF armature ai soli pezzi in inventario (fino al livello posseduto)."""
    if not inventory:
        return pd.DataFrame()
    filters = []
    for piece_name, max_lvl, piece_type, _ in inventory:
        mask = (
            (all_pieces_df[PIECE_NAME_COL] == piece_name)
            & (all_pieces_df[PIECE_TYPE_COL] == piece_type)
            & (all_pieces_df[LEVEL_COL] <= max_lvl)
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
            (all_weapons_df[WEAPON_NAME_COL] == wname)
            & (all_weapons_df[CATEGORY_COL] == cat)
            & (all_weapons_df[LEVEL_COL] <= max_lvl)
        )
        w_filters.append(mask)
    return all_weapons_df[pd.concat(w_filters, axis=1).any(axis=1)].copy()


# ─── Build attuale ──────────────────────────────────────────


def _compute_item_score(row, target_stats):
    """Score a single item row by target_stats (sum) or Total Stats."""
    if target_stats:
        return sum(
            v if pd.notna(v) else 0
            for v in (row.get(s, 0) for s in target_stats)
        )
    return row[TOTAL_STATS_COL]


def _find_best_item_in_slot(items_in_slot, df, name_col, cat_col, cat_value, target_stats):
    """Find the best item in a slot by score. Returns (row_copy, name, lvl) or None."""
    best_item = None
    best_score = -1
    for name, lvl, _ in items_in_slot:
        row = df[
            (df[name_col] == name)
            & (df[cat_col] == cat_value)
            & (df[LEVEL_COL] == lvl)
        ]
        if row.empty:
            continue
        score = _compute_item_score(row.iloc[0], target_stats)
        if score > best_score:
            best_score = score
            best_item = (row.iloc[0].copy(), name, lvl)
    return best_item


def collect_current_build(
    inventory, available_df, w_inventory, w_available_df, target_stats=None
):
    """Restituisce (armor_current, weapon_current) — liste di Series pandas.

    If target_stats is provided, selects best item per slot by summing those specific stats.
    Otherwise, selects by Total Stats (original behavior).
    """
    armor_current = []
    for pt in ARMOR_TYPES:
        items_in_slot = [
            (name, lvl, craft)
            for name, lvl, t, craft in inventory
            if t == pt and not craft
        ]
        if not items_in_slot:
            continue
        best_item = _find_best_item_in_slot(
            items_in_slot, available_df, PIECE_NAME_COL, PIECE_TYPE_COL, pt, target_stats
        )
        if best_item:
            r, name, lvl = best_item
            r["Slot"] = f"Armatura — {pt}"
            r["Item Name"] = name
            r["Item Level"] = lvl
            armor_current.append(r)

    weapon_current = []
    for cat in WEAPON_CATEGORIES:
        items_in_slot = [
            (name, lvl, craft)
            for name, lvl, c, craft in w_inventory
            if c == cat and not craft
        ]
        if not items_in_slot:
            continue
        best_item = _find_best_item_in_slot(
            items_in_slot, w_available_df, WEAPON_NAME_COL, CATEGORY_COL, cat, target_stats
        )
        if best_item:
            r, name, lvl = best_item
            r["Slot"] = f"Arma — {cat}"
            r["Item Name"] = name
            r["Item Level"] = lvl
            weapon_current.append(r)

    return armor_current, weapon_current


# ─── Upgrade chain / Pareto / Solver ────────────────────────


def get_upgrade_chain_with_mats(
    df, name_col, name, cat_col, cat, current_lvl, resource_budget, mat_aliases
):
    upg_cols = [
        c for c in df.columns if c.startswith("Upgrade_") and c != UPGRADE_HACK_COL
    ]
    item_df = df[(df[name_col] == name) & (df[cat_col] == cat)].sort_values(LEVEL_COL)
    chain = []
    cum_hack = 0
    cum_mats = Counter()

    for _, r in item_df.iterrows():
        if r[LEVEL_COL] <= current_lvl:
            continue
        hack = (
            int(r.get(UPGRADE_HACK_COL, 0))
            if pd.notna(r.get(UPGRADE_HACK_COL, 0))
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

        chain.append((r[LEVEL_COL], r[TOTAL_STATS_COL], cum_hack, dict(cum_mats), per_stat))

    return chain


def _score_option(score_fn, per_stat_or_total_stats):
    """Score an option using score_fn if available, otherwise return the value directly."""
    if score_fn is not None:
        return score_fn(per_stat_or_total_stats)
    return per_stat_or_total_stats


def build_slot_options_with_mats(
    items_with_chains, score_fn=None, current_per_stat=None
):
    """Build upgrade options for a slot, optionally using a multi-objective score function."""
    current_best = max((s for _, _, s, _, _ in items_with_chains), default=0)

    if score_fn is not None and current_per_stat is not None:
        no_action_score = score_fn(current_per_stat)
    else:
        no_action_score = current_best

    options = [(0, no_action_score, "— nessuna azione —", {})]

    for item_name, item_lvl, item_stats, chain, needs_craft in items_with_chains:
        for target_lvl, target_stats, hack, mats, per_stat in chain:
            lvl_label = int(target_lvl) if target_lvl == int(target_lvl) else target_lvl
            resulting_score = _score_option(
                score_fn, per_stat if score_fn is not None else target_stats
            )
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


def _build_slot_opts(slot_pareto_dict, slots, budget_hack):
    """Filter feasible options per slot within hacksilver budget."""
    slot_opts = []
    for slot in slots:
        feasible = [
            (h, s, lbl, m)
            for h, s, lbl, m in slot_pareto_dict[slot]
            if h <= budget_hack
        ]
        if not feasible:
            feasible = [(0, 0, "— nessuna azione —", {})]
        slot_opts.append(feasible)
    return slot_opts


def _build_ilp_arrays(slot_opts, slots, mat_list, mat_idx):
    """Build numpy arrays for the ILP formulation."""
    import numpy as np

    n_vars = sum(len(opts) for opts in slot_opts)
    obj = np.zeros(n_vars)
    hack_row = np.zeros(n_vars)
    mat_rows = np.zeros((len(mat_list), n_vars)) if mat_list else np.zeros((0, n_vars))

    var_map = []
    offset = 0
    for si, opts in enumerate(slot_opts):
        for oi, (hack, score, _label, mats) in enumerate(opts):
            vi = offset + oi
            obj[vi] = -score
            hack_row[vi] = hack
            for mat_name, qty in mats.items():
                mat_rows[mat_idx[mat_name], vi] = qty
            var_map.append((si, oi))
        offset += len(opts)

    eq_rows = np.zeros((len(slots), n_vars))
    offset = 0
    for si, opts in enumerate(slot_opts):
        for oi in range(len(opts)):
            eq_rows[si, offset + oi] = 1
        offset += len(opts)

    return n_vars, obj, hack_row, mat_rows, eq_rows, var_map


def solve_with_resources(slot_pareto_dict, budget_hack, resource_budget, mat_aliases):
    """Solve resource-constrained multi-choice knapsack via ILP (scipy.optimize.milp)."""
    import numpy as np
    from scipy.optimize import Bounds, LinearConstraint, milp
    from scipy.sparse import csc_array

    slots = list(slot_pareto_dict.keys())
    if not slots:
        return -1, {}

    slot_opts = _build_slot_opts(slot_pareto_dict, slots, budget_hack)

    all_mats: set[str] = set()
    for opts in slot_opts:
        for _, _, _, m in opts:
            all_mats.update(m.keys())
    mat_list = sorted(all_mats)
    mat_idx = {m: i for i, m in enumerate(mat_list)}

    n_vars, obj, hack_row, mat_rows, eq_rows, var_map = _build_ilp_arrays(
        slot_opts, slots, mat_list, mat_idx
    )

    # Inequality constraints: hacksilver + materials
    ineq_matrix = np.vstack(
        [hack_row.reshape(1, -1)] + ([mat_rows] if mat_list else [])
    )
    ineq_ub = np.array(
        [budget_hack]
        + [get_available(m, resource_budget, mat_aliases) for m in mat_list]
    )

    constraints = [
        LinearConstraint(csc_array(eq_rows), lb=1, ub=1),
        LinearConstraint(csc_array(ineq_matrix), ub=ineq_ub),  # type: ignore[arg-type]
    ]

    integrality = np.ones(n_vars)
    bounds = Bounds(lb=0.0, ub=1.0)  # type: ignore[arg-type]

    result = milp(obj, constraints=constraints, integrality=integrality, bounds=bounds)

    if not result.success:
        return -1, {}

    # Extract chosen options
    x = np.round(result.x).astype(int)
    best_total = 0
    best_choices = {}
    for vi in range(n_vars):
        if x[vi] == 1:
            si, oi = var_map[vi]
            slot = slots[si]
            hack, score, label, mats = slot_opts[si][oi]
            best_choices[slot] = (hack, score, label, mats)
            best_total += score

    return best_total, best_choices


# ─── Costruzione Pareto per tutti gli slot ──────────────────


def _collect_slot_items(inv_entries, df, name_col, cat_col, cat_value,
                        resource_budget, mat_aliases):
    """Collect items and upgrade chains for one slot from inventory entries.

    Returns (items, current_best_row) where items is a list of
    (name, lvl, stats, chain, needs_craft) tuples.
    """
    items = []
    current_best_row = None
    for name, lvl, needs_craft in inv_entries:
        if needs_craft:
            effective_lvl = lvl - 1
            stats = 0
        else:
            effective_lvl = lvl
            row = df[
                (df[name_col] == name)
                & (df[cat_col] == cat_value)
                & (df[LEVEL_COL] == lvl)
            ]
            if not row.empty:
                stats = row.iloc[0][TOTAL_STATS_COL]
                if current_best_row is None or stats > current_best_row[TOTAL_STATS_COL]:
                    current_best_row = row.iloc[0]
            else:
                stats = 0
        chain = get_upgrade_chain_with_mats(
            df, name_col, name, cat_col, cat_value,
            effective_lvl, resource_budget, mat_aliases,
        )
        items.append((name, lvl, stats, chain, needs_craft))
    return items, current_best_row


def _compute_slot_pareto(items, current_best_row, slot_label, score_fns):
    """Compute Pareto frontier for a single slot."""
    score_fn = (score_fns or {}).get(slot_label)
    current_per_stat = None
    if score_fn is not None and current_best_row is not None:
        current_per_stat = {col: current_best_row.get(col, 0) for col in STAT_COLS}
    return pareto_frontier_with_mats(
        build_slot_options_with_mats(
            items, score_fn=score_fn, current_per_stat=current_per_stat
        )
    )


def build_all_pareto(
    inventory,
    w_inventory,
    all_pieces_df,
    all_weapons_df,
    resource_budget,
    mat_aliases,
    score_fns=None,
):
    """Build Pareto frontier for all slots."""
    slot_pareto = {}

    for pt in ARMOR_TYPES:
        entries = [(n, lv, cr) for n, lv, t, cr in inventory if t == pt]
        items, best_row = _collect_slot_items(
            entries, all_pieces_df, PIECE_NAME_COL, PIECE_TYPE_COL, pt,
            resource_budget, mat_aliases,
        )
        slot_label = f"Armatura — {pt}"
        slot_pareto[slot_label] = _compute_slot_pareto(items, best_row, slot_label, score_fns)

    for cat in WEAPON_CATEGORIES:
        entries = [(n, lv, cr) for n, lv, c, cr in w_inventory if c == cat]
        items, best_row = _collect_slot_items(
            entries, all_weapons_df, WEAPON_NAME_COL, CATEGORY_COL, cat,
            resource_budget, mat_aliases,
        )
        if items:
            slot_label = f"Arma — {cat}"
            slot_pareto[slot_label] = _compute_slot_pareto(items, best_row, slot_label, score_fns)

    return slot_pareto


# ─── Decomposizione piano in step singoli ───────────────────


def _get_per_level_cost(df, name_col, name, cat_col, cat, level, mat_aliases):
    """Return (hack, mats_dict) for a single level upgrade to given level."""
    upg_cols = [
        c for c in df.columns if c.startswith("Upgrade_") and c != UPGRADE_HACK_COL
    ]
    row = df[(df[name_col] == name) & (df[cat_col] == cat) & (df[LEVEL_COL] == level)]
    if row.empty:
        return 0, {}
    r = row.iloc[0]
    hack = (
        int(r.get(UPGRADE_HACK_COL, 0))
        if pd.notna(r.get(UPGRADE_HACK_COL, 0))
        else 0
    )
    mats = {}
    for c in upg_cols:
        v = r.get(c, 0)
        if pd.notna(v) and v > 0:
            mat_name = normalize_mat(c.replace("Upgrade_", ""), mat_aliases)
            mats[mat_name] = mats.get(mat_name, 0) + int(v)
    return hack, mats


def _int_if_whole(value):
    """Convert float to int if it's a whole number."""
    return int(value) if value == int(value) else value


def _resolve_slot_df(slot, all_pieces_df, all_weapons_df):
    """Determine DataFrame and column names based on slot label."""
    if slot.startswith("Armatura"):
        return all_pieces_df, PIECE_NAME_COL, PIECE_TYPE_COL, slot.replace("Armatura — ", "")
    return all_weapons_df, WEAPON_NAME_COL, CATEGORY_COL, slot.replace("Arma — ", "")


def decompose_plan_to_steps(opt_actions, all_pieces_df, all_weapons_df, mat_aliases):
    """Decompose multi-level upgrade actions into individual per-level steps."""
    _label_re = re.compile(r"^(★craft\+)?(.+?) (\d+(?:\.\d+)?)→(\d+(?:\.\d+)?)$")

    for action in opt_actions:
        match = _label_re.match(action["label"])
        if not match:
            action["steps"] = []
            continue

        craft_prefix = match.group(1) or ""
        piece_name = match.group(2)
        from_level = _int_if_whole(float(match.group(3)))
        to_level = _int_if_whole(float(match.group(4)))

        df, name_col, cat_col, cat = _resolve_slot_df(
            action["slot"], all_pieces_df, all_weapons_df
        )

        item_levels = (
            df[(df[name_col] == piece_name) & (df[cat_col] == cat)]
            .sort_values(LEVEL_COL)[LEVEL_COL]
            .tolist()
        )
        target_levels = [lv for lv in item_levels if from_level < lv <= to_level]

        steps = []
        prev_level = from_level
        for lv in target_levels:
            hack, mats = _get_per_level_cost(
                df, name_col, piece_name, cat_col, cat, lv, mat_aliases
            )
            step_cp = craft_prefix if not steps else ""
            lv_display = _int_if_whole(lv)
            prev_display = _int_if_whole(prev_level)
            steps.append({
                "from_level": prev_display,
                "to_level": lv_display,
                "hack": hack,
                "mats": dict(sorted(mats.items())) if mats else {},
                "label": f"{step_cp}{piece_name} {prev_display}→{lv_display}",
            })
            prev_level = lv

        action["steps"] = steps

    return opt_actions


# ─── Shopping list: materiali per raggiungere un target ─────


_INF_BUDGET = type("_Inf", (), {"get": staticmethod(lambda k, d=0: 10**9)})()


def compute_shopping_list(
    inventory, w_inventory, all_pieces_df, all_weapons_df, mat_aliases
):
    """Compute all materials needed to max out every owned piece.

    Returns dict of {material_name: total_needed}.
    """
    total_mats = Counter()
    total_hack = 0

    for name, lvl, pt, needs_craft in inventory:
        effective_lvl = (lvl - 1) if needs_craft else lvl
        chain = get_upgrade_chain_with_mats(
            all_pieces_df,
            PIECE_NAME_COL,
            name,
            PIECE_TYPE_COL,
            pt,
            effective_lvl,
            _INF_BUDGET,
            mat_aliases,
        )
        if chain:
            # Last entry has cumulative costs
            _, _, cum_hack, cum_mats, _ = chain[-1]
            total_hack += cum_hack
            total_mats.update(cum_mats)

    for name, lvl, cat, needs_craft in w_inventory:
        effective_lvl = (lvl - 1) if needs_craft else lvl
        chain = get_upgrade_chain_with_mats(
            all_weapons_df,
            WEAPON_NAME_COL,
            name,
            CATEGORY_COL,
            cat,
            effective_lvl,
            {},
            mat_aliases,
        )
        if chain:
            _, _, cum_hack, cum_mats, _ = chain[-1]
            total_hack += cum_hack
            total_mats.update(cum_mats)

    return total_hack, dict(total_mats)
