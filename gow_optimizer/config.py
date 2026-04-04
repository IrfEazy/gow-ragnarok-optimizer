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


def load_stat_preferences() -> list[str] | None:
    """Load saved optimization stat preferences. Returns None if not set."""
    cfg = load_config()
    prefs = cfg.get("optimization_stats")
    if prefs is None:
        return None
    # Ensure it's a list of strings
    if isinstance(prefs, list):
        return [str(s) for s in prefs]
    return None


def save_stat_preferences(target_stats: list[str] | None) -> None:
    """Persist optimization stat preferences to config.yaml."""
    cfg = load_config()
    if target_stats is None:
        cfg.pop("optimization_stats", None)
    else:
        cfg["optimization_stats"] = [str(s) for s in target_stats]
    save_yaml(CONFIG_PATH, cfg)


def load_stat_presets() -> dict[str, list[str] | None]:
    """Load all saved stat selection presets from config.yaml.

    Returns dict mapping preset name → list of stat names, or None to mean "all stats"
    (no explicit filtering for that preset).
    Example: {"Defensive": ["Defense", "Vitality"], "Aggressive": ["Strength", "Runic"], "All": None}
    Returns empty dict if no presets are defined or if the format is invalid.
    """
    cfg = load_config()
    presets = cfg.get("stat_presets", {})
    # Validate: presets should be dict of lists
    if not isinstance(presets, dict):
        return {}
    return {k: v for k, v in presets.items() if isinstance(v, list)}


def save_stat_presets(presets: dict[str, list[str]]) -> None:
    """Persist stat selection presets to config.yaml.

    Args:
        presets: Dict mapping preset name → list of stat names
    """
    cfg = load_config()
    cfg["stat_presets"] = deepcopy(presets)
    save_yaml(CONFIG_PATH, cfg)


def save_current_as_preset(preset_name: str, current_stats: list[str] | None) -> None:
    """Save current stat selection as a named preset.

    Args:
        preset_name: Name for the new preset (required, non-empty)
        current_stats: List of currently selected stats, or None to mean "all stats"
            (i.e., no explicit filtering is applied).

    Raises:
        ValueError: If preset_name is empty or invalid
    """
    if not preset_name or not isinstance(preset_name, str) or not preset_name.strip():
        raise ValueError("Preset name must be a non-empty string")

    preset_name = preset_name.strip()
    presets = load_stat_presets()
    # Preserve None so that callers can distinguish between:
    # - None: "all stats" (no filter)
    # - []: "no stats selected"
    presets[preset_name] = current_stats
    save_stat_presets(presets)


def delete_preset(preset_name: str) -> None:
    """Delete a named preset from config.yaml.

    Args:
        preset_name: Name of preset to delete

    Raises:
        KeyError: If preset does not exist
    """
    presets = load_stat_presets()
    if preset_name not in presets:
        raise KeyError(f"Preset '{preset_name}' not found")
    del presets[preset_name]
    save_stat_presets(presets)
