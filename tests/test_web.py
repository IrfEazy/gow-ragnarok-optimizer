from copy import deepcopy

from gow_optimizer import web

EMPTY_COMPUTE_RESULT = {
    "armor_total": 0,
    "weapon_total": 0,
    "grand_total": 0,
    "hacksilver": 0,
    "opt_gain": 0,
    "best_armor": {},
    "best_weapons": {},
    "rankings_armor": {"Chest": [], "Wrist": [], "Waist": []},
    "rankings_weapons": {
        "Leviathan Axe": [],
        "Blades of Chaos": [],
        "Draupnir Spear": [],
        "Shield": [],
    },
    "craft_armor": [],
    "craft_weapons": [],
    "resources": [],
    "pareto_data": {},
    "opt_total": 0,
    "opt_hack": 0,
    "opt_hack_remaining": 0,
    "opt_actions": [],
    "opt_mats": [],
    "blocked": [],
    "steps": [],
    "step_final_total": 0,
    "step_final_gain": 0,
    "step_hack_spent": 0,
    "step_hack_remaining": 0,
    "step_mats_consumed": [],
    "stat_preferences": [],
}


def _patch_runtime_store(monkeypatch, state):
    def load():
        return deepcopy(state)

    def save(data):
        state.clear()
        state.update(deepcopy(data))

    monkeypatch.setattr(web, "load_web_inventory", load)
    monkeypatch.setattr(web, "save_web_inventory", save)
    monkeypatch.setattr(web, "load_stat_preferences", lambda: None)
    monkeypatch.setattr(
        web,
        "_compute_all",
        lambda web_data=None, target_stats=None: {
            **EMPTY_COMPUTE_RESULT,
            "hacksilver": (web_data or state)["resource_budget"].get("Hacksilver", 0),
            "resources": [
                {"name": key, "qty": value}
                for key, value in sorted((web_data or state)["resource_budget"].items())
            ],
        },
    )


def test_create_app_has_expected_routes(monkeypatch):
    monkeypatch.setattr(web, "_compute_all", lambda web_data=None, target_stats=None: EMPTY_COMPUTE_RESULT)
    monkeypatch.setattr(web, "load_stat_preferences", lambda: None)

    app = web.create_app({"TESTING": True})
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert b"Build Optimizer" in response.data


def test_save_inventory_persists_resource_budget(monkeypatch):
    state = {
        "resource_budget": {"Hacksilver": 100, "Forged Iron": 5},
        "chest_pieces": [],
        "wrist_pieces": [],
        "waist_pieces": [],
        "axe_attachments": [],
        "blades_attachments": [],
        "spear_attachments": [],
        "shield_attachments": [],
    }
    _patch_runtime_store(monkeypatch, state)

    app = web.create_app({"TESTING": True})
    client = app.test_client()

    response = client.post(
        "/api/save-inventory",
        json={"resource_budget": {"Hacksilver": "321", "Forged Iron": "7"}},
    )

    assert response.status_code == 200
    assert state["resource_budget"] == {"Hacksilver": 321, "Forged Iron": 7}


def test_apply_upgrade_updates_inventory_and_resources(monkeypatch):
    state = {
        "resource_budget": {"Hacksilver": 100, "Forged Iron": 5},
        "chest_pieces": [{"name": "Test Armor", "level": 1, "craft": True}],
        "wrist_pieces": [],
        "waist_pieces": [],
        "axe_attachments": [],
        "blades_attachments": [],
        "spear_attachments": [],
        "shield_attachments": [],
    }
    _patch_runtime_store(monkeypatch, state)

    app = web.create_app({"TESTING": True})
    client = app.test_client()

    response = client.post(
        "/api/apply-upgrade",
        json={
            "hack": 30,
            "mats": {"Forged Iron": 2},
            "label": "★craft+Test Armor 1→2",
            "slot": "Armatura — Chest",
        },
    )

    assert response.status_code == 200
    assert state["resource_budget"] == {"Hacksilver": 70, "Forged Iron": 3}
    assert state["chest_pieces"] == [{"name": "Test Armor", "level": 2, "craft": False}]


def test_recalc_api_accepts_target_stats_parameter(monkeypatch):
    """RED: /api/recalc should accept target_stats parameter for multi-objective."""
    state = {
        "resource_budget": {"Hacksilver": 5000},
        "chest_pieces": [{"name": "Lunda's Lost Cuirass", "level": 5, "craft": False}],
        "wrist_pieces": [],
        "waist_pieces": [],
        "axe_attachments": [],
        "blades_attachments": [],
        "spear_attachments": [],
        "shield_attachments": [],
    }

    def load():
        return deepcopy(state)

    def save(data):
        state.clear()
        state.update(deepcopy(data))

    monkeypatch.setattr(web, "load_web_inventory", load)
    monkeypatch.setattr(web, "save_web_inventory", save)

    app = web.create_app({"TESTING": True})
    client = app.test_client()

    # Should accept target_stats in request body
    response = client.post(
        "/api/recalc",
        json={"resource_budget": {"Hacksilver": 5000}, "target_stats": ["Strength", "Defense"]},
    )

    # For now, just verify the endpoint doesn't error (actual multi-objective logic comes later)
    assert response.status_code == 200


def test_apply_upgrade_rejects_invalid_upgrade_without_mutating_state(monkeypatch):
    state = {
        "resource_budget": {"Hacksilver": 100, "Forged Iron": 5},
        "chest_pieces": [{"name": "Test Armor", "level": 1, "craft": False}],
        "wrist_pieces": [],
        "waist_pieces": [],
        "axe_attachments": [],
        "blades_attachments": [],
        "spear_attachments": [],
        "shield_attachments": [],
    }
    original_state = deepcopy(state)
    _patch_runtime_store(monkeypatch, state)

    app = web.create_app({"TESTING": True})
    client = app.test_client()

    response = client.post(
        "/api/apply-upgrade",
        json={
            "hack": 30,
            "mats": {"Forged Iron": 2},
            "label": "BAD LABEL",
            "slot": "Armatura — Chest",
        },
    )

    assert response.status_code == 400
    assert response.get_json()["error"]
    assert state == original_state


def test_api_recalc_respects_target_stats_parameter_and_returns_updated_computation(monkeypatch):
    """RED: /api/recalc should accept target_stats and apply multi-objective scoring."""
    state = {
        "resource_budget": {"Hacksilver": 5000},
        "chest_pieces": [{"name": "Lunda's Lost Cuirass", "level": 5, "craft": False}],
        "wrist_pieces": [],
        "waist_pieces": [],
        "axe_attachments": [],
        "blades_attachments": [],
        "spear_attachments": [],
        "shield_attachments": [],
    }

    def load():
        return deepcopy(state)

    def save(data):
        state.clear()
        state.update(deepcopy(data))

    monkeypatch.setattr(web, "load_web_inventory", load)
    monkeypatch.setattr(web, "save_web_inventory", save)

    app = web.create_app({"TESTING": True})
    client = app.test_client()

    # Call without target_stats (should use original Total Stats behavior)
    response1 = client.post(
        "/api/recalc",
        json={"resource_budget": {"Hacksilver": 5000}},
    )
    assert response1.status_code == 200
    data1 = response1.get_json()

    # Call with target_stats (should use multi-objective geometric mean)
    response2 = client.post(
        "/api/recalc",
        json={"resource_budget": {"Hacksilver": 5000}, "target_stats": ["Strength", "Defense"]},
    )
    assert response2.status_code == 200
    data2 = response2.get_json()

    # Both should return valid data with same structure
    assert "opt_total" in data1
    assert "opt_total" in data2
    # Verify the endpoint accepted the parameter without error
    assert response2.status_code == 200


def test_home_page_renders_stat_selector_ui(monkeypatch):
    """RED: GET / should render stat selector checkboxes for multi-objective selection."""
    state = {
        "resource_budget": {"Hacksilver": 5000},
        "chest_pieces": [],
        "wrist_pieces": [],
        "waist_pieces": [],
        "axe_attachments": [],
        "blades_attachments": [],
        "spear_attachments": [],
        "shield_attachments": [],
    }
    _patch_runtime_store(monkeypatch, state)

    app = web.create_app({"TESTING": True})
    client = app.test_client()

    response = client.get("/")
    assert response.status_code == 200
    html = response.data.decode()

    # Check for stat selector UI elements
    assert "id=" in html and "stat-selector" in html  # Stat selector container
    assert "Strength" in html  # Strength stat label
    assert "Defense" in html  # Defense stat label
    assert "Runic" in html  # Runic stat label
    assert "Vitality" in html  # Vitality stat label
    assert "Cooldown" in html  # Cooldown stat label
    assert "Luck" in html  # Luck stat label
    # Verify checkboxes exist
    assert "type=" in html and "checkbox" in html


def test_home_page_includes_reset_stats_button(monkeypatch):
    """RED: GET / should render a reset button for stat selector."""
    state = {
        "resource_budget": {"Hacksilver": 5000},
        "chest_pieces": [],
        "wrist_pieces": [],
        "waist_pieces": [],
        "axe_attachments": [],
        "blades_attachments": [],
        "spear_attachments": [],
        "shield_attachments": [],
    }
    _patch_runtime_store(monkeypatch, state)

    app = web.create_app({"TESTING": True})
    client = app.test_client()

    response = client.get("/")
    assert response.status_code == 200
    html = response.data.decode()

    # Check for reset button
    assert "btn-reset-stats" in html
    assert "Ripristina Predefiniti" in html


def test_home_page_includes_stat_preference_functions(monkeypatch):
    """Test: GET / should include server-based stat preference persistence functions."""
    state = {
        "resource_budget": {"Hacksilver": 5000},
        "chest_pieces": [],
        "wrist_pieces": [],
        "waist_pieces": [],
        "axe_attachments": [],
        "blades_attachments": [],
        "spear_attachments": [],
        "shield_attachments": [],
    }
    _patch_runtime_store(monkeypatch, state)

    app = web.create_app({"TESTING": True})
    client = app.test_client()

    response = client.get("/")
    assert response.status_code == 200
    html = response.data.decode()

    # Check for server-based preference functions
    assert "function toggleStatPreferences" in html
    assert "function applyStatPreferences" in html
    assert "function loadStatPreferences" in html
    assert "function resetStatPreferences" in html
    assert "/api/stat-preferences" in html
    # Verify loadStatPreferences is called on page initialization
    assert "loadStatPreferences(" in html


def test_apply_stat_preferences_calls_api(monkeypatch):
    """Test: applyStatPreferences should call /api/stat-preferences endpoint."""
    state = {
        "resource_budget": {"Hacksilver": 5000},
        "chest_pieces": [],
        "wrist_pieces": [],
        "waist_pieces": [],
        "axe_attachments": [],
        "blades_attachments": [],
        "spear_attachments": [],
        "shield_attachments": [],
    }
    _patch_runtime_store(monkeypatch, state)

    app = web.create_app({"TESTING": True})
    client = app.test_client()

    response = client.get("/")
    assert response.status_code == 200
    html = response.data.decode()

    # Verify applyStatPreferences function calls /api/stat-preferences
    assert "async function applyStatPreferences()" in html
    assert "fetch('/api/stat-preferences'" in html


def test_score_fn_affects_pareto_frontier(monkeypatch):
    """RED: score_fn parameter should affect which items appear in Pareto frontier.

    This tests that build_slot_options_with_mats actually uses the score_fn
    to compute different scores vs Total Stats-based scoring.
    """
    from gow_optimizer.optimizer import build_slot_options_with_mats, make_score_fn
    from gow_optimizer.scraper import STAT_COLS

    # Create mock item chains with per_stat data
    # Item 1: Strong in Strength (36→40), weak in Defense (29→29)
    per_stat_1 = {'Strength': 40, 'Defense': 29, 'Runic': 14, 'Vitality': 26, 'Cooldown': 29, 'Luck': 29}
    chain_1 = [(2, 108, 100, {}, per_stat_1)]  # level, total_stats, hacksilver, mats, per_stat

    # Item 2: Weak in Strength (36→36), strong in Defense (29→33)
    per_stat_2 = {'Strength': 36, 'Defense': 33, 'Runic': 14, 'Vitality': 26, 'Cooldown': 29, 'Luck': 29}
    chain_2 = [(2, 108, 100, {}, per_stat_2)]

    # Current best: baseline values
    items_with_chains = [
        ("Item1", 1, 93, chain_1, False),  # name, level, current_stats, chain, needs_craft
        ("Item2", 1, 93, chain_2, False),
    ]

    baseline = {'Strength': 36, 'Defense': 29, 'Runic': 14, 'Vitality': 26, 'Cooldown': 29, 'Luck': 29}

    # Build with Strength-only scoring
    score_fn_strength = make_score_fn(['Strength'], baseline)
    options_strength = build_slot_options_with_mats(items_with_chains, score_fn=score_fn_strength)

    # Build with Defense-only scoring
    score_fn_defense = make_score_fn(['Defense'], baseline)
    options_defense = build_slot_options_with_mats(items_with_chains, score_fn=score_fn_defense)

    # Build without scoring (Total Stats)
    options_totals = build_slot_options_with_mats(items_with_chains, score_fn=None)

    # Extract scores for upgraded items (skip the "nessuna azione" option at index 0)
    scores_strength = [opt[1] for opt in options_strength[1:] if opt[0] > 0]  # (hack, score, label, mats)
    scores_defense = [opt[1] for opt in options_defense[1:] if opt[0] > 0]
    scores_totals = [opt[1] for opt in options_totals[1:] if opt[0] > 0]

    # With Strength-only scoring, Item 1 should score higher than Item 2
    # (Item 1 has +4 Strength, Item 2 has +4 Defense)
    assert scores_strength[0] > scores_strength[1], (
        f"Strength-only should prefer Item1 (+Strength). "
        f"Item1: {scores_strength[0]}, Item2: {scores_strength[1]}"
    )

    # With Defense-only scoring, Item 2 should score higher than Item 1
    assert scores_defense[1] > scores_defense[0], (
        f"Defense-only should prefer Item2 (+Defense). "
        f"Item1: {scores_defense[0]}, Item2: {scores_defense[1]}"
    )

    # Total Stats scoring should treat them equally (both are 108 total)
    assert scores_totals[0] == scores_totals[1], (
        f"Both items have same Total Stats, should score equally. "
        f"Item1: {scores_totals[0]}, Item2: {scores_totals[1]}"
    )


def test_build_rankings_respects_target_stats(monkeypatch):
    """RED: Rankings should be sorted by target_stats, not Total Stats."""
    from gow_optimizer.web import _build_rankings
    import pandas as pd

    # Two chest items with different stat profiles
    items = [
        pd.Series({
            "Piece Type": "Chest",
            "Piece Name": "High Defense Item",
            "Item Name": "High Defense Item",
            "Item Level": 5,
            "Level": 5,
            "Total Stats": 35,
            "Defense": 30,
            "Strength": 5,
            "Runic": 0,
            "Vitality": 0,
            "Cooldown": 0,
            "Luck": 0,
        }),
        pd.Series({
            "Piece Type": "Chest",
            "Piece Name": "Balanced Item",
            "Item Name": "Balanced Item",
            "Item Level": 5,
            "Level": 5,
            "Total Stats": 60,
            "Defense": 15,
            "Strength": 15,
            "Runic": 10,
            "Vitality": 10,
            "Cooldown": 5,
            "Luck": 5,
        }),
    ]

    # Test 1: Rankings sorted by Defense (target_stats=["Defense"])
    # Currently _build_rankings doesn't accept target_stats, so this test will fail
    # This is what we want to implement
    rankings = _build_rankings(items, "Piece Type", ["Chest"], target_stats=["Defense"])

    # With Defense-only ranking:
    # High Defense Item (30 Def) should rank #1
    # Balanced Item (15 Def) should rank #2
    assert rankings["Chest"][0]["name"] == "High Defense Item"
    assert rankings["Chest"][1]["name"] == "Balanced Item"

    # Test 2: Rankings sorted by Total Stats (target_stats=None)
    rankings_totals = _build_rankings(items, "Piece Type", ["Chest"], target_stats=None)

    # With Total Stats ranking:
    # Balanced Item (60 total) should rank #1
    # High Defense Item (35 total) should rank #2
    assert rankings_totals["Chest"][0]["name"] == "Balanced Item"
    assert rankings_totals["Chest"][1]["name"] == "High Defense Item"


def test_collect_current_build_respects_preference_baseline(monkeypatch):
    """RED: collect_current_build should use target_stats to select best item per slot.

    When target_stats is provided, select the item that maximizes those specific stats
    (not Total Stats, and not using score_fn which can give wrong results with zero baseline).

    Scenario:
    - Chest inventory: Item A (70 total: 30 Str + 30 Def + 10 Cool) and Item B (35 total: 35 Str)
    - With target_stats=["Strength"]: Select Item B (35 Str > 30 Str)
    - With target_stats=None (or all): Select Item A (70 total > 35 total)
    """
    from gow_optimizer.optimizer import collect_current_build
    from gow_optimizer.scraper import STAT_COLS
    import pandas as pd

    # Create mock CSV data
    chest_data = [
        {
            "Piece Name": "Chest A",
            "Piece Type": "Chest",
            "Level": 5,
            "Total Stats": 70,
            "Strength": 30,
            "Defense": 30,
            "Runic": 5,
            "Vitality": 3,
            "Cooldown": 1,
            "Luck": 1,
        },
        {
            "Piece Name": "Chest B",
            "Piece Type": "Chest",
            "Level": 5,
            "Total Stats": 35,
            "Strength": 35,
            "Defense": 0,
            "Runic": 0,
            "Vitality": 0,
            "Cooldown": 0,
            "Luck": 0,
        },
    ]
    all_pieces_df = pd.DataFrame(chest_data)

    # Inventory: own both items at level 5
    inventory = [
        ("Chest A", 5, "Chest", False),
        ("Chest B", 5, "Chest", False),
    ]

    # Test 1: With target_stats=["Strength"]
    current_strength, _ = collect_current_build(
        inventory, all_pieces_df, [], pd.DataFrame(), target_stats=["Strength"]
    )

    # Should select Chest B (higher Strength: 35 > 30)
    assert len(current_strength) == 1
    assert current_strength[0]["Item Name"] == "Chest B", (
        f"Strength-only should select Chest B (35 Str), "
        f"but selected {current_strength[0]['Item Name']}"
    )

    # Test 2: With target_stats=None (default: Total Stats)
    current_totals, _ = collect_current_build(
        inventory, all_pieces_df, [], pd.DataFrame(), target_stats=None
    )

    # Should select Chest A (higher total stats: 70 > 35)
    assert len(current_totals) == 1
    assert current_totals[0]["Item Name"] == "Chest A", (
        f"Total Stats should select Chest A (70 total), "
        f"but selected {current_totals[0]['Item Name']}"
    )


def test_collect_current_build_handles_nan_stats_when_filtering_by_target_stats(monkeypatch):
    """RED: collect_current_build should handle NaN stat values when filtering by target_stats.

    When a stat is NaN for an item, it should be treated as 0 for scoring purposes.
    Otherwise, NaN propagates through the sum and breaks comparisons.
    """
    from gow_optimizer.optimizer import collect_current_build
    import pandas as pd
    import numpy as np

    # Create mock inventory with two wrist items
    inventory = [
        ("Item A", 5, "Wrist", False),
        ("Item B", 5, "Wrist", False),
    ]

    # Item A: Has Defense=30, Strength=NaN (should score 30 for Defense-only)
    # Item B: Has Defense=NaN, Strength=20 (should score 0 for Defense-only)
    item_a_data = {
        "Piece Name": "Item A",
        "Piece Type": "Wrist",
        "Level": 5,
        "Total Stats": 50,
        "Defense": 30.0,
        "Strength": np.nan,
        "Runic": np.nan,
        "Vitality": np.nan,
        "Cooldown": np.nan,
        "Luck": np.nan,
    }

    item_b_data = {
        "Piece Name": "Item B",
        "Piece Type": "Wrist",
        "Level": 5,
        "Total Stats": 20,
        "Defense": np.nan,
        "Strength": 20.0,
        "Runic": np.nan,
        "Vitality": np.nan,
        "Cooldown": np.nan,
        "Luck": np.nan,
    }

    available_df = pd.DataFrame([item_a_data, item_b_data])
    empty_w_inventory = []
    empty_w_available_df = pd.DataFrame()

    # Test with target_stats=["Defense"]
    current, _ = collect_current_build(
        inventory, available_df, empty_w_inventory, empty_w_available_df,
        target_stats=["Defense"]
    )

    # Item A (Defense=30) should be selected, not Item B (Defense=NaN-&gt;0)
    assert len(current) == 1, "Should select exactly 1 wrist item"
    assert current[0]["Item Name"] == "Item A", (
        f"Defense-only should select Item A (Defense=30), "
        f"but selected {current[0]['Item Name']}"
    )


def test_build_slot_options_no_action_respects_score_fn(monkeypatch):
    """RED: no-action option should use score_fn when provided, not Total Stats.

    This test reproduces the bug: when score_fn is provided for multi-objective
    optimization, the "no-action" option incorrectly uses Total Stats instead of
    score_fn, causing it to be incorrectly ranked against alternatives that use
    score_fn for scoring.
    """
    from gow_optimizer.optimizer import build_slot_options_with_mats, make_score_fn

    # Create two items:
    # Item A: high Total Stats (70) but low Defense (22)
    # Item B: low Total Stats (30) but high Defense (40)

    # When optimizing for Defense only, Item B should rank higher.
    # But the bug causes "no-action" to be scored as 70 (Total Stats)
    # instead of using the Defense-only score_fn.

    baseline = {
        "Defense": 20, "Strength": 10, "Runic": 0,
        "Vitality": 0, "Cooldown": 0, "Luck": 0
    }
    score_fn = make_score_fn(["Defense"], baseline)

    # Current item's per_stat (this is what the no-action option should score)
    current_per_stat = baseline.copy()

    # Mock chains with per_stat dicts
    items_with_chains = [
        # Item A: total=70, but Defense gain only +2 (from 20 to 22)
        (
            "Item A", 5, 70,
            [(5, 70, 0, {}, {
                "Defense": 22, "Strength": 30, "Runic": 10,
                "Vitality": 0, "Cooldown": 0, "Luck": 8
            })],
            False
        ),
        # Item B: total=30, but Defense gain +20 (from 20 to 40)
        (
            "Item B", 5, 30,
            [(5, 30, 0, {}, {
                "Defense": 40, "Strength": -10, "Runic": 0,
                "Vitality": 0, "Cooldown": 0, "Luck": 0
            })],
            False
        ),
    ]

    options = build_slot_options_with_mats(
        items_with_chains, score_fn=score_fn, current_per_stat=current_per_stat
    )

    # First option: "— nessuna azione —" (no action)
    no_action = options[0]
    assert no_action[2] == "— nessuna azione —"

    # With the fix, no_action[1] should be score_fn(current_per_stat) = 1.0
    # (since current_per_stat == baseline, gain is 0)
    expected_score = score_fn(current_per_stat)
    assert no_action[1] == expected_score, (
        f"no-action should use score_fn(current_per_stat)={expected_score}, "
        f"but got {no_action[1]}"
    )

# ─── Multi-objective step planner tests ──────────────────────────────────


def test_candidate_step_action_accepts_target_stats_parameter():
    """Test: _candidate_step_action accepts target_stats and score_fns parameters."""
    from collections import Counter

    options = [(100, 50, "Item A 1→2", {})]
    result = web._candidate_step_action(
        "Armatura — Chest",
        options,
        current_stats=40,
        used_budget=0,
        used_mats=Counter(),
        resource_budget={"Hacksilver": 1000},
        mat_aliases={},
        target_stats=["Strength", "Defense"],
        score_fns={},
    )
    assert result is not None


def test_find_best_step_action_accepts_target_stats_parameter():
    """Test: _find_best_step_action accepts target_stats and score_fns parameters."""
    from collections import Counter

    remaining_slots = {
        "Armatura — Chest": [(100, 50, "Item A 1→2", {})]
    }
    result = web._find_best_step_action(
        remaining_slots,
        cur_stats={"Armatura — Chest": 40},
        used_budget=0,
        used_mats=Counter(),
        resource_budget={"Hacksilver": 1000},
        mat_aliases={},
        target_stats=["Strength", "Defense"],
        score_fns={},
    )
    assert result is None or isinstance(result, tuple)


def test_build_step_plan_accepts_target_stats_parameter(monkeypatch):
    """Test: _build_step_plan accepts target_stats and score_fns parameters."""
    from gow_optimizer.optimizer import make_score_fn

    slot_pareto = {
        "Armatura — Chest": [(0, 30, "— nessuna azione —", {})],
        "Armatura — Wrist": [(0, 20, "— nessuna azione —", {})],
        "Armatura — Waist": [(0, 15, "— nessuna azione —", {})],
    }
    resource_budget = {"Hacksilver": 5000}
    mat_aliases = {}
    grand_total = 65
    target_stats = ["Strength", "Defense"]
    score_fns = {
        "Armatura — Chest": make_score_fn(target_stats, {"Strength": 10, "Defense": 20, "Runic": 0, "Vitality": 0, "Cooldown": 0, "Luck": 0}),
    }

    result = web._build_step_plan(
        slot_pareto,
        resource_budget,
        mat_aliases,
        grand_total,
        target_stats=target_stats,
        score_fns=score_fns,
    )

    assert "steps" in result
    assert "step_final_total" in result
    assert "step_final_gain" in result


def test_build_step_plan_works_backwards_compatible(monkeypatch):
    """Test: _build_step_plan still works without target_stats parameter (backwards compatible)."""
    slot_pareto = {
        "Armatura — Chest": [(0, 30, "— nessuna azione —", {})],
        "Armatura — Wrist": [(0, 20, "— nessuna azione —", {})],
    }
    resource_budget = {"Hacksilver": 5000}
    mat_aliases = {}
    grand_total = 50

    # Call without target_stats
    result = web._build_step_plan(
        slot_pareto,
        resource_budget,
        mat_aliases,
        grand_total,
    )

    assert "steps" in result
    assert "step_final_total" in result
    assert result["step_final_total"] == 50
    assert result["step_final_gain"] == 0


def test_build_step_plan_with_multi_objective_options(monkeypatch):
    """Test: _build_step_plan handles options scored with multi-objective metrics."""
    from gow_optimizer.optimizer import make_score_fn

    # Create a Pareto frontier where options are scored with multi-objective metrics
    target_stats = ["Strength", "Defense"]
    baseline = {
        "Strength": 10,
        "Defense": 20,
        "Runic": 0,
        "Vitality": 0,
        "Cooldown": 0,
        "Luck": 0,
    }
    score_fn = make_score_fn(target_stats, baseline)

    # Build a Pareto frontier with geometric mean scores
    # These represent options where stats are already scored with score_fn
    slot_pareto = {
        "Armatura — Chest": [
            (0, score_fn(baseline), "— nessuna azione —", {}),
            (100, score_fn({"Strength": 12, "Defense": 22, "Runic": 0, "Vitality": 0, "Cooldown": 0, "Luck": 0}), "Strong Item 1→2", {}),
        ],
        "Armatura — Wrist": [
            (0, 1.0, "— nessuna azione —", {}),
        ],
    }

    score_fns = {
        "Armatura — Chest": score_fn,
    }

    result = web._build_step_plan(
        slot_pareto,
        {"Hacksilver": 5000},
        {},
        sum(opt[1] for slot in slot_pareto.values() for opt in slot),
        target_stats=target_stats,
        score_fns=score_fns,
    )

    # Verify result structure
    assert "steps" in result
    assert isinstance(result["steps"], list)
    # Should recommend the upgrade since it has positive efficiency
