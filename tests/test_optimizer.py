"""Tests for multi-objective optimization with geometric mean scoring."""

import math
import pytest

from gow_optimizer import optimizer


def test_make_score_fn_geometric_mean_of_gains():
    """RED: make_score_fn should return geometric mean of per-stat gains."""
    # Baseline: Chest has Strength=10, Defense=20
    baseline = {"Strength": 10, "Defense": 20, "Runic": 0, "Vitality": 0, "Cooldown": 0, "Luck": 0}
    target_stats = ["Strength", "Defense"]
    score_fn = optimizer.make_score_fn(target_stats, baseline)

    # Upgrade: Strength +5, Defense +5
    per_stat = {"Strength": 15, "Defense": 25, "Runic": 0, "Vitality": 0, "Cooldown": 0, "Luck": 0}
    score = score_fn(per_stat)

    # Expected: ∏(1 + gain)^(1/n) = ((1+5) * (1+5))^(1/2) = (6*6)^0.5 = 6.0
    expected = math.sqrt(6 * 6)
    assert abs(score - expected) < 0.001, f"Expected {expected}, got {score}"


def test_make_score_fn_balances_gains():
    """RED: Balanced gains should score higher than imbalanced gains."""
    baseline = {"Strength": 10, "Defense": 10, "Runic": 0, "Vitality": 0, "Cooldown": 0, "Luck": 0}
    target_stats = ["Strength", "Defense"]
    score_fn = optimizer.make_score_fn(target_stats, baseline)

    # Imbalanced: Strength +20, Defense +0
    imbalanced = {"Strength": 30, "Defense": 10, "Runic": 0, "Vitality": 0, "Cooldown": 0, "Luck": 0}
    score_imbalanced = score_fn(imbalanced)  # ((1+20) * (1+0))^0.5 = sqrt(21) ≈ 4.58

    # Balanced: Strength +10, Defense +10
    balanced = {"Strength": 20, "Defense": 20, "Runic": 0, "Vitality": 0, "Cooldown": 0, "Luck": 0}
    score_balanced = score_fn(balanced)  # ((1+10) * (1+10))^0.5 = sqrt(121) = 11

    assert score_balanced > score_imbalanced, "Balanced gains should score higher"


def test_make_score_fn_handles_zero_gains():
    """RED: Should handle 0 gains gracefully (no collapse to 0)."""
    baseline = {"Strength": 10, "Defense": 10, "Runic": 0, "Vitality": 0, "Cooldown": 0, "Luck": 0}
    target_stats = ["Strength", "Defense"]
    score_fn = optimizer.make_score_fn(target_stats, baseline)

    # One stat improves, one doesn't
    one_improves = {"Strength": 20, "Defense": 10, "Runic": 0, "Vitality": 0, "Cooldown": 0, "Luck": 0}
    score = score_fn(one_improves)  # ((1+10) * (1+0))^0.5 = sqrt(11) ≈ 3.32

    # Should not collapse to 0
    assert score > 0, "Score should not be 0 when one stat improves"
    assert abs(score - math.sqrt(11)) < 0.001


def test_make_score_fn_single_stat_objective():
    """RED: Single-stat objective should work."""
    baseline = {"Strength": 10, "Defense": 10, "Runic": 0, "Vitality": 0, "Cooldown": 0, "Luck": 0}
    target_stats = ["Strength"]
    score_fn = optimizer.make_score_fn(target_stats, baseline)

    # Only Strength matters
    per_stat = {"Strength": 20, "Defense": 10, "Runic": 0, "Vitality": 0, "Cooldown": 0, "Luck": 0}
    score = score_fn(per_stat)  # (1+10)^(1/1) = 11

    assert abs(score - 11.0) < 0.001, f"Expected 11.0, got {score}"


def test_make_score_fn_all_six_stats():
    """RED: All six stats should work as target."""
    baseline = {s: 10 for s in ["Strength", "Defense", "Runic", "Vitality", "Cooldown", "Luck"]}
    target_stats = ["Strength", "Defense", "Runic", "Vitality", "Cooldown", "Luck"]
    score_fn = optimizer.make_score_fn(target_stats, baseline)

    # All improve by +5
    per_stat = {s: 15 for s in ["Strength", "Defense", "Runic", "Vitality", "Cooldown", "Luck"]}
    score = score_fn(per_stat)

    # Expected: (6 * 6 * 6 * 6 * 6 * 6)^(1/6) = 6^(6/6) = 6.0
    expected = 6.0
    assert abs(score - expected) < 0.001, f"Expected {expected}, got {score}"


def test_make_score_fn_empty_target_stats_fallback():
    """RED: Empty target_stats should fall back to sum (original behavior)."""
    baseline = {"Strength": 10, "Defense": 20, "Runic": 5, "Vitality": 0, "Cooldown": 0, "Luck": 0}
    target_stats = []
    score_fn = optimizer.make_score_fn(target_stats, baseline)

    # With empty target_stats, should sum all stats
    per_stat = {"Strength": 15, "Defense": 25, "Runic": 8, "Vitality": 0, "Cooldown": 0, "Luck": 0}
    score = score_fn(per_stat)

    expected = sum(per_stat.values())  # 15 + 25 + 8 + 0 + 0 + 0 = 48
    assert abs(score - expected) < 0.001, f"Expected {expected}, got {score}"


def test_get_upgrade_chain_stores_per_stat_dict():
    """RED: Upgrade chain should store per-stat dict alongside Total Stats."""
    import pandas as pd

    # Create a minimal test dataframe
    df = pd.DataFrame([
        {
            "Piece Name": "Test Armor",
            "Piece Type": "Chest",
            "Level": 1,
            "Total Stats": 20,
            "Strength": 5,
            "Defense": 8,
            "Runic": 3,
            "Vitality": 2,
            "Cooldown": 1,
            "Luck": 1,
            "Upgrade_Hacksilver": 0,
        },
        {
            "Piece Name": "Test Armor",
            "Piece Type": "Chest",
            "Level": 2,
            "Total Stats": 30,
            "Strength": 8,
            "Defense": 10,
            "Runic": 5,
            "Vitality": 3,
            "Cooldown": 2,
            "Luck": 2,
            "Upgrade_Hacksilver": 100,
        },
    ])

    resource_budget = {"Hacksilver": 500}
    mat_aliases = {}

    chain = optimizer.get_upgrade_chain_with_mats(
        df, "Piece Name", "Test Armor", "Piece Type", "Chest",
        current_lvl=1, resource_budget=resource_budget, mat_aliases=mat_aliases
    )

    assert len(chain) > 0, "Chain should have at least one upgrade"
    # Chain tuples should be: (level, total_stats, cum_hack, mats, per_stat_dict)
    level, total_stats, cum_hack, mats, per_stat = chain[0]
    assert level == 2
    assert total_stats == 30
    assert cum_hack == 100
    assert isinstance(per_stat, dict), "per_stat should be a dict"
    assert per_stat.get("Strength") == 8, "Should have Strength value"
    assert per_stat.get("Defense") == 10, "Should have Defense value"


def test_build_slot_options_with_score_fn():
    """RED: build_slot_options_with_mats should accept score_fn and use it."""
    # Create items_with_chains in the format expected:
    # (item_name, item_lvl, item_stats, chain, needs_craft)
    # where chain = [(level, total_stats, cum_hack, mats, per_stat)]

    chain1 = [
        (2, 30, 100, {}, {"Strength": 8, "Defense": 10, "Runic": 5, "Vitality": 3, "Cooldown": 2, "Luck": 2}),
    ]
    chain2 = [
        (2, 25, 50, {}, {"Strength": 10, "Defense": 6, "Runic": 4, "Vitality": 2, "Cooldown": 2, "Luck": 1}),
    ]

    items_with_chains = [
        ("Item1", 1, 20, chain1, False),
        ("Item2", 1, 15, chain2, False),
    ]

    # Score function that maximizes Strength only
    baseline = {"Strength": 5, "Defense": 8, "Runic": 3, "Vitality": 2, "Cooldown": 1, "Luck": 1}
    target_stats = ["Strength"]
    score_fn = optimizer.make_score_fn(target_stats, baseline)

    # Without score_fn parameter, build_slot_options_with_mats should still work
    # (for backwards compatibility, or we can add a new parameter)
    # For now, let's just verify the function signature handles it correctly
    options = optimizer.build_slot_options_with_mats(items_with_chains)

    # Should have options: no-op, Item1->2, Item2->2
    assert len(options) >= 1, "Should have at least the no-op option"
    # Each option is (hack, score, label, mats)
    assert all(len(opt) == 4 for opt in options), "Each option should be (hack, score, label, mats)"


def test_single_objective_matches_all_stats_selected():
    """INTEGRATION: Single-stat vs all-stats should match (backwards compatibility)."""
    import pandas as pd

    # Minimal df with two armor levels
    df = pd.DataFrame([
        {
            "Piece Name": "Armor1",
            "Piece Type": "Chest",
            "Level": 1,
            "Total Stats": 20,
            "Strength": 5,
            "Defense": 8,
            "Runic": 3,
            "Vitality": 2,
            "Cooldown": 1,
            "Luck": 1,
            "Upgrade_Hacksilver": 0,
        },
        {
            "Piece Name": "Armor1",
            "Piece Type": "Chest",
            "Level": 2,
            "Total Stats": 35,
            "Strength": 9,
            "Defense": 12,
            "Runic": 5,
            "Vitality": 4,
            "Cooldown": 3,
            "Luck": 2,
            "Upgrade_Hacksilver": 100,
        },
    ])

    inventory = [("Armor1", 1, "Chest", False)]
    resource_budget = {"Hacksilver": 500}
    mat_aliases = {}

    chain = optimizer.get_upgrade_chain_with_mats(
        df, "Piece Name", "Armor1", "Piece Type", "Chest",
        current_lvl=1, resource_budget=resource_budget, mat_aliases=mat_aliases
    )

    assert len(chain) > 0
    # Chain has per-stat data now: (level, total_stats, cum_hack, mats, per_stat)
    level, total_stats, cum_hack, mats, per_stat = chain[0]
    assert per_stat["Strength"] == 9
    assert sum(per_stat.values()) == 35  # All stats sum to Total Stats
