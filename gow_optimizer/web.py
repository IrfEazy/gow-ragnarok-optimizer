"""God of War Ragnarök — Web UI (Flask)."""

import base64
import hashlib
import json
import logging
import re
import urllib.parse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template, request

from gow_optimizer.config import (
    PIECE_KEYS,
    SLOT_TO_KEY,
    coerce_resource_budget,
    get_data_file_paths,
    load_config,
    load_stat_preferences,
    load_web_inventory,
    save_stat_preferences,
    save_web_inventory,
)
from gow_optimizer.optimizer import (
    build_all_pareto,
    build_available_df,
    build_weapon_available_df,
    collect_current_build,
    get_available,
    make_score_fn,
    normalize_mat,
    parse_inventory_from_config,
    solve_with_resources,
)
from gow_optimizer.paths import TEMPLATES_DIR
from gow_optimizer.scraper import STAT_COLS, load_csvs

logger = logging.getLogger(__name__)

ARMOR_TYPES = ["Chest", "Wrist", "Waist"]
WEAPON_CATEGORIES = ["Leviathan Axe", "Blades of Chaos", "Draupnir Spear", "Shield"]
WEAPON_CATEGORIES_WITH_UPGRADES = ["Leviathan Axe", "Blades of Chaos", "Shield"]
PIECE_TYPE_COL = "Piece Type"
CATEGORY_COL = "Category"
TOTAL_STATS_COL = "Total Stats"
ITEM_NAME_COL = "Item Name"
ITEM_LEVEL_COL = "Item Level"

# ---------------------------------------------------------------------------
# Static data cache (CSV dataframes + mat aliases only)
# ---------------------------------------------------------------------------
_static_cache = None


def _load_static():
    global _static_cache
    if _static_cache is not None:
        return _static_cache

    cfg = load_config()
    armor_csv, weapons_csv = get_data_file_paths(cfg)
    mat_aliases = cfg.get("mat_aliases", {})

    all_pieces_df, all_weapons_df = load_csvs(armor_csv, weapons_csv)

    _static_cache = {
        "all_pieces_df": all_pieces_df,
        "all_weapons_df": all_weapons_df,
        "mat_aliases": mat_aliases,
    }
    return _static_cache


# ---------------------------------------------------------------------------
# Web‑inventory helpers (read / write the dedicated YAML)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Compute pipeline
# ---------------------------------------------------------------------------


def _build_inventory_from_web(web_data):
    """Build optimizer inventory tuples from web_inventory data."""
    cfg_like = {k: web_data.get(k, []) for k in PIECE_KEYS}
    return parse_inventory_from_config(cfg_like)


def _serialize_best_item(record, target_stats=None):
    # Handle rows from CSV data (use "Piece Name") or processed rows (use "Item Name")
    name_col = ITEM_NAME_COL if ITEM_NAME_COL in record else "Piece Name"
    name_col = name_col if name_col in record else "Weapon Name"  # For weapons
    level_col = ITEM_LEVEL_COL if ITEM_LEVEL_COL in record else "Level"

    # If target_stats specified, show only those stats; otherwise show all > 0
    if target_stats:
        stats_to_show = [s for s in target_stats if record.get(s, 0) > 0]
    else:
        stats_to_show = [s for s in STAT_COLS if record.get(s, 0) > 0]

    return {
        "name": record[name_col],
        "level": int(record[level_col]),
        "total": int(record[TOTAL_STATS_COL]),
        "stats": {stat: int(record.get(stat, 0)) for stat in stats_to_show},
    }


def _build_best_armor(armor_current, target_stats=None):
    best_armor = {}
    armor_total = 0

    for armor_type in ARMOR_TYPES:
        candidates = [row for row in armor_current if row[PIECE_TYPE_COL] == armor_type]
        if not candidates:
            continue
        # Score by target_stats (sum) if provided, otherwise by Total Stats
        if target_stats:
            best = max(candidates, key=lambda row: sum(row.get(s, 0) for s in target_stats))
        else:
            best = max(candidates, key=lambda row: row[TOTAL_STATS_COL])
        best_armor[armor_type] = _serialize_best_item(best, target_stats=target_stats)
        armor_total += best[TOTAL_STATS_COL]

    return best_armor, armor_total


def _build_best_weapons(weapon_current, target_stats=None):
    best_weapons = {}
    weapon_total = 0

    for category in WEAPON_CATEGORIES:
        candidates = [row for row in weapon_current if row[CATEGORY_COL] == category]
        if not candidates:
            continue
        # Score by target_stats (sum) if provided, otherwise by Total Stats
        if target_stats:
            best = max(candidates, key=lambda row: sum(row.get(s, 0) for s in target_stats))
        else:
            best = max(candidates, key=lambda row: row[TOTAL_STATS_COL])
        best_weapons[category] = _serialize_best_item(best, target_stats=target_stats)
        weapon_total += best[TOTAL_STATS_COL]

    return best_weapons, weapon_total


def _build_rankings(items, group_key, values, target_stats=None):
    """Build rankings of items per group, sorted by target_stats or Total Stats.

    Args:
        items: List of item rows (pandas Series)
        group_key: Column to group by (e.g., "Piece Type")
        values: Values of group_key to include (e.g., ["Chest", "Wrist"])
        target_stats: Optional list of stats to sort by. If None, uses Total Stats.
    """
    rankings = {}
    for value in values:
        grouped_items = [row for row in items if row[group_key] == value]

        # Sort by target_stats (sum of selected stats) or Total Stats
        if target_stats:
            sorted_items = sorted(
                grouped_items,
                key=lambda row: sum(row.get(s, 0) for s in target_stats),
                reverse=True,
            )
        else:
            sorted_items = sorted(
                grouped_items,
                key=lambda row: row[TOTAL_STATS_COL],
                reverse=True,
            )

        rankings[value] = [_serialize_best_item(row, target_stats=target_stats) for row in sorted_items]
    return rankings


def _build_pareto_data(slot_pareto):
    pareto_data = {}
    for slot, frontier in slot_pareto.items():
        pareto_data[slot] = [
            {
                "hack": hack,
                "stats": int(stats),
                "label": label,
                "mats": dict(sorted(mats.items())) if mats else {},
            }
            for hack, stats, label, mats in frontier
            if "nessuna" not in label
        ]
    return pareto_data


def _build_optimal_plan_data(slot_pareto, resource_budget, mat_aliases, grand_total):
    opt_total, choices = solve_with_resources(
        slot_pareto,
        resource_budget["Hacksilver"],
        resource_budget,
        mat_aliases,
    )
    opt_hack = sum(hack for hack, _, _, _ in choices.values())
    opt_mats = Counter()
    for _, _, _, mats in choices.values():
        opt_mats.update(mats)

    opt_actions = []
    for slot, (hack, stats, label, mats) in sorted(choices.items()):
        if "nessuna" in label:
            continue
        opt_actions.append(
            {
                "slot": slot,
                "hack": hack,
                "stats": int(stats),
                "label": label,
                "mats": dict(sorted(mats.items())) if mats else {},
            }
        )

    opt_mats_detail = []
    for material, used in sorted(opt_mats.items()):
        available = get_available(material, resource_budget, mat_aliases)
        opt_mats_detail.append({"name": material, "used": used, "available": available})

    return {
        "opt_gain": int(opt_total - grand_total),
        "opt_total": int(opt_total),
        "opt_hack": opt_hack,
        "opt_hack_remaining": resource_budget["Hacksilver"] - opt_hack,
        "opt_actions": opt_actions,
        "opt_mats": opt_mats_detail,
    }


def _find_missing_materials(row, upgrade_columns, resource_budget, mat_aliases):
    missing = []
    for column in upgrade_columns:
        value = row.get(column, 0)
        if not (value and value > 0):
            continue
        material = normalize_mat(column.replace("Upgrade_", ""), mat_aliases)
        available = get_available(material, resource_budget, mat_aliases)
        if available < value:
            missing.append({"mat": material, "need": int(value), "have": available})
    return missing


def _iter_group_entries(entries, group):
    for name, level, slot_value, needs_craft in entries:
        if slot_value == group:
            yield name, level, needs_craft


def _find_next_upgrade_row(
    dataframe, name_column, group_column, name, group, level, needs_craft
):
    next_level = level if needs_craft else level + 1
    row = dataframe[
        (dataframe[name_column] == name)
        & (dataframe[group_column] == group)
        & (dataframe["Level"] == next_level)
    ]
    if row.empty:
        return None, next_level
    return row.iloc[0], next_level


def _build_blocked_item(
    name,
    level,
    next_level,
    needs_craft,
    row,
    upgrade_columns,
    resource_budget,
    mat_aliases,
):
    missing = _find_missing_materials(
        row,
        upgrade_columns,
        resource_budget,
        mat_aliases,
    )
    if not missing:
        return None
    action = f"craft LVL {level}" if needs_craft else f"{level}→{next_level}"
    return {"name": name, "action": action, "missing": missing}


def _collect_blocked_items(
    entries,
    dataframe,
    *,
    name_column,
    group_column,
    groups,
    resource_budget,
    mat_aliases,
):
    blocked = []
    upgrade_columns = [
        column
        for column in dataframe.columns
        if column.startswith("Upgrade_") and column != "Upgrade_Hacksilver"
    ]

    for group in groups:
        for name, level, needs_craft in _iter_group_entries(entries, group):
            row, next_level = _find_next_upgrade_row(
                dataframe,
                name_column,
                group_column,
                name,
                group,
                level,
                needs_craft,
            )
            if row is None:
                continue
            blocked_item = _build_blocked_item(
                name,
                level,
                next_level,
                needs_craft,
                row,
                upgrade_columns,
                resource_budget,
                mat_aliases,
            )
            if blocked_item is None:
                continue
            blocked.append(blocked_item)

    return blocked


def _collect_blocked_armor(inventory, all_pieces_df, resource_budget, mat_aliases):
    return _collect_blocked_items(
        inventory,
        all_pieces_df,
        name_column="Piece Name",
        group_column=PIECE_TYPE_COL,
        groups=ARMOR_TYPES,
        resource_budget=resource_budget,
        mat_aliases=mat_aliases,
    )


def _collect_blocked_weapons(w_inventory, all_weapons_df, resource_budget, mat_aliases):
    return _collect_blocked_items(
        w_inventory,
        all_weapons_df,
        name_column="Weapon Name",
        group_column=CATEGORY_COL,
        groups=WEAPON_CATEGORIES_WITH_UPGRADES,
        resource_budget=resource_budget,
        mat_aliases=mat_aliases,
    )


def _candidate_step_action(
    slot,
    options,
    current_stats,
    used_budget,
    used_mats,
    resource_budget,
    mat_aliases,
    target_stats=None,
    score_fns=None,
):
    best_action = None
    best_eff = -1

    for hack, stats, label, mats in options:
        if hack == 0 or stats <= current_stats:
            continue
        test = Counter(used_mats)
        test.update(mats)
        if not all(
            test[material] <= get_available(material, resource_budget, mat_aliases)
            for material in test
        ):
            continue
        if used_budget + hack > resource_budget["Hacksilver"]:
            continue
        gain = stats - current_stats
        eff = gain / hack * 1000
        if eff <= best_eff:
            continue
        best_eff = eff
        best_action = (slot, hack, stats, label, gain, eff, mats)

    return best_action


def _find_best_step_action(
    remaining_slots,
    cur_stats,
    used_budget,
    used_mats,
    resource_budget,
    mat_aliases,
    target_stats=None,
    score_fns=None,
):
    best_action = None
    best_eff = -1

    for slot, options in remaining_slots.items():
        action = _candidate_step_action(
            slot,
            options,
            cur_stats[slot],
            used_budget,
            used_mats,
            resource_budget,
            mat_aliases,
            target_stats=target_stats,
            score_fns=score_fns,
        )
        if action is None or action[5] <= best_eff:
            continue
        best_eff = action[5]
        best_action = action

    return best_action


def _apply_step_action(step_i, action, remaining_slots, cur_stats, used_mats, running):
    slot, hack, stats, label, gain, eff, mats = action
    running += gain
    cur_stats[slot] = stats
    used_mats.update(mats)
    remaining_slots[slot] = [
        (cur_hack, cur_stats_value, cur_label, cur_mats)
        for cur_hack, cur_stats_value, cur_label, cur_mats in remaining_slots[slot]
        if cur_stats_value > stats
    ]
    step = {
        "step": step_i,
        "label": label,
        "slot": slot,
        "gain": int(gain),
        "hack": hack,
        "eff": round(eff, 2),
        "grand_total": int(running),
        "mats": dict(sorted(mats.items())) if mats else {},
    }
    return step, running, hack


def _serialize_consumed_mats(used_mats, resource_budget, mat_aliases):
    consumed = []
    for material, used in sorted(used_mats.items()):
        available = get_available(material, resource_budget, mat_aliases)
        consumed.append(
            {
                "name": material,
                "used": used,
                "available": available,
                "remaining": available - used,
            }
        )
    return consumed


def _build_step_plan(slot_pareto, resource_budget, mat_aliases, grand_total, target_stats=None, score_fns=None):
    remaining_slots = {slot: list(options) for slot, options in slot_pareto.items() if options}
    cur_stats = {slot: options[0][1] for slot, options in slot_pareto.items() if options}
    running = grand_total
    used_budget = 0
    used_mats = Counter()
    steps = []

    for step_i in range(1, 50):
        best_action = _find_best_step_action(
            remaining_slots,
            cur_stats,
            used_budget,
            used_mats,
            resource_budget,
            mat_aliases,
            target_stats=target_stats,
            score_fns=score_fns,
        )
        if best_action is None:
            break

        step, running, spent_hack = _apply_step_action(
            step_i,
            best_action,
            remaining_slots,
            cur_stats,
            used_mats,
            running,
        )
        used_budget += spent_hack
        step["cum_hack"] = used_budget
        steps.append(step)

    step_mats_consumed = _serialize_consumed_mats(
        used_mats,
        resource_budget,
        mat_aliases,
    )

    return {
        "steps": steps,
        "step_final_total": int(running),
        "step_final_gain": int(running - grand_total),
        "step_hack_spent": used_budget,
        "step_hack_remaining": resource_budget["Hacksilver"] - used_budget,
        "step_mats_consumed": step_mats_consumed,
    }


def _serialize_resources(resource_budget):
    return [
        {"name": material, "qty": quantity}
        for material, quantity in sorted(resource_budget.items())
    ]


# ---------------------------------------------------------------------------
# Export/Import functionality
# ---------------------------------------------------------------------------


def export_build(build_data):
    """Export build data to JSON-serializable dict with metadata."""
    return {
        "version": "0.1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "resource_budget": build_data.get("resource_budget", {}),
        "armor": {
            "chest": build_data.get("chest_pieces", []),
            "wrist": build_data.get("wrist_pieces", []),
            "waist": build_data.get("waist_pieces", []),
        },
        "weapons": {
            "axe": build_data.get("axe_attachments", []),
            "blades": build_data.get("blades_attachments", []),
            "spear": build_data.get("spear_attachments", []),
            "shield": build_data.get("shield_attachments", []),
        },
    }


def import_build(exported_data):
    """Restore exported build data to inventory format."""
    return {
        "resource_budget": exported_data.get("resource_budget", {}),
        "chest_pieces": exported_data.get("armor", {}).get("chest", []),
        "wrist_pieces": exported_data.get("armor", {}).get("wrist", []),
        "waist_pieces": exported_data.get("armor", {}).get("waist", []),
        "axe_attachments": exported_data.get("weapons", {}).get("axe", []),
        "blades_attachments": exported_data.get("weapons", {}).get("blades", []),
        "spear_attachments": exported_data.get("weapons", {}).get("spear", []),
        "shield_attachments": exported_data.get("weapons", {}).get("shield", []),
    }


def export_build_csv(build_data):
    """Export build to CSV format."""
    lines = ["Piece Type,Name,Level,Craft"]

    # Export armor
    for piece_type, pieces in [
        ("Chest", build_data.get("chest_pieces", [])),
        ("Wrist", build_data.get("wrist_pieces", [])),
        ("Waist", build_data.get("waist_pieces", [])),
    ]:
        for piece in pieces:
            craft = "Yes" if piece.get("craft") else "No"
            lines.append(
                f'{piece_type},{piece.get("name", "")},{piece.get("level", 0)},{craft}'
            )

    # Export weapons
    for weapon_type, attachments in [
        ("Axe Attachment", build_data.get("axe_attachments", [])),
        ("Blades Attachment", build_data.get("blades_attachments", [])),
        ("Spear Attachment", build_data.get("spear_attachments", [])),
        ("Shield Attachment", build_data.get("shield_attachments", [])),
    ]:
        for attachment in attachments:
            craft = "Yes" if attachment.get("craft") else "No"
            lines.append(
                f'{weapon_type},{attachment.get("name", "")},{attachment.get("level", 0)},{craft}'
            )

    return "\n".join(lines)


def generate_shareable_url(base_url, build_data):
    """Generate URL-safe shareable build link."""
    exported = export_build(build_data)
    json_str = json.dumps(exported, separators=(",", ":"))
    encoded = base64.urlsafe_b64encode(json_str.encode()).decode().rstrip("=")
    return f"{base_url}/?build={encoded}"


# ---------------------------------------------------------------------------
# Build slot management (multi-save)
# ---------------------------------------------------------------------------


def create_build_slot(slot_name, build_data, current_slots):
    """Create a new named build slot."""
    slots = deepcopy(current_slots)
    slots[slot_name] = deepcopy(build_data)
    return slots


def list_build_slots(slots):
    """List all saved build slots."""
    return [{"name": slot_name} for slot_name in sorted(slots.keys())]


def load_build_slot(slot_name, slots):
    """Load a named build slot. Raises KeyError if not found."""
    if slot_name not in slots:
        raise KeyError(f"Build slot '{slot_name}' not found")
    return deepcopy(slots[slot_name])


def delete_build_slot(slot_name, slots):
    """Delete a named build slot."""
    result = deepcopy(slots)
    result.pop(slot_name, None)
    return result


def load_build_slots():
    """Load all saved build slots from storage."""
    cfg = load_config()
    return cfg.get("build_slots", {})


def save_build_slots(slots):
    """Save build slots to storage."""
    cfg = load_config()
    cfg["build_slots"] = slots
    from gow_optimizer.paths import CONFIG_FILE
    import yaml

    with open(CONFIG_FILE, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False)

def safe_resource_update(resources, deduction):
    """Safely deduct resources, raises ValueError if would go negative."""
    result = deepcopy(resources)

    for material, amount in deduction.items():
        if result.get(material, 0) - amount < 0:
            raise ValueError(
                f"insufficient {material}: need {amount}, have {result.get(material, 0)}"
            )
        result[material] = result.get(material, 0) - amount

    return result



def _compute_all(web_data=None, target_stats=None):
    """Run the full pipeline. Uses web_inventory.yaml if no data given.

    Args:
        web_data: Inventory and resource data. If None, loads from config.
        target_stats: List of stats to optimize (subset of STAT_COLS).
                     Defaults to all stats (backwards-compatible).
    """
    st = _load_static()
    all_pieces_df = st["all_pieces_df"]
    all_weapons_df = st["all_weapons_df"]
    mat_aliases = st["mat_aliases"]

    if web_data is None:
        web_data = load_web_inventory()

    resource_budget = web_data.get("resource_budget", {})
    inventory, w_inventory = _build_inventory_from_web(web_data)
    available_df = build_available_df(all_pieces_df, inventory)
    w_available_df = build_weapon_available_df(all_weapons_df, w_inventory)

    # Collect current build, respecting user target_stats if provided
    armor_current, weapon_current = collect_current_build(
        inventory,
        available_df,
        w_inventory,
        w_available_df,
        target_stats=target_stats,
    )

    best_armor, armor_total = _build_best_armor(armor_current, target_stats=target_stats)
    best_weapons, weapon_total = _build_best_weapons(weapon_current, target_stats=target_stats)
    grand_total = armor_total + weapon_total

    # Build rankings from all available items (not just current build),
    # sorted by target_stats if provided, otherwise by Total Stats
    rankings_armor = _build_rankings(
        [row for _, row in available_df.iterrows()],
        PIECE_TYPE_COL,
        ARMOR_TYPES,
        target_stats=target_stats,
    )
    rankings_weapons = _build_rankings(
        [row for _, row in w_available_df.iterrows()],
        CATEGORY_COL,
        WEAPON_CATEGORIES,
        target_stats=target_stats,
    )

    craft_armor = [(n, l, pt) for n, l, pt, c in inventory if c]
    craft_weapons = [(n, l, cat) for n, l, cat, c in w_inventory if c]

    # Build score_fns dict for upgrade optimization using actual current build as baseline
    score_fns = None
    if target_stats:
        score_fns = {}
        # Compute per-stat baseline for each armor slot (from current build)
        for pt in ARMOR_TYPES:
            slot_label = f"Armatura — {pt}"
            baseline = {col: 0 for col in STAT_COLS}
            for item in armor_current:
                if f"Armatura — {pt}" in item.get("Slot", ""):
                    for col in STAT_COLS:
                        baseline[col] = item.get(col, 0)
                    break
            score_fns[slot_label] = make_score_fn(target_stats, baseline)

        # Compute per-stat baseline for each weapon slot (from current build)
        for cat in WEAPON_CATEGORIES_WITH_UPGRADES:
            slot_label = f"Arma — {cat}"
            baseline = {col: 0 for col in STAT_COLS}
            for item in weapon_current:
                if f"Arma — {cat}" in item.get("Slot", ""):
                    for col in STAT_COLS:
                        baseline[col] = item.get(col, 0)
                    break
            score_fns[slot_label] = make_score_fn(target_stats, baseline)

    slot_pareto = build_all_pareto(
        inventory,
        w_inventory,
        all_pieces_df,
        all_weapons_df,
        resource_budget,
        mat_aliases,
        score_fns=score_fns,
    )
    pareto_data = _build_pareto_data(slot_pareto)
    optimal_plan = _build_optimal_plan_data(
        slot_pareto,
        resource_budget,
        mat_aliases,
        grand_total,
    )
    blocked = _collect_blocked_armor(
        inventory,
        all_pieces_df,
        resource_budget,
        mat_aliases,
    ) + _collect_blocked_weapons(
        w_inventory,
        all_weapons_df,
        resource_budget,
        mat_aliases,
    )
    step_plan = _build_step_plan(
        slot_pareto,
        resource_budget,
        mat_aliases,
        grand_total,
        target_stats=target_stats,
        score_fns=score_fns,
    )
    resources = _serialize_resources(resource_budget)

    return {
        "best_armor": best_armor,
        "best_weapons": best_weapons,
        "armor_total": int(armor_total),
        "weapon_total": int(weapon_total),
        "grand_total": int(grand_total),
        "rankings_armor": rankings_armor,
        "rankings_weapons": rankings_weapons,
        "craft_armor": craft_armor,
        "craft_weapons": craft_weapons,
        "resources": resources,
        "hacksilver": resource_budget.get("Hacksilver", 0),
        "pareto_data": pareto_data,
        "blocked": blocked,
        **optimal_plan,
        **step_plan,
    }


def _parse_upgrade_label(label):
    match = re.match(r"^(★craft\+)?(.+?) (\d+)→(\d+)$", label)
    if not match:
        return None

    return {
        "piece_name": match.group(2),
        "from_level": int(match.group(3)),
        "to_level": int(match.group(4)),
    }


def _find_inventory_piece(web_data, slot, label):
    piece_key = SLOT_TO_KEY.get(slot)
    parsed_label = _parse_upgrade_label(label)
    if not piece_key or parsed_label is None:
        return None, None, None

    pieces = web_data.get(piece_key, [])
    for piece in pieces:
        if (
            piece.get("name") == parsed_label["piece_name"]
            and piece.get("level") == parsed_label["from_level"]
        ):
            return piece, pieces, parsed_label

    return None, None, parsed_label


def _has_sufficient_resources(budget, hack_cost, mats_cost):
    if budget.get("Hacksilver", 0) < hack_cost:
        return False

    return all(budget.get(mat, 0) >= qty for mat, qty in mats_cost.items())


def _apply_upgrade_to_inventory(web_data, slot, label):
    piece, _, parsed_label = _find_inventory_piece(web_data, slot, label)
    if piece is None or parsed_label is None:
        return False

    piece["level"] = parsed_label["to_level"]
    piece["craft"] = False
    return True


def create_app(test_config=None) -> Flask:
    app = Flask(__name__, template_folder=str(TEMPLATES_DIR))

    if test_config:
        app.config.update(test_config)

    @app.get("/")
    def index():
        target_stats = load_stat_preferences()
        data = _compute_all(target_stats=target_stats)
        data["stat_preferences"] = target_stats or []
        return render_template("index.html", **data)

    @app.route("/api/recalc", methods=["POST"])
    def api_recalc():
        """Accept a modified resource budget and optional target stats for multi-objective optimization."""
        payload = request.get_json(force=True)
        budget = payload.get("resource_budget")
        target_stats = payload.get("target_stats")
        web_data = load_web_inventory()
        if budget:
            web_data["resource_budget"] = coerce_resource_budget(budget)
        data = _compute_all(web_data=web_data, target_stats=target_stats)
        return jsonify(data)

    @app.route("/api/save-inventory", methods=["POST"])
    def api_save_inventory():
        """Persist modified resources and return recalculated data."""
        payload = request.get_json(force=True)
        web_data = load_web_inventory()
        web_data["resource_budget"] = coerce_resource_budget(
            payload.get("resource_budget", {})
        )
        save_web_inventory(web_data)
        data = _compute_all(web_data=web_data)
        return jsonify(data)

    @app.route("/api/apply-upgrade", methods=["POST"])
    def api_apply_upgrade():
        """Apply a step-by-step upgrade: deduct resources and update piece level."""
        payload = request.get_json(force=True)
        label = str(payload.get("label", ""))
        slot = str(payload.get("slot", ""))

        try:
            hack_cost = int(payload.get("hack", 0))
            mats_cost = {
                str(mat): int(qty) for mat, qty in payload.get("mats", {}).items()
            }
        except (AttributeError, TypeError, ValueError):
            return jsonify({"error": "Payload upgrade non valido."}), 400

        if hack_cost < 0 or any(qty < 0 for qty in mats_cost.values()):
            return jsonify(
                {"error": "I costi dell'upgrade devono essere non negativi."}
            ), 400

        web_data = load_web_inventory()
        budget = web_data.get("resource_budget", {})

        if not _apply_upgrade_to_inventory(web_data, slot, label):
            return jsonify(
                {"error": "Upgrade non valido o non presente in inventario."}
            ), 400

        if not _has_sufficient_resources(budget, hack_cost, mats_cost):
            return jsonify(
                {"error": "Risorse insufficienti per applicare l'upgrade."}
            ), 400

        budget["Hacksilver"] = budget.get("Hacksilver", 0) - hack_cost
        for mat, qty in mats_cost.items():
            budget[mat] = budget.get(mat, 0) - qty
        web_data["resource_budget"] = budget

        save_web_inventory(web_data)
        data = _compute_all(web_data=web_data)
        return jsonify(data)

    @app.route("/api/export-build", methods=["POST"])
    def api_export_build():
        """Export current build as JSON."""
        web_data = load_web_inventory()
        exported = export_build(web_data)
        return jsonify(exported)

    @app.route("/api/export-build-csv", methods=["GET"])
    def api_export_build_csv():
        """Export current build as CSV file."""
        web_data = load_web_inventory()
        csv_content = export_build_csv(web_data)
        return csv_content, 200, {"Content-Type": "text/csv", "Content-Disposition": "attachment; filename=build.csv"}

    @app.route("/api/import-build", methods=["POST"])
    def api_import_build():
        """Import an exported build."""
        payload = request.get_json(force=True)
        imported_data = import_build(payload)
        save_web_inventory(imported_data)
        data = _compute_all(web_data=imported_data)
        return jsonify(data)

    @app.route("/api/share-build", methods=["POST"])
    def api_share_build():
        """Generate shareable URL for current build."""
        web_data = load_web_inventory()
        # In production, use request.host_url
        base_url = request.host_url.rstrip("/")
        share_url = generate_shareable_url(base_url, web_data)
        return jsonify({"url": share_url})

    @app.route("/api/stat-preferences", methods=["POST"])
    def api_save_stat_preferences():
        """Save user's optimization stat preferences."""
        payload = request.get_json(force=True)
        target_stats = payload.get("target_stats")

        # Validate target_stats is None or a list of strings
        if target_stats is not None and not isinstance(target_stats, list):
            return jsonify({"error": "target_stats must be null or a list"}), 400

        save_stat_preferences(target_stats)

        # Recalculate with new preferences
        web_data = load_web_inventory()
        data = _compute_all(web_data=web_data, target_stats=target_stats)
        data["stat_preferences"] = target_stats or []
        return jsonify(data)

    @app.route("/api/build-slots", methods=["GET"])
    def api_list_build_slots():
        """List all saved build slots."""
        slots = load_build_slots()
        slot_list = list_build_slots(slots)
        return jsonify({"slots": slot_list})

    @app.route("/api/build-slots", methods=["POST"])
    def api_manage_build_slots():
        """Create, load, or delete a build slot."""
        payload = request.get_json(force=True)
        action = payload.get("action", "").lower()
        slot_name = payload.get("name", "")

        if not slot_name or not action:
            return jsonify({"error": "Missing action or slot name"}), 400

        slots = load_build_slots()

        try:
            if action == "create":
                web_data = load_web_inventory()
                slots = create_build_slot(slot_name, web_data, slots)
                save_build_slots(slots)
                return jsonify({"message": f"Slot '{slot_name}' created"})

            elif action == "load":
                loaded_data = load_build_slot(slot_name, slots)
                save_web_inventory(loaded_data)
                data = _compute_all(web_data=loaded_data)
                return jsonify(data)

            elif action == "delete":
                slots = delete_build_slot(slot_name, slots)
                save_build_slots(slots)
                return jsonify({"message": f"Slot '{slot_name}' deleted"})

            else:
                return jsonify({"error": f"Unknown action: {action}"}), 400

        except KeyError as e:
            return jsonify({"error": f"Build slot not found: {e}"}), 404
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    return app


app = create_app()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    app.run(debug=True, port=5000)


if __name__ == "__main__":
    main()
