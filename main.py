"""CLI entry point — runs the full optimizer report to stdout.

Usage:
    uv run python main.py
"""

import logging
import sys
import io

from gow_optimizer.paths import WEB_INVENTORY_PATH
from gow_optimizer.config import load_config, load_web_inventory, get_data_file_paths
from gow_optimizer.scraper import load_csvs
from gow_optimizer.optimizer import (
    parse_inventory_from_config,
    build_available_df,
    build_weapon_available_df,
    build_all_pareto,
    solve_with_resources,
    collect_current_build,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")

PIECE_KEYS = [
    "chest_pieces", "wrist_pieces", "waist_pieces",
    "axe_attachments", "blades_attachments", "spear_attachments",
    "shield_attachments",
]


def main():
    cfg = load_config()
    armor_csv, weapons_csv = get_data_file_paths(cfg)
    mat_aliases = cfg.get("mat_aliases", {})
    all_pieces_df, all_weapons_df = load_csvs(armor_csv, weapons_csv)

    # Use web_inventory if available, else fall back to config
    if WEB_INVENTORY_PATH.exists():
        web_data = load_web_inventory()
    else:
        web_data = cfg

    resource_budget = dict(web_data.get("resource_budget", {}))
    budget_hack = resource_budget.pop("Hacksilver", 0)

    cfg_like = {k: web_data.get(k, []) for k in PIECE_KEYS}
    inventory, w_inventory = parse_inventory_from_config(cfg_like)

    available_df = build_available_df(all_pieces_df, inventory)
    w_available_df = build_weapon_available_df(all_weapons_df, w_inventory)

    # Current build
    armor_current, weapon_current = collect_current_build(
        inventory, available_df, w_inventory, w_available_df,
    )

    print("=" * 60)
    print("  GOD OF WAR RAGNAROK - Build Optimizer Report")
    print("=" * 60)

    print("\n-- Build Attuale --")
    armor_total = sum(r["Total Stats"] for r in armor_current)
    weapon_total = sum(r["Total Stats"] for r in weapon_current)
    for r in armor_current:
        print(f"  {r['Slot']}: {r['Item Name']} Lv{r['Item Level']} ({r['Total Stats']} stats)")
    for r in weapon_current:
        print(f"  {r['Slot']}: {r['Item Name']} Lv{r['Item Level']} ({r['Total Stats']} stats)")
    print(f"\n  Armatura totale: {armor_total}")
    print(f"  Armi totale:     {weapon_total}")
    print(f"  GRAND TOTAL:     {armor_total + weapon_total}")

    # Pareto + solve
    slot_pareto = build_all_pareto(
        inventory, w_inventory, all_pieces_df, all_weapons_df,
        resource_budget, mat_aliases,
    )
    best_total, best_choices = solve_with_resources(
        slot_pareto, budget_hack, resource_budget, mat_aliases,
    )

    print("\n-- Piano Ottimo --")
    if not best_choices:
        print("  Nessun upgrade possibile con le risorse disponibili.")
    else:
        total_hack = 0
        for slot, (hack, score, label, mats) in sorted(best_choices.items()):
            if "nessuna azione" in label:
                continue
            total_hack += hack
            mat_str = ", ".join(f"{k}: {v}" for k, v in mats.items()) if mats else "-"
            print(f"  [{slot}] {label}")
            print(f"    Score: +{score}  |  Hacksilver: {hack:,}  |  Materiali: {mat_str}")
        print(f"\n  Score totale upgrade: +{best_total}")
        print(f"  Hacksilver richiesto: {total_hack:,}")

    print()


if __name__ == "__main__":
    main()
