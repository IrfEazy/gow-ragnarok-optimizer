"""Configuration and runtime inventory helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import yaml

from gow_optimizer.paths import CONFIG_PATH, WEB_INVENTORY_PATH, resolve_project_path

PIECE_KEYS = [
    "chest_pieces",
    "wrist_pieces",
    "waist_pieces",
    "axe_attachments",
    "blades_attachments",
    "spear_attachments",
    "shield_attachments",
]

SLOT_TO_KEY = {
    "Armatura — Chest": "chest_pieces",
    "Armatura — Wrist": "wrist_pieces",
    "Armatura — Waist": "waist_pieces",
    "Arma — Leviathan Axe": "axe_attachments",
    "Arma — Blades of Chaos": "blades_attachments",
    "Arma — Draupnir Spear": "spear_attachments",
    "Arma — Shield": "shield_attachments",
}


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def save_yaml(path, data: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as file:
        yaml.dump(
            data,
            file,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )


def get_data_file_paths(cfg: dict[str, Any]) -> tuple[str, str]:
    armor_csv = resolve_project_path(cfg.get("armor_csv", "data/all_pieces.csv"))
    weapons_csv = resolve_project_path(cfg.get("weapons_csv", "data/all_weapons.csv"))
    return str(armor_csv), str(weapons_csv)


def coerce_resource_budget(raw_budget: dict[str, Any] | None) -> dict[str, int]:
    budget: dict[str, int] = {}
    for key, value in (raw_budget or {}).items():
        try:
            budget[key] = int(value)
        except (TypeError, ValueError):
            budget[key] = 0
    return budget


def build_web_inventory_seed(cfg: dict[str, Any]) -> dict[str, Any]:
    data = {"resource_budget": coerce_resource_budget(cfg.get("resource_budget", {}))}
    for key in PIECE_KEYS:
        data[key] = deepcopy(cfg.get(key, []))
    return data


def load_web_inventory() -> dict[str, Any]:
    if not WEB_INVENTORY_PATH.exists():
        data = build_web_inventory_seed(load_config())
        save_web_inventory(data)
        return data

    with WEB_INVENTORY_PATH.open(encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    data.setdefault("resource_budget", {})
    for key in PIECE_KEYS:
        data.setdefault(key, [])
    return data


def save_web_inventory(data: dict[str, Any]) -> None:
    save_yaml(WEB_INVENTORY_PATH, data)
