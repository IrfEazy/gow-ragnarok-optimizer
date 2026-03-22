"""God of War Ragnarök — Web UI (Flask)."""

import logging
import re
from collections import Counter

from flask import Flask, jsonify, render_template, request

from gow_optimizer.config import (
    PIECE_KEYS,
    SLOT_TO_KEY,
    coerce_resource_budget,
    get_data_file_paths,
    load_config,
    load_web_inventory,
    save_web_inventory,
)
from gow_optimizer.optimizer import (
    build_all_pareto,
    build_available_df,
    build_weapon_available_df,
    collect_current_build,
    get_available,
    normalize_mat,
    parse_inventory_from_config,
    solve_with_resources,
)
from gow_optimizer.paths import TEMPLATES_DIR
from gow_optimizer.scraper import STAT_COLS, load_or_scrape

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
    force_scrape = cfg.get("force_scrape", False)
    armor_csv, weapons_csv = get_data_file_paths(cfg)
    mat_aliases = cfg.get("mat_aliases", {})

    all_pieces_df, all_weapons_df = load_or_scrape(armor_csv, weapons_csv, force_scrape)

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


def _serialize_best_item(record):
    return {
        "name": record[ITEM_NAME_COL],
        "level": int(record[ITEM_LEVEL_COL]),
        "total": int(record[TOTAL_STATS_COL]),
        "stats": {
            stat: int(record.get(stat, 0))
            for stat in STAT_COLS
            if record.get(stat, 0) > 0
        },
    }


def _build_best_armor(armor_current):
    best_armor = {}
    armor_total = 0

    for armor_type in ARMOR_TYPES:
        candidates = [row for row in armor_current if row[PIECE_TYPE_COL] == armor_type]
        if not candidates:
            continue
        best = max(candidates, key=lambda row: row[TOTAL_STATS_COL])
        best_armor[armor_type] = _serialize_best_item(best)
        armor_total += best[TOTAL_STATS_COL]

    return best_armor, armor_total


def _build_best_weapons(weapon_current):
    best_weapons = {}
    weapon_total = 0

    for category in WEAPON_CATEGORIES:
        candidates = [row for row in weapon_current if row[CATEGORY_COL] == category]
        if not candidates:
            continue
        best = max(candidates, key=lambda row: row[TOTAL_STATS_COL])
        best_weapons[category] = _serialize_best_item(best)
        weapon_total += best[TOTAL_STATS_COL]

    return best_weapons, weapon_total


def _build_rankings(items, group_key, values):
    rankings = {}
    for value in values:
        grouped_items = sorted(
            [row for row in items if row[group_key] == value],
            key=lambda row: row[TOTAL_STATS_COL],
            reverse=True,
        )
        rankings[value] = [_serialize_best_item(row) for row in grouped_items]
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


def _build_step_plan(slot_pareto, resource_budget, mat_aliases, grand_total):
    remaining_slots = {slot: list(options) for slot, options in slot_pareto.items()}
    cur_stats = {slot: options[0][1] for slot, options in slot_pareto.items()}
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


def _compute_all(web_data=None):
    """Run the full pipeline. Uses web_inventory.yaml if no data given."""
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
    armor_current, weapon_current = collect_current_build(
        inventory,
        available_df,
        w_inventory,
        w_available_df,
    )

    best_armor, armor_total = _build_best_armor(armor_current)
    best_weapons, weapon_total = _build_best_weapons(weapon_current)
    grand_total = armor_total + weapon_total

    rankings_armor = _build_rankings(armor_current, PIECE_TYPE_COL, ARMOR_TYPES)
    rankings_weapons = _build_rankings(
        weapon_current,
        CATEGORY_COL,
        WEAPON_CATEGORIES,
    )

    craft_armor = [(n, l, pt) for n, l, pt, c in inventory if c]
    craft_weapons = [(n, l, cat) for n, l, cat, c in w_inventory if c]

    slot_pareto = build_all_pareto(
        inventory,
        w_inventory,
        all_pieces_df,
        all_weapons_df,
        resource_budget,
        mat_aliases,
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
    step_plan = _build_step_plan(slot_pareto, resource_budget, mat_aliases, grand_total)
    resources = _serialize_resources(resource_budget)

    return {
        "stat_cols": STAT_COLS,
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
        data = _compute_all()
        return render_template("index.html", **data)

    @app.route("/api/recalc", methods=["POST"])
    def api_recalc():
        """Accept a modified resource budget and return the recomputed data."""
        payload = request.get_json(force=True)
        budget = payload.get("resource_budget")
        web_data = load_web_inventory()
        if budget:
            web_data["resource_budget"] = coerce_resource_budget(budget)
        data = _compute_all(web_data=web_data)
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

    return app


app = create_app()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    app.run(debug=True, port=5000)


if __name__ == "__main__":
    main()
