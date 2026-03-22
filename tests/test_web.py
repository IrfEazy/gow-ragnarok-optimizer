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
