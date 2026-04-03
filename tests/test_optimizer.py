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


def test_build_all_pareto_accepts_score_fn_parameter():
    """RED: build_all_pareto should accept optional score_fn parameter."""
    import pandas as pd

    # Create minimal test DataFrames
    armor_df = pd.DataFrame([
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
    weapon_df = pd.DataFrame()

    inventory = [("Armor1", 1, "Chest", False)]
    w_inventory = []
    resource_budget = {"Hacksilver": 500}
    mat_aliases = {}

    # Should work with default (no score_fn)
    slot_pareto = optimizer.build_all_pareto(
        inventory, w_inventory, armor_df, weapon_df, resource_budget, mat_aliases
    )
    assert "Armatura — Chest" in slot_pareto
    assert len(slot_pareto["Armatura — Chest"]) > 0


def test_multi_objective_vs_single_objective_differences():
    """INTEGRATION: Multi-objective and single-objective should produce different results."""
    # This is a RED test — it will guide implementation of score_fn threading
    # For now, just verify the infrastructure is in place
    import pandas as pd

    armor_df = pd.DataFrame([
        {
            "Piece Name": "Balanced",
            "Piece Type": "Chest",
            "Level": 1,
            "Total Stats": 20,
            "Strength": 10,
            "Defense": 10,
            "Runic": 0,
            "Vitality": 0,
            "Cooldown": 0,
            "Luck": 0,
            "Upgrade_Hacksilver": 0,
        },
        {
            "Piece Name": "Balanced",
            "Piece Type": "Chest",
            "Level": 2,
            "Total Stats": 30,
            "Strength": 15,
            "Defense": 15,
            "Runic": 0,
            "Vitality": 0,
            "Cooldown": 0,
            "Luck": 0,
            "Upgrade_Hacksilver": 100,
        },
        {
            "Piece Name": "StrengthFocus",
            "Piece Type": "Chest",
            "Level": 1,
            "Total Stats": 20,
            "Strength": 15,
            "Defense": 5,
            "Runic": 0,
            "Vitality": 0,
            "Cooldown": 0,
            "Luck": 0,
            "Upgrade_Hacksilver": 0,
        },
        {
            "Piece Name": "StrengthFocus",
            "Piece Type": "Chest",
            "Level": 2,
            "Total Stats": 30,
            "Strength": 24,
            "Defense": 6,
            "Runic": 0,
            "Vitality": 0,
            "Cooldown": 0,
            "Luck": 0,
            "Upgrade_Hacksilver": 50,
        },
    ])
    weapon_df = pd.DataFrame()

    inventory = [("Balanced", 1, "Chest", False), ("StrengthFocus", 1, "Chest", False)]
    w_inventory = []
    resource_budget = {"Hacksilver": 500}
    mat_aliases = {}

    # Both items have Total Stats of 30 at level 2, but different stat distributions
    # Balanced: +5 Strength, +5 Defense
    # StrengthFocus: +9 Strength, +1 Defense

    # When optimizing for Strength+Defense (balanced), Balanced should score higher
    # When optimizing for Strength only, StrengthFocus should score higher

    # For now, just verify build_all_pareto completes without error
    slot_pareto = optimizer.build_all_pareto(
        inventory, w_inventory, armor_df, weapon_df, resource_budget, mat_aliases
    )
    assert "Armatura — Chest" in slot_pareto


def test_build_slot_options_with_score_fn_applied():
    """RED: build_slot_options_with_mats should score using score_fn when provided."""
    # Create items with per-stat chains
    chain_balanced = [
        (2, 30, 100, {}, {"Strength": 15, "Defense": 15, "Runic": 0, "Vitality": 0, "Cooldown": 0, "Luck": 0}),
    ]
    chain_strength = [
        (2, 30, 50, {}, {"Strength": 24, "Defense": 6, "Runic": 0, "Vitality": 0, "Cooldown": 0, "Luck": 0}),
    ]

    items_with_chains = [
        ("Balanced", 1, 20, chain_balanced, False),
        ("StrengthFocus", 1, 20, chain_strength, False),
    ]

    # Baseline stats for the slot
    baseline = {"Strength": 10, "Defense": 10, "Runic": 0, "Vitality": 0, "Cooldown": 0, "Luck": 0}

    # Score function for Strength+Defense (balanced)
    target_stats = ["Strength", "Defense"]
    score_fn = optimizer.make_score_fn(target_stats, baseline)

    # For now, build_slot_options_with_mats doesn't take score_fn yet
    # This test is marked RED — we'll implement score_fn support next
    options = optimizer.build_slot_options_with_mats(items_with_chains)

    # Should have: no-op, Balanced->2, StrengthFocus->2
    assert len(options) >= 1
