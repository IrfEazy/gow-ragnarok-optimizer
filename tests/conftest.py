"""Pytest configuration for safe test execution."""

import pytest
from pathlib import Path
from gow_optimizer import config as config_module
from gow_optimizer.paths import PROJECT_ROOT


def _create_minimal_test_config(config_path: Path) -> None:
    """Create a minimal test config in the given path.

    Uses shared logic from config.py to ensure consistency with the real config.
    """
    from gow_optimizer.config import save_yaml

    test_config = {
        "force_scrape": False,
        "armor_csv": "data/all_pieces.csv",
        "weapons_csv": "data/all_weapons.csv",
        "mat_aliases": {
            "Smouldering Embers": "Smoldering Embers",
            "Petrified Bones": "Petrified Bone",
            "Whispering Slabs": "Whispering Slab",
            "Asgardian Ingots": "Asgardian Ingot",
            "Dwaren Steel": "Dwarven Steel",
            "s Broken Cuirass": "Lunda's Broken Cuirass",
            "s Broken Bracers": "Lunda's Broken Bracers",
            "s Broken Belt": "Lunda's Broken Belt",
        },
        "resource_budget": {"Hacksilver": 5000},
        "chest_pieces": [],
        "wrist_pieces": [],
        "waist_pieces": [],
        "axe_attachments": [],
        "blades_attachments": [],
        "spear_attachments": [],
        "shield_attachments": [],
        "optimization_stats": [],
        "stat_presets": {
            "Defensive": ["Defense", "Vitality"],
            "Aggressive": ["Strength", "Runic"],
            "Balanced": ["Strength", "Defense", "Runic", "Vitality"],
        },
    }
    save_yaml(config_path, test_config)


@pytest.fixture(autouse=True)
def protect_config_yaml(tmp_path, monkeypatch):
    """Automatically protect config.yaml in all tests by redirecting CONFIG_PATH.

    This autouse fixture ensures no test can accidentally modify the real config.yaml.
    Any test that needs to read/write YAML uses a temporary isolated config file.

    Centralizes config path resolution via monkeypatch to ensure all modules
    (even those with direct imports) use the test config.
    """
    # Create a minimal safe config in tmp_path
    config_path = tmp_path / "config.yaml"
    _create_minimal_test_config(config_path)

    # Patch CONFIG_PATH in both paths and config modules to ensure all imports
    # reference the test config, including direct imports like:
    # from gow_optimizer.paths import CONFIG_PATH
    from gow_optimizer import paths as paths_module

    monkeypatch.setattr(paths_module, "CONFIG_PATH", config_path)
    monkeypatch.setattr(config_module, "CONFIG_PATH", config_path)

    yield

    # After test completes, verify config.yaml remains unmodified.
    # Fail the test explicitly if the real config was deleted/corrupted.
    real_config = PROJECT_ROOT / "config.yaml"
    if not real_config.exists():
        raise AssertionError(
            f"Test fixture detected that real config.yaml was deleted or moved. "
            f"Expected at: {real_config}\n"
            f"This indicates a test either directly deleted config.yaml or "
            f"bypassed the fixture's CONFIG_PATH protection."
        )
