from gow_optimizer.config import (
    build_web_inventory_seed,
    get_data_file_paths,
    load_config,
)
from gow_optimizer.paths import PROJECT_ROOT


def test_load_config_has_expected_top_level_keys():
    cfg = load_config()

    assert "resource_budget" in cfg
    assert "chest_pieces" in cfg
    assert "mat_aliases" in cfg


def test_data_paths_resolve_inside_repo():
    cfg = load_config()

    armor_csv, weapons_csv = get_data_file_paths(cfg)

    assert armor_csv.startswith(str(PROJECT_ROOT))
    assert weapons_csv.startswith(str(PROJECT_ROOT))


def test_web_inventory_seed_contains_runtime_sections():
    cfg = load_config()
    seed = build_web_inventory_seed(cfg)

    assert "resource_budget" in seed
    assert "chest_pieces" in seed
    assert "shield_attachments" in seed
