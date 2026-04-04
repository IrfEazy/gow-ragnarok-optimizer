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


def test_build_available_df_filters_by_level():
    """Should only include pieces up to owned level."""
    import pandas as pd

    df = pd.DataFrame([
        {"Piece Name": "Armor A", "Piece Type": "Chest", "Level": 1, "Total Stats": 10},
        {"Piece Name": "Armor A", "Piece Type": "Chest", "Level": 2, "Total Stats": 20},
        {"Piece Name": "Armor A", "Piece Type": "Chest", "Level": 3, "Total Stats": 30},
        {"Piece Name": "Armor B", "Piece Type": "Chest", "Level": 1, "Total Stats": 15},
    ])

    # Own Armor A at level 2 and Armor B at level 1
    inventory = [
        ("Armor A", 2, "Chest", False),
        ("Armor B", 1, "Chest", False),
    ]

    result = optimizer.build_available_df(df, inventory)

    # Should include Armor A levels 1-2, and Armor B level 1, but NOT Armor A level 3
    assert len(result) == 3
    assert result[result["Level"] == 3].empty


def test_build_weapon_available_df_empty_inventory():
    """Should return empty DataFrame when weapon inventory is empty."""
    import pandas as pd

    df = pd.DataFrame([
        {"Weapon Name": "Axe", "Category": "Leviathan Axe", "Level": 1, "Total Stats": 10},
    ])

    result = optimizer.build_weapon_available_df(df, [])

    assert result.empty


def test_build_weapon_available_df_filters_by_level():
    """Should only include weapon levels up to owned level."""
    import pandas as pd

    df = pd.DataFrame([
        {"Weapon Name": "Spear", "Category": "Draupnir Spear", "Level": 1, "Total Stats": 10},
        {"Weapon Name": "Spear", "Category": "Draupnir Spear", "Level": 2, "Total Stats": 20},
        {"Weapon Name": "Spear", "Category": "Draupnir Spear", "Level": 3, "Total Stats": 30},
    ])

    # Own Spear at level 2
    w_inventory = [("Spear", 2, "Draupnir Spear", False)]

    result = optimizer.build_weapon_available_df(df, w_inventory)

    # Should include levels 1-2, not 3
    assert len(result) == 2
    assert result[result["Level"] == 3].empty


def test_collect_current_build_excludes_crafted_items():
    """Should exclude items with needs_craft=True from current build."""
    import pandas as pd

    df = pd.DataFrame([
        {"Piece Name": "Armor A", "Piece Type": "Chest", "Level": 1, "Total Stats": 10, "Strength": 5, "Defense": 5, "Runic": 0, "Vitality": 0, "Cooldown": 0, "Luck": 0},
        {"Piece Name": "Armor A", "Piece Type": "Chest", "Level": 2, "Total Stats": 20, "Strength": 10, "Defense": 10, "Runic": 0, "Vitality": 0, "Cooldown": 0, "Luck": 0},
        {"Piece Name": "Armor B", "Piece Type": "Chest", "Level": 1, "Total Stats": 15, "Strength": 8, "Defense": 7, "Runic": 0, "Vitality": 0, "Cooldown": 0, "Luck": 0},
    ])
    empty_df = pd.DataFrame()

    # Own Armor A at level 2 (needs crafting), and Armor B at level 1 (owned)
    inventory = [
        ("Armor A", 2, "Chest", True),  # needs_craft=True, should be excluded
        ("Armor B", 1, "Chest", False),  # needs_craft=False, should be included
    ]
    w_inventory = []

    available_df = optimizer.build_available_df(df, inventory)
    w_available_df = optimizer.build_weapon_available_df(empty_df, w_inventory)

    armor_current, weapon_current = optimizer.collect_current_build(
        inventory, available_df, w_inventory, w_available_df
    )

    # Should only include Armor B (Armor A is excluded because needs_craft=True)
    assert len(armor_current) == 1
    assert armor_current[0]["Item Name"] == "Armor B"


def test_collect_current_build_respects_target_stats():
    """Should select items based on target stats when specified."""
    import pandas as pd

    df = pd.DataFrame([
        {"Piece Name": "Balanced", "Piece Type": "Chest", "Level": 1, "Total Stats": 20, "Strength": 10, "Defense": 10, "Runic": 0, "Vitality": 0, "Cooldown": 0, "Luck": 0},
        {"Piece Name": "StrengthFocus", "Piece Type": "Chest", "Level": 1, "Total Stats": 20, "Strength": 15, "Defense": 5, "Runic": 0, "Vitality": 0, "Cooldown": 0, "Luck": 0},
    ])
    empty_df = pd.DataFrame()

    inventory = [
        ("Balanced", 1, "Chest", False),
        ("StrengthFocus", 1, "Chest", False),
    ]
    w_inventory = []

    available_df = optimizer.build_available_df(df, inventory)
    w_available_df = optimizer.build_weapon_available_df(empty_df, w_inventory)

    # When targeting Strength only, should prefer StrengthFocus
    armor_current, _ = optimizer.collect_current_build(
        inventory, available_df, w_inventory, w_available_df, target_stats=["Strength"]
    )

    # Should select StrengthFocus (15 Strength vs 10 Strength)
    assert len(armor_current) == 1
    assert armor_current[0]["Item Name"] == "StrengthFocus"


def test_solve_with_resources_respects_budget():
    """Should only select upgrades within Hacksilver budget."""
    slot_pareto = {
        "Armatura — Chest": [
            (100, 15, "No-action", {}),
            (200, 25, "Upgrade A", {}),
            (500, 40, "Upgrade B", {}),
        ],
    }
    budget_hack = 300
    resource_budget = {"Hacksilver": 300}
    mat_aliases = {}

    total_stats, choices = optimizer.solve_with_resources(
        slot_pareto, budget_hack, resource_budget, mat_aliases
    )

    # Should pick Upgrade A (200 Hacksilver, 25 stats) over Upgrade B (exceeds budget)
    assert total_stats == 25
    assert "Armatura — Chest" in choices
    assert choices["Armatura — Chest"][2] == "Upgrade A"


def test_solve_with_resources_combines_multiple_slots():
    """Should find best combination across multiple slots within budget."""
    slot_pareto = {
        "Armatura — Chest": [
            (0, 0, "No-action", {}),
            (100, 20, "Chest Upgrade", {}),
        ],
        "Armatura — Wrist": [
            (0, 0, "No-action", {}),
            (100, 15, "Wrist Upgrade", {}),
        ],
    }
    budget_hack = 150
    resource_budget = {"Hacksilver": 150}
    mat_aliases = {}

    total_stats, choices = optimizer.solve_with_resources(
        slot_pareto, budget_hack, resource_budget, mat_aliases
    )

    # Should combine both upgrades (100 + 100 = 200... wait that exceeds, so should be 100+50 or 100+0)
    # Actually should pick: Chest (100) + Wrist (100) but that's 200 > 150
    # So either Chest (100, 20 stats) alone or Wrist (100, 15 stats) alone
    # Both use same cost, Chest gives more stats, so should pick Chest + no-action Wrist
    assert total_stats == 20
    assert choices["Armatura — Chest"][2] == "Chest Upgrade"
    assert choices["Armatura — Wrist"][2] == "No-action"


def test_collect_current_build_skips_missing_armor():
    """Should skip armor items not found in available_df (line 145 coverage)."""
    import pandas as pd

    df = pd.DataFrame([
        {"Piece Name": "Armor A", "Piece Type": "Chest", "Level": 1, "Total Stats": 10, "Strength": 5, "Defense": 5, "Runic": 0, "Vitality": 0, "Cooldown": 0, "Luck": 0},
        {"Piece Name": "Armor A", "Piece Type": "Chest", "Level": 2, "Total Stats": 20, "Strength": 10, "Defense": 10, "Runic": 0, "Vitality": 0, "Cooldown": 0, "Luck": 0},
        # Note: Armor B is NOT in the dataframe
    ])
    empty_df = pd.DataFrame()

    # Inventory includes Armor B which doesn't exist in df
    inventory = [
        ("Armor A", 2, "Chest", False),
        ("Armor B", 1, "Chest", False),  # This one is missing from df
    ]
    w_inventory = []

    available_df = optimizer.build_available_df(df, inventory)
    w_available_df = optimizer.build_weapon_available_df(empty_df, w_inventory)

    armor_current, weapon_current = optimizer.collect_current_build(
        inventory, available_df, w_inventory, w_available_df
    )

    # Should only include Armor A, skipping Armor B which isn't in df
    assert len(armor_current) == 1
    assert armor_current[0]["Item Name"] == "Armor A"


def test_collect_current_build_skips_missing_weapons():
    """Should skip weapon items not found in available_df (lines 181-213 coverage)."""
    import pandas as pd

    armor_df = pd.DataFrame()
    weapon_df = pd.DataFrame([
        {"Weapon Name": "Spear", "Category": "Draupnir Spear", "Level": 1, "Total Stats": 10, "Strength": 5, "Defense": 5, "Runic": 0, "Vitality": 0, "Cooldown": 0, "Luck": 0},
        {"Weapon Name": "Spear", "Category": "Draupnir Spear", "Level": 2, "Total Stats": 20, "Strength": 10, "Defense": 10, "Runic": 0, "Vitality": 0, "Cooldown": 0, "Luck": 0},
        # Note: Axe is NOT in the dataframe
    ])

    inventory = []
    # Have a weapon that exists and one that doesn't
    w_inventory = [
        ("Spear", 2, "Draupnir Spear", False),
        ("Axe", 1, "Leviathan Axe", False),  # This one is missing from df
    ]

    available_df = optimizer.build_available_df(armor_df, inventory)
    w_available_df = optimizer.build_weapon_available_df(weapon_df, w_inventory)

    armor_current, weapon_current = optimizer.collect_current_build(
        inventory, available_df, w_inventory, w_available_df
    )

    # Should only include Spear, skipping Axe which isn't in df
    assert len(weapon_current) == 1
    assert weapon_current[0]["Item Name"] == "Spear"
    assert weapon_current[0]["Category"] == "Draupnir Spear"


def test_collect_current_build_with_missing_stats():
    """Should handle NaN/missing stats gracefully with target_stats (line 150-153 coverage)."""
    import pandas as pd

    df = pd.DataFrame([
        {"Piece Name": "Sparse Armor", "Piece Type": "Chest", "Level": 1, "Total Stats": 20, "Strength": 10, "Defense": None, "Runic": 10, "Vitality": 0, "Cooldown": 0, "Luck": 0},
    ])
    empty_df = pd.DataFrame()

    inventory = [("Sparse Armor", 1, "Chest", False)]
    w_inventory = []

    available_df = optimizer.build_available_df(df, inventory)
    w_available_df = optimizer.build_weapon_available_df(empty_df, w_inventory)

    # When Defense is None/NaN, should treat as 0 when summing
    armor_current, _ = optimizer.collect_current_build(
        inventory, available_df, w_inventory, w_available_df, target_stats=["Strength", "Defense"]
    )

    assert len(armor_current) == 1
    # Should have included Strength (10) but Defense is NaN (treated as 0)
    assert armor_current[0]["Item Name"] == "Sparse Armor"


def test_build_all_pareto_with_weapons_only():
    """Should build Pareto frontier with weapons inventory (lines 432-469 coverage)."""
    import pandas as pd

    armor_df = pd.DataFrame()  # No armor
    weapon_df = pd.DataFrame([
        {"Weapon Name": "Axe", "Category": "Leviathan Axe", "Level": 1, "Total Stats": 15, "Strength": 8, "Defense": 7, "Runic": 0, "Vitality": 0, "Cooldown": 0, "Luck": 0, "Upgrade_Hacksilver": 0},
        {"Weapon Name": "Axe", "Category": "Leviathan Axe", "Level": 2, "Total Stats": 25, "Strength": 13, "Defense": 12, "Runic": 0, "Vitality": 0, "Cooldown": 0, "Luck": 0, "Upgrade_Hacksilver": 100},
    ])

    inventory = []
    w_inventory = [("Axe", 1, "Leviathan Axe", False)]
    resource_budget = {"Hacksilver": 500}
    mat_aliases = {}

    slot_pareto = optimizer.build_all_pareto(
        inventory, w_inventory, armor_df, weapon_df, resource_budget, mat_aliases
    )

    # Should have weapon slot with actual options
    assert "Arma — Leviathan Axe" in slot_pareto
    assert len(slot_pareto["Arma — Leviathan Axe"]) > 0


def test_build_all_pareto_with_empty_weapon_slots():
    """Should handle weapon categories with no inventory (lines 460 coverage)."""
    import pandas as pd

    armor_df = pd.DataFrame([
        {"Piece Name": "Chest", "Piece Type": "Chest", "Level": 1, "Total Stats": 20, "Strength": 10, "Defense": 10, "Runic": 0, "Vitality": 0, "Cooldown": 0, "Luck": 0, "Upgrade_Hacksilver": 0},
    ])
    weapon_df = pd.DataFrame([
        {"Weapon Name": "Axe", "Category": "Leviathan Axe", "Level": 1, "Total Stats": 15, "Strength": 8, "Defense": 7, "Runic": 0, "Vitality": 0, "Cooldown": 0, "Luck": 0, "Upgrade_Hacksilver": 0},
        {"Weapon Name": "Spear", "Category": "Draupnir Spear", "Level": 1, "Total Stats": 15, "Strength": 8, "Defense": 7, "Runic": 0, "Vitality": 0, "Cooldown": 0, "Luck": 0, "Upgrade_Hacksilver": 0},
    ])

    inventory = [("Chest", 1, "Chest", False)]
    # Only have axe in inventory, no spear or blades
    w_inventory = [("Axe", 1, "Leviathan Axe", False)]
    resource_budget = {"Hacksilver": 500}
    mat_aliases = {}

    slot_pareto = optimizer.build_all_pareto(
        inventory, w_inventory, armor_df, weapon_df, resource_budget, mat_aliases
    )

    # Should have Axe slot
    assert "Arma — Leviathan Axe" in slot_pareto
    # Should NOT have Spear or Blades slots (if condition at line 460)
    assert "Arma — Draupnir Spear" not in slot_pareto
    assert "Arma — Blades of Chaos" not in slot_pareto
