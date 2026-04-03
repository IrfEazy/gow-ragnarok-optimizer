"""Configuration and runtime inventory helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import yaml

from gow_optimizer.paths import CONFIG_PATH, resolve_project_path

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


def load_web_inventory() -> dict[str, Any]:
    """Load runtime inventory directly from config.yaml (single source of truth)."""
    data = load_config()
    data.setdefault("resource_budget", {})
    for key in PIECE_KEYS:
        data.setdefault(key, [])
    return data


def save_web_inventory(data: dict[str, Any]) -> None:
    """Persist runtime inventory changes into config.yaml.

    Only runtime sections are overwritten; static settings are preserved.
    """
    cfg = load_config()
    cfg["resource_budget"] = coerce_resource_budget(data.get("resource_budget", {}))
    for key in PIECE_KEYS:
        cfg[key] = deepcopy(data.get(key, []))
    save_yaml(CONFIG_PATH, cfg)
