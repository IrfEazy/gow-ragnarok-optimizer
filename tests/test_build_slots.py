"""Tests for multi-save build slots functionality."""

from copy import deepcopy

from gow_optimizer import web


def test_create_build_slot_saves_current_build():
    """RED: Should create a named save slot with current build."""
    build_data = {
        "resource_budget": {"Hacksilver": 5000},
        "chest_pieces": [{"name": "Lunda's Lost Cuirass", "level": 5, "craft": True}],
        "wrist_pieces": [],
        "waist_pieces": [],
        "axe_attachments": [],
        "blades_attachments": [],
        "spear_attachments": [],
        "shield_attachments": [],
    }

    slots = web.create_build_slot("Strength Build", build_data, {})

    assert "Strength Build" in slots
    assert slots["Strength Build"]["resource_budget"]["Hacksilver"] == 5000
    assert slots["Strength Build"]["chest_pieces"][0]["name"] == "Lunda's Lost Cuirass"


def test_list_build_slots_returns_all_saved_slots():
    """RED: Should list all saved build slots with metadata."""
    slots = {
        "Strength Build": {
            "resource_budget": {"Hacksilver": 5000},
            "chest_pieces": [],
            "wrist_pieces": [],
            "waist_pieces": [],
            "axe_attachments": [],
            "blades_attachments": [],
            "spear_attachments": [],
            "shield_attachments": [],
        },
        "Runic Build": {
            "resource_budget": {"Hacksilver": 3000},
            "chest_pieces": [],
            "wrist_pieces": [],
            "waist_pieces": [],
            "axe_attachments": [],
            "blades_attachments": [],
            "spear_attachments": [],
            "shield_attachments": [],
        },
    }

    result = web.list_build_slots(slots)

    assert len(result) == 2
    assert "Strength Build" in [s["name"] for s in result]
    assert "Runic Build" in [s["name"] for s in result]


def test_load_build_slot_restores_saved_build():
    """RED: Should load a named build slot and return its data."""
    slots = {
        "Strength Build": {
            "resource_budget": {"Hacksilver": 5000},
            "chest_pieces": [{"name": "Lunda's Lost Cuirass", "level": 5, "craft": True}],
            "wrist_pieces": [],
            "waist_pieces": [],
            "axe_attachments": [],
            "blades_attachments": [],
            "spear_attachments": [],
            "shield_attachments": [],
        },
    }

    result = web.load_build_slot("Strength Build", slots)

    assert result["resource_budget"]["Hacksilver"] == 5000
    assert result["chest_pieces"][0]["name"] == "Lunda's Lost Cuirass"


def test_delete_build_slot_removes_saved_slot():
    """RED: Should delete a named build slot."""
    slots = {
        "Strength Build": {"resource_budget": {}},
        "Runic Build": {"resource_budget": {}},
    }

    result = web.delete_build_slot("Strength Build", slots)

    assert "Strength Build" not in result
    assert "Runic Build" in result


def test_load_build_slot_raises_on_missing_slot():
    """RED: Should raise KeyError if slot doesn't exist."""
    slots = {"Strength Build": {"resource_budget": {}}}

    try:
        web.load_build_slot("Nonexistent Build", slots)
        assert False, "Should have raised KeyError"
    except KeyError:
        assert True
