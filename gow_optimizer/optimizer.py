"""Ottimizzatore build: inventario, upgrade chain, Pareto, solver."""

import math
from collections import Counter

import pandas as pd

from gow_optimizer.scraper import STAT_COLS

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
        _parse(cfg.get("axe_attachments", []), "Leviathan Axe")
        + _parse(cfg.get("blades_attachments", []), "Blades of Chaos")
        + _parse(cfg.get("spear_attachments", []), "Draupnir Spear")
        + _parse(cfg.get("shield_attachments", []), "Shield")
    )
    return inventory, w_inventory


def build_available_df(all_pieces_df, inventory):
    """Filtra il DF armature ai soli pezzi in inventario (fino al livello posseduto)."""
    if not inventory:
        return pd.DataFrame()
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


def collect_current_build(
    inventory, available_df, w_inventory, w_available_df, target_stats=None
):
    """Restituisce (armor_current, weapon_current) — liste di Series pandas.

    If target_stats is provided, selects best item per slot by summing those specific stats.
    Otherwise, selects by Total Stats (original behavior).

    Args:
        target_stats: Optional list of stat names to optimize (e.g., ["Strength", "Defense"]).
                     If None, uses Total Stats.
    """
    armor_current = []
    for pt in ["Chest", "Wrist", "Waist"]:
        # Collect all items in inventory for this piece type
        items_in_slot = [
            (name, lvl, craft)
            for name, lvl, t, craft in inventory
            if t == pt and not craft
        ]

        if not items_in_slot:
            continue

        # Find best item by selected stats or Total Stats
        best_item = None
        best_score = -1
        slot_label = f"Armatura — {pt}"

        for name, lvl, _ in items_in_slot:
            row = available_df[
                (available_df["Piece Name"] == name)
                & (available_df["Piece Type"] == pt)
                & (available_df["Level"] == lvl)
            ]
            if row.empty:
                continue

            # Compute score based on target_stats or Total Stats
            if target_stats:
                # Sum selected stats, treating NaN as 0
                score = sum(
                    v if pd.notna(v) else 0
                    for v in (row.iloc[0].get(s, 0) for s in target_stats)
                )
            else:
                score = row.iloc[0]["Total Stats"]

            if score > best_score:
                best_score = score
                best_item = (row.iloc[0].copy(), name, lvl)

        if best_item:
            r, name, lvl = best_item
            r["Slot"] = slot_label
            r["Item Name"] = name
            r["Item Level"] = lvl
            armor_current.append(r)

    weapon_current = []
    for cat in ["Leviathan Axe", "Blades of Chaos", "Draupnir Spear", "Shield"]:
        # Collect all items in inventory for this weapon category
        items_in_slot = [
            (name, lvl, craft)
            for name, lvl, c, craft in w_inventory
            if c == cat and not craft
        ]

        if not items_in_slot:
            continue

        # Find best item by selected stats or Total Stats
        best_item = None
        best_score = -1
        slot_label = f"Arma — {cat}"

        for name, lvl, _ in items_in_slot:
            row = w_available_df[
                (w_available_df["Weapon Name"] == name)
                & (w_available_df["Category"] == cat)
                & (w_available_df["Level"] == lvl)
            ]
            if row.empty:
                continue

            # Compute score based on target_stats or Total Stats
            if target_stats:
                # Sum selected stats, treating NaN as 0
                score = sum(
                    v if pd.notna(v) else 0
                    for v in (row.iloc[0].get(s, 0) for s in target_stats)
                )
            else:
                score = row.iloc[0]["Total Stats"]

            if score > best_score:
                best_score = score
                best_item = (row.iloc[0].copy(), name, lvl)

        if best_item:
            r, name, lvl = best_item
            r["Slot"] = slot_label
            r["Item Name"] = name
            r["Item Level"] = lvl
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


def build_slot_options_with_mats(
    items_with_chains, score_fn=None, current_per_stat=None
):
    """Build upgrade options for a slot, optionally using a multi-objective score function.

    Args:
        items_with_chains: List of (name, lvl, stats, chain, needs_craft) tuples.
        score_fn: Optional function that takes per_stat dict and returns a score.
                 If None, uses Total Stats (original behavior).
        current_per_stat: Optional dict of {stat_name: value} for current item. Used to score
                         the no-action option when score_fn is provided.

    Returns:
        List of (hack, score, label, mats) tuples representing upgrade options.
    """
    current_best = max((s for _, _, s, _, _ in items_with_chains), default=0)

    # When score_fn is provided (multi-objective), score the no-action option using score_fn
    # Otherwise use current_best (Total Stats) for backwards compatibility
    if score_fn is not None and current_per_stat is not None:
        no_action_score = score_fn(current_per_stat)
    else:
        no_action_score = current_best

    options = [(0, no_action_score, "— nessuna azione —", {})]

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
    """Solve resource-constrained multi-choice knapsack via ILP (scipy.optimize.milp)."""
    import numpy as np
    from scipy.optimize import LinearConstraint, milp
    from scipy.sparse import csc_array

    slots = list(slot_pareto_dict.keys())
    if not slots:
        return -1, {}

    # Flatten all options: build flat arrays of hack costs, scores, labels, mats
    slot_opts = []  # list of list of (hack, score, label, mats)
    for slot in slots:
        feasible = [
            (h, s, l, m) for h, s, l, m in slot_pareto_dict[slot] if h <= budget_hack
        ]
        if not feasible:
            feasible = [(0, 0, "— nessuna azione —", {})]
        slot_opts.append(feasible)

    # Collect all material names
    all_mats = set()
    for opts in slot_opts:
        for _, _, _, m in opts:
            all_mats.update(m.keys())
    mat_list = sorted(all_mats)
    mat_idx = {m: i for i, m in enumerate(mat_list)}

    # Build flat variable arrays
    n_vars = sum(len(opts) for opts in slot_opts)
    c = np.zeros(n_vars)  # objective (negate for minimization)
    hack_row = np.zeros(n_vars)  # hacksilver costs
    mat_rows = np.zeros((len(mat_list), n_vars)) if mat_list else np.zeros((0, n_vars))

    var_map = []  # (slot_index, option_index) for each variable
    offset = 0
    for si, opts in enumerate(slot_opts):
        for oi, (hack, score, label, mats) in enumerate(opts):
            vi = offset + oi
            c[vi] = -score  # minimize negative score = maximize score
            hack_row[vi] = hack
            for mat_name, qty in mats.items():
                mat_rows[mat_idx[mat_name], vi] = qty
            var_map.append((si, oi))
        offset += len(opts)

    # Constraints: exactly one option per slot
    # Σ_i x[s][i] = 1 for each slot s
    eq_rows = np.zeros((len(slots), n_vars))
    offset = 0
    for si, opts in enumerate(slot_opts):
        for oi in range(len(opts)):
            eq_rows[si, offset + oi] = 1
        offset += len(opts)

    # Build constraint matrices
    # 1) Slot equality constraints: row per slot, sum = 1
    # 2) Hacksilver: sum <= budget_hack
    # 3) Materials: sum per material <= available
    ineq_A = np.vstack(
        [hack_row.reshape(1, -1)] + ([mat_rows] if len(mat_list) > 0 else [])
    )
    ineq_ub = np.array(
        [budget_hack]
        + [get_available(m, resource_budget, mat_aliases) for m in mat_list]
    )

    constraints = [
        LinearConstraint(csc_array(eq_rows), lb=1, ub=1),
        LinearConstraint(csc_array(ineq_A), lb=-np.inf, ub=ineq_ub),
    ]

    integrality = np.ones(n_vars)  # all variables are integer (binary)
    bounds = type("Bounds", (), {"lb": np.zeros(n_vars), "ub": np.ones(n_vars)})()

    from scipy.optimize import Bounds as SpBounds

    bounds = SpBounds(lb=np.zeros(n_vars), ub=np.ones(n_vars))

    result = milp(c, constraints=constraints, integrality=integrality, bounds=bounds)

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


def build_all_pareto(
    inventory,
    w_inventory,
    all_pieces_df,
    all_weapons_df,
    resource_budget,
    mat_aliases,
    score_fns=None,
):
    """Build Pareto frontier for all slots.

    Args:
        score_fns: Optional dict mapping slot_label -> score_fn for multi-objective optimization.
                  If None, uses original Total Stats-based scoring.
    """
    slot_pareto = {}

    for pt in ["Chest", "Wrist", "Waist"]:
        items = []
        current_best_row = None
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
                if not row.empty:
                    stats = row.iloc[0]["Total Stats"]
                    # Track the best current item for scoring no-action option
                    if (
                        current_best_row is None
                        or stats > current_best_row["Total Stats"]
                    ):
                        current_best_row = row.iloc[0]
                else:
                    stats = 0
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
        # Compute current_per_stat for no-action option when score_fn is present
        current_per_stat = None
        if score_fn is not None and current_best_row is not None:
            current_per_stat = {col: current_best_row.get(col, 0) for col in STAT_COLS}
        slot_pareto[slot_label] = pareto_frontier_with_mats(
            build_slot_options_with_mats(
                items, score_fn=score_fn, current_per_stat=current_per_stat
            )
        )

    for cat in ["Leviathan Axe", "Blades of Chaos", "Draupnir Spear", "Shield"]:
        items = []
        current_best_row = None
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
                if not row.empty:
                    stats = row.iloc[0]["Total Stats"]
                    # Track the best current item for scoring no-action option
                    if (
                        current_best_row is None
                        or stats > current_best_row["Total Stats"]
                    ):
                        current_best_row = row.iloc[0]
                else:
                    stats = 0
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
            # Compute current_per_stat for no-action option when score_fn is present
            current_per_stat = None
            if score_fn is not None and current_best_row is not None:
                current_per_stat = {
                    col: current_best_row.get(col, 0) for col in STAT_COLS
                }
            slot_pareto[slot_label] = pareto_frontier_with_mats(
                build_slot_options_with_mats(
                    items, score_fn=score_fn, current_per_stat=current_per_stat
                )
            )

    return slot_pareto


# ─── Decomposizione piano in step singoli ───────────────────


def _get_per_level_cost(df, name_col, name, cat_col, cat, level, mat_aliases):
    """Return (hack, mats_dict) for a single level upgrade to given level."""
    upg_cols = [
        c for c in df.columns if c.startswith("Upgrade_") and c != "Upgrade_Hacksilver"
    ]
    row = df[(df[name_col] == name) & (df[cat_col] == cat) & (df["Level"] == level)]
    if row.empty:
        return 0, {}
    r = row.iloc[0]
    hack = (
        int(r.get("Upgrade_Hacksilver", 0))
        if pd.notna(r.get("Upgrade_Hacksilver", 0))
        else 0
    )
    mats = {}
    for c in upg_cols:
        v = r.get(c, 0)
        if pd.notna(v) and v > 0:
            mat_name = normalize_mat(c.replace("Upgrade_", ""), mat_aliases)
            mats[mat_name] = mats.get(mat_name, 0) + int(v)
    return hack, mats


def decompose_plan_to_steps(opt_actions, all_pieces_df, all_weapons_df, mat_aliases):
    """Decompose multi-level upgrade actions into individual per-level steps.

    Args:
        opt_actions: list of dicts with keys {slot, hack, stats, label, mats}
        all_pieces_df: DataFrame of armor pieces
        all_weapons_df: DataFrame of weapon attachments
        mat_aliases: dict for material name normalization

    Returns:
        The same opt_actions list, each augmented with a "steps" key containing
        a list of per-level steps: [{from_level, to_level, hack, mats, label}, ...]
        Single-level upgrades get exactly one step.
    """
    import re

    for action in opt_actions:
        label = action["label"]
        match = re.match(r"^(★craft\+)?(.+?) (\d+(?:\.\d+)?)→(\d+(?:\.\d+)?)$", label)
        if not match:
            action["steps"] = []
            continue

        craft_prefix = match.group(1) or ""
        piece_name = match.group(2)
        from_level = float(match.group(3))
        to_level = float(match.group(4))
        # Normalize to int when whole number
        from_level = int(from_level) if from_level == int(from_level) else from_level
        to_level = int(to_level) if to_level == int(to_level) else to_level
        slot = action["slot"]

        # Determine which DataFrame and columns to use
        if slot.startswith("Armatura"):
            df = all_pieces_df
            name_col, cat_col = "Piece Name", "Piece Type"
            cat = slot.replace("Armatura — ", "")
        else:
            df = all_weapons_df
            name_col, cat_col = "Weapon Name", "Category"
            cat = slot.replace("Arma — ", "")

        # Walk level by level, collecting all intermediate levels
        item_levels = (
            df[(df[name_col] == piece_name) & (df[cat_col] == cat)]
            .sort_values("Level")["Level"]
            .tolist()
        )
        # Filter to levels in (from_level, to_level]
        target_levels = [lv for lv in item_levels if from_level < lv <= to_level]

        steps = []
        prev_level = from_level
        for lv in target_levels:
            hack, mats = _get_per_level_cost(
                df, name_col, piece_name, cat_col, cat, lv, mat_aliases
            )
            step_cp = craft_prefix if len(steps) == 0 else ""
            lv_display = int(lv) if lv == int(lv) else lv
            prev_display = (
                int(prev_level) if prev_level == int(prev_level) else prev_level
            )
            step_label = f"{step_cp}{piece_name} {prev_display}→{lv_display}"
            steps.append(
                {
                    "from_level": prev_display,
                    "to_level": lv_display,
                    "hack": hack,
                    "mats": dict(sorted(mats.items())) if mats else {},
                    "label": step_label,
                }
            )
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
        if needs_craft:
            effective_lvl = lvl - 1
        else:
            effective_lvl = lvl
        chain = get_upgrade_chain_with_mats(
            all_pieces_df,
            "Piece Name",
            name,
            "Piece Type",
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
        if needs_craft:
            effective_lvl = lvl - 1
        else:
            effective_lvl = lvl
        chain = get_upgrade_chain_with_mats(
            all_weapons_df,
            "Weapon Name",
            name,
            "Category",
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
