"""Tests for error handling and validation."""

import pytest

from gow_optimizer import web


class CSVNotFoundError(Exception):
    """Raised when required CSV files are not found."""

    pass


def test_validate_build_data_detects_missing_resource_budget():
    """RED: Should validate that resource_budget exists and has Hacksilver."""
    invalid_build = {
        "chest_pieces": [],
        "wrist_pieces": [],
        "waist_pieces": [],
        "axe_attachments": [],
        "blades_attachments": [],
        "spear_attachments": [],
        "shield_attachments": [],
        # Missing resource_budget
    }

    with pytest.raises(ValueError, match="resource_budget"):
        web.validate_build_data(invalid_build)


def test_validate_build_data_detects_missing_hacksilver():
    """RED: Should validate that Hacksilver key exists in resource_budget."""
    invalid_build = {
        "resource_budget": {"Forged Iron": 50},  # Missing Hacksilver
        "chest_pieces": [],
        "wrist_pieces": [],
        "waist_pieces": [],
        "axe_attachments": [],
        "blades_attachments": [],
        "spear_attachments": [],
        "shield_attachments": [],
    }

    with pytest.raises(ValueError, match="Hacksilver"):
        web.validate_build_data(invalid_build)


def test_validate_build_data_accepts_valid_build():
    """RED: Should accept valid build data without raising."""
    valid_build = {
        "resource_budget": {"Hacksilver": 5000},
        "chest_pieces": [],
        "wrist_pieces": [],
        "waist_pieces": [],
        "axe_attachments": [],
        "blades_attachments": [],
        "spear_attachments": [],
        "shield_attachments": [],
    }

    result = web.validate_build_data(valid_build)
    assert result is True


def test_validate_inventory_piece_detects_invalid_level():
    """RED: Should validate that piece level is between 1 and 9."""
    invalid_piece = {"name": "Test Armor", "level": 10, "craft": True}

    with pytest.raises(ValueError, match="level"):
        web.validate_inventory_piece(invalid_piece)


def test_validate_inventory_piece_accepts_valid_piece():
    """RED: Should accept valid piece with level 1-9."""
    valid_piece = {"name": "Test Armor", "level": 5, "craft": True}

    result = web.validate_inventory_piece(valid_piece)
    assert result is True


def test_validate_csv_data_integrity():
    """RED: Should detect missing required columns in CSV data."""
    invalid_csv_dict = {
        "Item Name": ["Test1", "Test2"],
        # Missing required 'Total Stats' column
        "Strength": [10, 20],
    }

    with pytest.raises(ValueError, match="Total Stats"):
        web.validate_csv_integrity(invalid_csv_dict)


def test_format_error_message_for_missing_materials():
    """RED: Should format helpful error messages for missing materials."""
    missing_mats = {"Forged Iron": 50, "Petrified Bone": 5}

    msg = web.format_missing_materials_error(missing_mats)

    assert "Forged Iron" in msg
    assert "50" in msg
    assert "Petrified Bone" in msg
    assert "5" in msg


def test_safe_resource_update_prevents_negative_values():
    """RED: Should prevent resource quantities from going negative."""
    resources = {"Hacksilver": 100, "Forged Iron": 10}
    deduction = {"Hacksilver": 200}  # Would go negative

    with pytest.raises(ValueError, match="insufficient"):
        web.safe_resource_update(resources, deduction)


def test_safe_resource_update_accepts_valid_deduction():
    """RED: Should accept valid resource deduction."""
    resources = {"Hacksilver": 100, "Forged Iron": 10}
    deduction = {"Hacksilver": 50}

    result = web.safe_resource_update(resources, deduction)

    assert result["Hacksilver"] == 50
    assert result["Forged Iron"] == 10
