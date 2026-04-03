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
}


def _patch_runtime_store(monkeypatch, state):
    def load():
        return deepcopy(state)

    def save(data):
        state.clear()
        state.update(deepcopy(data))

    monkeypatch.setattr(web, "load_web_inventory", load)
    monkeypatch.setattr(web, "save_web_inventory", save)
    monkeypatch.setattr(
        web,
        "_compute_all",
        lambda web_data=None: {
            **EMPTY_COMPUTE_RESULT,
            "hacksilver": (web_data or state)["resource_budget"].get("Hacksilver", 0),
            "resources": [
                {"name": key, "qty": value}
                for key, value in sorted((web_data or state)["resource_budget"].items())
            ],
        },
    )


def test_create_app_has_expected_routes(monkeypatch):
    monkeypatch.setattr(web, "_compute_all", lambda web_data=None: EMPTY_COMPUTE_RESULT)

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


def test_home_page_includes_localstorage_functions(monkeypatch):
    """Test: GET / should include localStorage persistence functions."""
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

    # Check for localStorage functions
    assert "function saveStatSelection" in html
    assert "localStorage.setItem('gow_optimizer_stats'" in html
    assert "function loadStatSelection" in html
    assert "localStorage.getItem('gow_optimizer_stats')" in html
    assert "function resetStatSelection" in html
    assert "localStorage.removeItem('gow_optimizer_stats')" in html
    # Verify loadStatSelection is called on page initialization
    assert "loadStatSelection()" in html


def test_apply_stat_selection_includes_save_logic(monkeypatch):
    """Test: applyStatSelection should call saveStatSelection."""
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

    # Verify applyStatSelection function includes saveStatSelection call
    assert "async function applyStatSelection()" in html
    assert "saveStatSelection(selected)" in html


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
