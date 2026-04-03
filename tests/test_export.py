"""Tests for build export/import and sharing functionality."""

import json
from copy import deepcopy

from gow_optimizer import web


def test_export_build_as_json_returns_valid_structure():
    """RED: Test that export_build returns JSON-serializable dict with build data."""
    build_data = {
        "resource_budget": {"Hacksilver": 5000, "Forged Iron": 50},
        "chest_pieces": [{"name": "Lunda's Lost Cuirass", "level": 5, "craft": True}],
        "wrist_pieces": [{"name": "Sol's Wraps", "level": 4, "craft": False}],
        "waist_pieces": [],
        "axe_attachments": [],
        "blades_attachments": [],
        "spear_attachments": [],
        "shield_attachments": [],
    }

    result = web.export_build(build_data)

    # Should be JSON-serializable
    json_str = json.dumps(result)
    assert json_str

    # Should contain core sections
    assert "resource_budget" in result
    assert "armor" in result
    assert "weapons" in result
    assert result["resource_budget"]["Hacksilver"] == 5000


def test_export_build_includes_metadata():
    """RED: Export should include timestamp and version for sharing."""
    build_data = {
        "resource_budget": {"Hacksilver": 5000},
        "chest_pieces": [],
        "wrist_pieces": [],
        "waist_pieces": [],
        "axe_attachments": [],
        "blades_attachments": [],
        "spear_attachments": [],
        "shield_attachments": [],
    }

    result = web.export_build(build_data)

    assert "timestamp" in result
    assert "version" in result
    assert result["version"] == "0.1.0"


def test_import_build_restores_inventory():
    """RED: Import should restore exported build data to usable format."""
    exported = {
        "version": "0.1.0",
        "timestamp": "2026-04-03T12:00:00Z",
        "resource_budget": {"Hacksilver": 5000, "Forged Iron": 50},
        "armor": {
            "chest": [{"name": "Lunda's Lost Cuirass", "level": 5, "craft": True}],
        },
        "weapons": {
            "axe": [{"name": "Grip of the Fallen", "level": 3, "craft": False}],
        },
    }

    result = web.import_build(exported)

    assert result["resource_budget"]["Hacksilver"] == 5000
    assert result["chest_pieces"][0]["name"] == "Lunda's Lost Cuirass"
    assert result["axe_attachments"][0]["name"] == "Grip of the Fallen"


def test_export_build_as_csv():
    """RED: Should export armor and weapons to CSV format."""
    build_data = {
        "resource_budget": {"Hacksilver": 5000},
        "chest_pieces": [
            {"name": "Lunda's Lost Cuirass", "level": 5, "craft": True},
            {"name": "Spiritual Shoulder Straps", "level": 4, "craft": False},
        ],
        "wrist_pieces": [],
        "waist_pieces": [],
        "axe_attachments": [],
        "blades_attachments": [],
        "spear_attachments": [],
        "shield_attachments": [],
    }

    csv_str = web.export_build_csv(build_data)

    assert "Piece Type,Name,Level,Craft" in csv_str
    assert "Chest,Lunda's Lost Cuirass,5,Yes" in csv_str
    assert "Chest,Spiritual Shoulder Straps,4,No" in csv_str


def test_generate_shareable_url_encodes_build():
    """RED: Should generate URL-safe shareable link with encoded build."""
    build_data = {
        "resource_budget": {"Hacksilver": 5000},
        "chest_pieces": [{"name": "Test Armor", "level": 3, "craft": True}],
        "wrist_pieces": [],
        "waist_pieces": [],
        "axe_attachments": [],
        "blades_attachments": [],
        "spear_attachments": [],
        "shield_attachments": [],
    }

    share_url = web.generate_shareable_url("http://localhost:5000", build_data)

    assert "http://localhost:5000" in share_url
    assert "#build=" in share_url or "?build=" in share_url
    # URL should be reasonably short (URL-safe encoding)
    assert len(share_url) < 2000
