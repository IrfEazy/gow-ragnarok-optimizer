from gow_optimizer import config as config_module
from gow_optimizer.config import (
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


def test_load_web_inventory_reads_from_config_yaml(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
force_scrape: false
resource_budget:
    Hacksilver: 999
chest_pieces:
    - { name: "Spiritual Shoulder Straps", level: 5, craft: false }
""".strip()
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(config_module, "CONFIG_PATH", config_path)

    data = config_module.load_web_inventory()

    assert data["resource_budget"]["Hacksilver"] == 999
    assert data["chest_pieces"][0]["level"] == 5
    assert data["chest_pieces"][0]["craft"] is False


def test_save_web_inventory_writes_runtime_sections_into_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
force_scrape: false
armor_csv: data/all_pieces.csv
resource_budget:
    Hacksilver: 10
chest_pieces: []
wrist_pieces: []
waist_pieces: []
axe_attachments: []
blades_attachments: []
spear_attachments: []
shield_attachments: []
""".strip()
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(config_module, "CONFIG_PATH", config_path)

    config_module.save_web_inventory(
        {
            "resource_budget": {"Hacksilver": 123},
            "chest_pieces": [
                {
                    "name": "Spiritual Shoulder Straps",
                    "level": 5,
                    "craft": False,
                }
            ],
            "wrist_pieces": [],
            "waist_pieces": [],
            "axe_attachments": [],
            "blades_attachments": [],
            "spear_attachments": [],
            "shield_attachments": [],
        }
    )

    saved = config_module.load_config()
    assert saved["force_scrape"] is False
    assert saved["armor_csv"] == "data/all_pieces.csv"
    assert saved["resource_budget"]["Hacksilver"] == 123
    assert saved["chest_pieces"][0]["level"] == 5
