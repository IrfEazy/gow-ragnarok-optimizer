"""Tests for features added in Phases 2-5: decompose_plan_to_steps,
compute_shopping_list, undo stack, ILP solver, stat weights, and caching."""

import math
from copy import deepcopy

import pandas as pd
import pytest

from gow_optimizer import optimizer, web


# ─── Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def simple_pieces_df():
    """Minimal armor DataFrame with 2 levels for one piece."""
    data = {
        "Piece Name": ["Helm A", "Helm A", "Helm A"],
        "Piece Type": ["Chest", "Chest", "Chest"],
        "Level": [1, 2, 3],
        "Total Stats": [10, 20, 35],
        "Strength": [5, 10, 18],
        "Defense": [5, 10, 17],
        "Runic": [0, 0, 0],
        "Vitality": [0, 0, 0],
        "Cooldown": [0, 0, 0],
        "Luck": [0, 0, 0],
        "Upgrade_Hacksilver": [0, 100, 200],
    }
    return pd.DataFrame(data)


@pytest.fixture
def simple_weapons_df():
    """Minimal weapon DataFrame."""
    data = {
        "Weapon Name": ["Axe Grip", "Axe Grip"],
        "Category": ["Leviathan Axe", "Leviathan Axe"],
        "Level": [1, 2],
        "Total Stats": [10, 22],
        "Strength": [5, 12],
        "Defense": [5, 10],
        "Runic": [0, 0],
        "Vitality": [0, 0],
        "Cooldown": [0, 0],
        "Luck": [0, 0],
        "Upgrade_Hacksilver": [0, 150],
    }
    return pd.DataFrame(data)


# ─── decompose_plan_to_steps ─────────────────────────────────────────────

def test_decompose_plan_splits_multi_level(simple_pieces_df, simple_weapons_df):
    """A 1->3 upgrade should decompose into 1->2 and 2->3 steps."""
    opt_actions = [
        {"label": "Helm A 1\u21923", "slot": "Armatura \u2014 Chest",
         "hack": 300, "mats": {}, "score": 35}
    ]
    result = optimizer.decompose_plan_to_steps(
        opt_actions, simple_pieces_df, simple_weapons_df, {}
    )
    steps = result[0]["steps"]
    assert len(steps) == 2
    assert steps[0]["from_level"] == 1
    assert steps[0]["to_level"] == 2
    assert steps[1]["from_level"] == 2
    assert steps[1]["to_level"] == 3


def test_decompose_single_level_returns_one_step(simple_pieces_df, simple_weapons_df):
    """A 2->3 upgrade should produce exactly one step."""
    opt_actions = [
        {"label": "Helm A 2\u21923", "slot": "Armatura \u2014 Chest",
         "hack": 200, "mats": {}, "score": 35}
    ]
    result = optimizer.decompose_plan_to_steps(
        opt_actions, simple_pieces_df, simple_weapons_df, {}
    )
    steps = result[0]["steps"]
    assert len(steps) == 1
    assert steps[0]["from_level"] == 2
    assert steps[0]["to_level"] == 3


# ─── compute_shopping_list ───────────────────────────────────────────────

def test_compute_shopping_list_sums_costs(simple_pieces_df, simple_weapons_df):
    """Shopping list aggregates costs to max level for all owned pieces."""
    inventory = [("Helm A", 1, "Chest", False)]
    w_inventory = []
    total_hack, total_mats = optimizer.compute_shopping_list(
        inventory, w_inventory, simple_pieces_df, simple_weapons_df, {}
    )
    # Levels 2 and 3 needed: 100 + 200 = 300 Hacksilver
    assert total_hack == 300


def test_compute_shopping_list_already_maxed(simple_pieces_df, simple_weapons_df):
    """Piece already at max level contributes zero cost."""
    inventory = [("Helm A", 3, "Chest", False)]
    w_inventory = []
    total_hack, total_mats = optimizer.compute_shopping_list(
        inventory, w_inventory, simple_pieces_df, simple_weapons_df, {}
    )
    assert total_hack == 0


# ─── make_score_fn with weights ──────────────────────────────────────────

def test_make_score_fn_weighted():
    """Weights should bias the scoring toward the heavier stat."""
    baseline = {"Strength": 10, "Defense": 10, "Runic": 0, "Vitality": 0, "Cooldown": 0, "Luck": 0}
    target = ["Strength", "Defense"]
    weights = {"Strength": 5, "Defense": 1}

    score_fn = optimizer.make_score_fn(target, baseline, weights=weights)

    # Piece A: Strength +10, Defense +0  (favored by weight)
    a = {"Strength": 20, "Defense": 10, "Runic": 0, "Vitality": 0, "Cooldown": 0, "Luck": 0}
    # Piece B: Strength +0, Defense +10
    b = {"Strength": 10, "Defense": 20, "Runic": 0, "Vitality": 0, "Cooldown": 0, "Luck": 0}

    score_a = score_fn(a)
    score_b = score_fn(b)
    assert score_a > score_b, "Higher-weighted stat gain should score higher"


def test_make_score_fn_equal_weights_matches_unweighted():
    """Equal weights should produce same result as no weights."""
    baseline = {"Strength": 10, "Defense": 10, "Runic": 0, "Vitality": 0, "Cooldown": 0, "Luck": 0}
    target = ["Strength", "Defense"]

    fn_no_weights = optimizer.make_score_fn(target, baseline)
    fn_equal_weights = optimizer.make_score_fn(target, baseline, weights={"Strength": 3, "Defense": 3})

    per_stat = {"Strength": 20, "Defense": 25, "Runic": 0, "Vitality": 0, "Cooldown": 0, "Luck": 0}
    assert abs(fn_no_weights(per_stat) - fn_equal_weights(per_stat)) < 0.001


# ─── ILP solver ──────────────────────────────────────────────────────────

def test_ilp_solver_picks_best_within_budget():
    """ILP solver should pick the best option per slot within budget."""
    slot_pareto = {
        "Slot A": [(100, 10, "A cheap", {}), (500, 50, "A expensive", {})],
        "Slot B": [(200, 20, "B cheap", {}), (600, 60, "B expensive", {})],
    }
    # Budget only allows cheap choices
    best_total, choices = optimizer.solve_with_resources(
        slot_pareto, 300, {}, {}
    )
    assert best_total == 30
    assert choices["Slot A"][2] == "A cheap"
    assert choices["Slot B"][2] == "B cheap"


def test_ilp_solver_respects_material_budget():
    """ILP solver should respect per-material constraints."""
    slot_pareto = {
        "Slot A": [
            (0, 50, "A uses ore", {"Ore": 3}),
            (0, 10, "A no ore", {}),
        ],
    }
    # Only 2 Ore available, option needing 3 is infeasible
    best_total, choices = optimizer.solve_with_resources(
        slot_pareto, 999999, {"Ore": 2}, {}
    )
    assert choices["Slot A"][2] == "A no ore"
    assert best_total == 10


def test_ilp_solver_empty_slots():
    """Empty slot dict should return -1."""
    best_total, choices = optimizer.solve_with_resources({}, 1000, {}, {})
    assert best_total == -1
    assert choices == {}


# ─── Undo stack (API tests) ─────────────────────────────────────────────

def _patch_for_undo(monkeypatch, state):
    """Patch web module for undo tests."""
    def load():
        return deepcopy(state)

    def save(data):
        state.clear()
        state.update(deepcopy(data))

    monkeypatch.setattr(web, "load_web_inventory", load)
    monkeypatch.setattr(web, "save_web_inventory", save)
    monkeypatch.setattr(web, "load_stat_preferences", lambda: None)
    monkeypatch.setattr(web, "load_stat_weights", lambda: {})


def test_undo_returns_error_when_stack_empty(monkeypatch):
    """Undo with empty stack should return 400."""
    state = {"resource_budget": {}}
    _patch_for_undo(monkeypatch, state)
    app = web.create_app()
    web._undo_stack.clear()
    with app.test_client() as c:
        resp = c.post("/api/undo-upgrade", content_type="application/json")
        assert resp.status_code == 400


def test_undo_restores_previous_state(monkeypatch):
    """After apply + undo, state should match original."""
    original_state = {
        "resource_budget": {"Hacksilver": 99999},
        "chest_pieces": [{"name": "Helm A", "level": 2, "craft": False}],
        "wrist_pieces": [], "waist_pieces": [],
        "axe_attachments": [], "blades_attachments": [],
        "spear_attachments": [], "shield_attachments": [],
    }
    state = deepcopy(original_state)
    _patch_for_undo(monkeypatch, state)
    app = web.create_app()
    web._undo_stack.clear()

    # Push a snapshot to the undo stack
    web._undo_stack.append(deepcopy(original_state))

    with app.test_client() as c:
        resp = c.post("/api/undo-upgrade", content_type="application/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("undo_available") is False


# ─── Caching ────────────────────────────────────────────────────────────

def test_compute_cache_returns_same_result(monkeypatch):
    """Two calls with same data should return identical results (cache hit)."""
    state = {
        "resource_budget": {"Hacksilver": 0},
        "chest_pieces": [], "wrist_pieces": [], "waist_pieces": [],
        "axe_attachments": [], "blades_attachments": [],
        "spear_attachments": [], "shield_attachments": [],
    }
    _patch_for_undo(monkeypatch, state)
    app = web.create_app()

    # Clear cache
    web._compute_cache["hash"] = None
    web._compute_cache["result"] = None

    with app.app_context():
        result1 = web._compute_all(web_data=deepcopy(state))
        result2 = web._compute_all(web_data=deepcopy(state))
        # Results should be equal (cache hit on second call)
        assert result1["grand_total"] == result2["grand_total"]
        assert web._compute_cache["hash"] is not None
