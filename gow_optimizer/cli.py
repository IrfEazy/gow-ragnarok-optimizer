"""CLI entry point for the build optimizer."""

import logging

from gow_optimizer.config import get_data_file_paths, load_config
from gow_optimizer.optimizer import (
    build_all_pareto,
    build_available_df,
    build_weapon_available_df,
    collect_current_build,
    parse_inventory_from_config,
    print_blocked_slots,
    print_craft_warnings,
    print_current_build,
    print_optimal_plan,
    print_optimizer_report,
    print_slot_rankings,
    print_step_by_step,
)
from gow_optimizer.scraper import load_or_scrape

logger = logging.getLogger(__name__)


def main() -> None:
    cfg = load_config()

    force_scrape = cfg.get("force_scrape", False)
    armor_csv, weapons_csv = get_data_file_paths(cfg)
    resource_budget = cfg.get("resource_budget", {})
    mat_aliases = cfg.get("mat_aliases", {})

    inventory, w_inventory = parse_inventory_from_config(cfg)

    craft_a = sum(1 for *_, craft in inventory if craft)
    craft_w = sum(1 for *_, craft in w_inventory if craft)
    logger.info("Configurazione caricata.")
    logger.info(
        "  Armature: %d chest, %d wrist, %d waist",
        sum(1 for _, _, slot, _ in inventory if slot == "Chest"),
        sum(1 for _, _, slot, _ in inventory if slot == "Wrist"),
        sum(1 for _, _, slot, _ in inventory if slot == "Waist"),
    )
    logger.info(
        "  Armi: %d axe, %d blades, %d spear, %d shield",
        sum(1 for _, _, slot, _ in w_inventory if slot == "Leviathan Axe"),
        sum(1 for _, _, slot, _ in w_inventory if slot == "Blades of Chaos"),
        sum(1 for _, _, slot, _ in w_inventory if slot == "Draupnir Spear"),
        sum(1 for _, _, slot, _ in w_inventory if slot == "Shield"),
    )
    logger.info("  Da craftare: %d armature, %d armi", craft_a, craft_w)
    logger.info("  Hacksilver: %s", f"{resource_budget.get('Hacksilver', 0):,}")
    logger.info("  FORCE_SCRAPE: %s", force_scrape)

    all_pieces_df, all_weapons_df = load_or_scrape(armor_csv, weapons_csv, force_scrape)

    available_df = build_available_df(all_pieces_df, inventory)
    w_available_df = build_weapon_available_df(all_weapons_df, w_inventory)

    logger.info(
        "Armature in inventario: %d pezzi (%d da craftare), %d righe DB",
        len(inventory),
        craft_a,
        available_df.shape[0],
    )
    if w_inventory:
        logger.info(
            "Armi in inventario: %d attachment (%d da craftare), %d righe DB",
            len(w_inventory),
            craft_w,
            w_available_df.shape[0],
        )
    else:
        logger.info("Inventario armi vuoto.")

    armor_current, weapon_current = collect_current_build(
        inventory,
        available_df,
        w_inventory,
        w_available_df,
    )
    grand_total, _ = print_current_build(armor_current, weapon_current)
    print_craft_warnings(inventory, w_inventory)
    print_slot_rankings(armor_current, weapon_current)

    slot_pareto = build_all_pareto(
        inventory,
        w_inventory,
        all_pieces_df,
        all_weapons_df,
        resource_budget,
        mat_aliases,
    )

    print_optimizer_report(slot_pareto, grand_total, resource_budget, mat_aliases)
    print_optimal_plan(slot_pareto, grand_total, resource_budget, mat_aliases)
    print_blocked_slots(
        inventory,
        w_inventory,
        all_pieces_df,
        all_weapons_df,
        resource_budget,
        mat_aliases,
    )
    print_step_by_step(slot_pareto, grand_total, resource_budget, mat_aliases)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
