"""Test that inventory piece toggle state reflects YAML craft flag."""

import pytest

from gow_optimizer.web import _compute_all

# --- Fixture: stub extract_all_pieces to avoid CSV dependency ---

_FAKE_ALL_PIECES = {
    "chest_pieces": [("Cuirass of Zeus", 1.0), ("Cuirass of Ares", 1.0)],
    "wrist_pieces": [],
    "waist_pieces": [],
    "axe_attachments": [],
    "blades_attachments": [],
    "spear_attachments": [],
    "shield_attachments": [],
}


@pytest.fixture(autouse=True)
def _stub_extract_all_pieces(monkeypatch):
    """Replace CSV-based extract_all_pieces with in-memory stub."""
    monkeypatch.setattr(
        "gow_optimizer.scraper.extract_all_pieces",
        lambda: _FAKE_ALL_PIECES,
    )


def test_piece_toggle_state_reflects_craft_false():
    """When craft=False, piece should show owned=True (toggle ON)."""
    web_data = {
        "chest_pieces": [
            {"name": "Cuirass of Zeus", "level": 5, "craft": False, "locked": False}
        ],
        "wrist_pieces": [],
        "waist_pieces": [],
        "axe_attachments": [],
        "blades_attachments": [],
        "spear_attachments": [],
        "shield_attachments": [],
        "resource_budget": {"Hacksilver": 1000},
    }

    result = _compute_all(web_data=web_data, target_stats=None)
    all_pieces = result["all_pieces"]["chest_pieces"]

    piece = next(p for p in all_pieces if p["name"] == "Cuirass of Zeus")
    assert piece["owned"] is True, "craft=False should render as owned=True"


def test_piece_toggle_state_reflects_craft_true():
    """When craft=True, piece should show owned=False (toggle OFF)."""
    web_data = {
        "chest_pieces": [
            {"name": "Cuirass of Zeus", "level": 3, "craft": True, "locked": False}
        ],
        "wrist_pieces": [],
        "waist_pieces": [],
        "axe_attachments": [],
        "blades_attachments": [],
        "spear_attachments": [],
        "shield_attachments": [],
        "resource_budget": {"Hacksilver": 1000},
    }

    result = _compute_all(web_data=web_data, target_stats=None)
    all_pieces = result["all_pieces"]["chest_pieces"]

    piece = next(p for p in all_pieces if p["name"] == "Cuirass of Zeus")
    assert piece["owned"] is False, "craft=True should render as owned=False"


def test_piece_not_in_inventory_shows_unowned():
    """Pieces not in inventory should show owned=False."""
    web_data = {
        "chest_pieces": [],
        "wrist_pieces": [],
        "waist_pieces": [],
        "axe_attachments": [],
        "blades_attachments": [],
        "spear_attachments": [],
        "shield_attachments": [],
        "resource_budget": {"Hacksilver": 1000},
    }

    result = _compute_all(web_data=web_data, target_stats=None)
    all_pieces = result["all_pieces"]["chest_pieces"]

    # All pieces should show as not owned
    for piece in all_pieces:
        assert piece["owned"] is False, (
            f"Piece {piece['name']} should be owned=False when not in inventory"
        )


def test_mixed_craft_states_in_same_slot():
    """Same slot with mixed craft states should be distinguished correctly."""
    web_data = {
        "chest_pieces": [
            {"name": "Cuirass of Zeus", "level": 5, "craft": False, "locked": False},
            {"name": "Cuirass of Ares", "level": 3, "craft": True, "locked": False},
        ],
        "wrist_pieces": [],
        "waist_pieces": [],
        "axe_attachments": [],
        "blades_attachments": [],
        "spear_attachments": [],
        "shield_attachments": [],
        "resource_budget": {"Hacksilver": 1000},
    }

    result = _compute_all(web_data=web_data, target_stats=None)
    all_pieces = result["all_pieces"]["chest_pieces"]

    zeus = next(p for p in all_pieces if p["name"] == "Cuirass of Zeus")
    ares = next(p for p in all_pieces if p["name"] == "Cuirass of Ares")

    assert zeus["owned"] is True, "craft=False should be owned=True"
    assert ares["owned"] is False, "craft=True should be owned=False"


def test_locked_piece_shows_locked_state():
    """When locked=true, piece should show locked=True in display data."""
    web_data = {
        "chest_pieces": [
            {"name": "Cuirass of Zeus", "level": 5, "craft": False, "locked": True}
        ],
        "wrist_pieces": [],
        "waist_pieces": [],
        "axe_attachments": [],
        "blades_attachments": [],
        "spear_attachments": [],
        "shield_attachments": [],
        "resource_budget": {"Hacksilver": 1000},
    }

    result = _compute_all(web_data=web_data, target_stats=None)
    all_pieces = result["all_pieces"]["chest_pieces"]

    piece = next(p for p in all_pieces if p["name"] == "Cuirass of Zeus")
    assert piece["locked"] is True, "locked=True should render as locked=True"
    assert piece["owned"] is False, "locked pieces should not be owned"


def test_locked_pieces_excluded_from_optimization():
    """Locked pieces should not be included in inventory for optimization."""
    from gow_optimizer.optimizer import parse_inventory_from_config

    cfg = {
        "chest_pieces": [
            {"name": "Cuirass of Zeus", "level": 5, "craft": False, "locked": False},
            {"name": "Cuirass of Ares", "level": 3, "craft": True, "locked": True},
        ],
        "wrist_pieces": [],
        "waist_pieces": [],
        "axe_attachments": [],
        "blades_attachments": [],
        "spear_attachments": [],
        "shield_attachments": [],
    }

    inventory, w_inventory = parse_inventory_from_config(cfg)

    # Only Zeus should be in inventory (not locked)
    piece_names = [p[0] for p in inventory]
    assert "Cuirass of Zeus" in piece_names, "Non-locked piece should be in inventory"
    assert "Cuirass of Ares" not in piece_names, (
        "Locked piece should not be in inventory"
    )
