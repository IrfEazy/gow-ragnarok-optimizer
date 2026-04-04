"""Test that inventory piece toggle state reflects YAML craft flag."""
import pytest
from gow_optimizer.web import _compute_all


def test_piece_toggle_state_reflects_craft_false():
    """When craft=False, piece should show owned=True (toggle ON)."""
    web_data = {
        'chest_pieces': [{'name': 'Cuirass of Zeus', 'level': 5, 'craft': False}],
        'wrist_pieces': [],
        'waist_pieces': [],
        'axe_attachments': [],
        'blades_attachments': [],
        'spear_attachments': [],
        'shield_attachments': [],
        'resource_budget': {'Hacksilver': 1000}
    }
    
    result = _compute_all(web_data=web_data, target_stats=None)
    all_pieces = result['all_pieces']['chest_pieces']
    
    piece = next(p for p in all_pieces if p['name'] == 'Cuirass of Zeus')
    assert piece['owned'] is True, "craft=False should render as owned=True"


def test_piece_toggle_state_reflects_craft_true():
    """When craft=True, piece should show owned=False (toggle OFF)."""
    web_data = {
        'chest_pieces': [{'name': 'Cuirass of Zeus', 'level': 3, 'craft': True}],
        'wrist_pieces': [],
        'waist_pieces': [],
        'axe_attachments': [],
        'blades_attachments': [],
        'spear_attachments': [],
        'shield_attachments': [],
        'resource_budget': {'Hacksilver': 1000}
    }
    
    result = _compute_all(web_data=web_data, target_stats=None)
    all_pieces = result['all_pieces']['chest_pieces']
    
    piece = next(p for p in all_pieces if p['name'] == 'Cuirass of Zeus')
    assert piece['owned'] is False, "craft=True should render as owned=False"


def test_piece_not_in_inventory_shows_unowned():
    """Pieces not in inventory should show owned=False."""
    web_data = {
        'chest_pieces': [],
        'wrist_pieces': [],
        'waist_pieces': [],
        'axe_attachments': [],
        'blades_attachments': [],
        'spear_attachments': [],
        'shield_attachments': [],
        'resource_budget': {'Hacksilver': 1000}
    }
    
    result = _compute_all(web_data=web_data, target_stats=None)
    all_pieces = result['all_pieces']['chest_pieces']
    
    # All pieces should show as not owned
    for piece in all_pieces:
        assert piece['owned'] is False, f"Piece {piece['name']} should be owned=False when not in inventory"


def test_mixed_craft_states_in_same_slot():
    """Same slot with mixed craft states should be distinguished correctly."""
    web_data = {
        'chest_pieces': [
            {'name': 'Cuirass of Zeus', 'level': 5, 'craft': False},
            {'name': 'Cuirass of Ares', 'level': 3, 'craft': True},
        ],
        'wrist_pieces': [],
        'waist_pieces': [],
        'axe_attachments': [],
        'blades_attachments': [],
        'spear_attachments': [],
        'shield_attachments': [],
        'resource_budget': {'Hacksilver': 1000}
    }

    result = _compute_all(web_data=web_data, target_stats=None)
    all_pieces = result['all_pieces']['chest_pieces']

    zeus = next(p for p in all_pieces if p['name'] == 'Cuirass of Zeus')
    ares = next(p for p in all_pieces if p['name'] == 'Cuirass of Ares')

    assert zeus['owned'] is True, "craft=False should be owned=True"
    assert ares['owned'] is False, "craft=True should be owned=False"
