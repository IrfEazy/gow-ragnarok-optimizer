from gow_optimizer import config as config_module
from gow_optimizer.config import (
    coerce_resource_budget,
    get_data_file_paths,
    load_config,
    load_stat_preferences,
    save_stat_preferences,
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


def test_coerce_resource_budget_converts_valid_integers():
    """Should convert valid string/int values to integers."""
    raw_budget = {"Hacksilver": "100", "Petrified Bone": 50}
    result = coerce_resource_budget(raw_budget)

    assert result["Hacksilver"] == 100
    assert result["Petrified Bone"] == 50


def test_coerce_resource_budget_handles_invalid_values():
    """Should convert unparseable values to 0."""
    raw_budget = {"Hacksilver": "not_a_number", "Bone": None}
    result = coerce_resource_budget(raw_budget)

    assert result["Hacksilver"] == 0
    assert result["Bone"] == 0


def test_coerce_resource_budget_handles_none_input():
    """Should handle None input gracefully."""
    result = coerce_resource_budget(None)

    assert result == {}


def test_coerce_resource_budget_handles_empty_dict():
    """Should handle empty dict."""
    result = coerce_resource_budget({})

    assert result == {}


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


def test_load_stat_preferences_returns_none_when_not_set(tmp_path, monkeypatch):
    """Should return None when optimization_stats not in config."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text("resource_budget:\n  Hacksilver: 100\n", encoding="utf-8")

    monkeypatch.setattr(config_module, "CONFIG_PATH", config_path)

    result = load_stat_preferences()

    assert result is None


def test_load_stat_preferences_returns_list_when_set(tmp_path, monkeypatch):
    """Should return list when optimization_stats is set."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
resource_budget:
  Hacksilver: 100
optimization_stats:
  - Strength
  - Defense
""".strip()
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(config_module, "CONFIG_PATH", config_path)

    result = load_stat_preferences()

    assert result == ["Strength", "Defense"]


def test_load_stat_preferences_handles_non_list_value(tmp_path, monkeypatch):
    """Should return None when optimization_stats is not a list."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
resource_budget:
  Hacksilver: 100
optimization_stats: invalid_string
""".strip()
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(config_module, "CONFIG_PATH", config_path)

    result = load_stat_preferences()

    assert result is None


def test_save_stat_preferences_with_list(tmp_path, monkeypatch):
    """Should save list of stat preferences."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text("resource_budget:\n  Hacksilver: 100\n", encoding="utf-8")

    monkeypatch.setattr(config_module, "CONFIG_PATH", config_path)

    save_stat_preferences(["Strength", "Defense"])

    loaded = load_stat_preferences()
    assert loaded == ["Strength", "Defense"]


def test_save_stat_preferences_with_none(tmp_path, monkeypatch):
    """Should remove optimization_stats when saving None."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
resource_budget:
  Hacksilver: 100
optimization_stats:
  - Strength
""".strip()
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(config_module, "CONFIG_PATH", config_path)

    save_stat_preferences(None)

    result = load_stat_preferences()
    assert result is None
