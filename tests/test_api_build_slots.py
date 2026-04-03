"""Tests for build slot API endpoints."""

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


def _patch_runtime_with_slots(monkeypatch, state, slots):
    def load():
        return deepcopy(state)

    def save(data):
        state.clear()
        state.update(deepcopy(data))

    def load_slots():
        return deepcopy(slots)

    def save_slots(s):
        slots.clear()
        slots.update(deepcopy(s))

    monkeypatch.setattr(web, "load_web_inventory", load)
    monkeypatch.setattr(web, "save_web_inventory", save)
    monkeypatch.setattr(web, "load_build_slots", load_slots)
    monkeypatch.setattr(web, "save_build_slots", save_slots)
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


def test_create_build_slot_endpoint(monkeypatch):
    """RED: POST /api/build-slots should create a named slot."""
    state = {
        "resource_budget": {"Hacksilver": 5000},
        "chest_pieces": [{"name": "Lunda's Lost Cuirass", "level": 5, "craft": True}],
        "wrist_pieces": [],
        "waist_pieces": [],
        "axe_attachments": [],
        "blades_attachments": [],
        "spear_attachments": [],
        "shield_attachments": [],
    }
    slots = {}
    _patch_runtime_with_slots(monkeypatch, state, slots)

    app = web.create_app({"TESTING": True})
    client = app.test_client()

    response = client.post(
        "/api/build-slots",
        json={"action": "create", "name": "Strength Build"},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert "Strength Build" in slots


def test_list_build_slots_endpoint(monkeypatch):
    """RED: GET /api/build-slots should list all slots."""
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
    slots = {
        "Strength Build": {"resource_budget": {"Hacksilver": 5000}},
        "Runic Build": {"resource_budget": {"Hacksilver": 3000}},
    }
    _patch_runtime_with_slots(monkeypatch, state, slots)

    app = web.create_app({"TESTING": True})
    client = app.test_client()

    response = client.get("/api/build-slots")

    assert response.status_code == 200
    data = response.get_json()
    assert len(data["slots"]) == 2
    assert "Strength Build" in [s["name"] for s in data["slots"]]


def test_load_build_slot_endpoint(monkeypatch):
    """RED: POST /api/build-slots with load action should restore slot."""
    state = {
        "resource_budget": {"Hacksilver": 0},
        "chest_pieces": [],
        "wrist_pieces": [],
        "waist_pieces": [],
        "axe_attachments": [],
        "blades_attachments": [],
        "spear_attachments": [],
        "shield_attachments": [],
    }
    slots = {
        "Strength Build": {
            "resource_budget": {"Hacksilver": 5000},
            "chest_pieces": [{"name": "Lunda's Lost Cuirass", "level": 5, "craft": True}],
            "wrist_pieces": [],
            "waist_pieces": [],
            "axe_attachments": [],
            "blades_attachments": [],
            "spear_attachments": [],
            "shield_attachments": [],
        },
    }
    _patch_runtime_with_slots(monkeypatch, state, slots)

    app = web.create_app({"TESTING": True})
    client = app.test_client()

    response = client.post(
        "/api/build-slots",
        json={"action": "load", "name": "Strength Build"},
    )

    assert response.status_code == 200
    assert state["resource_budget"]["Hacksilver"] == 5000


def test_delete_build_slot_endpoint(monkeypatch):
    """RED: POST /api/build-slots with delete action should remove slot."""
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
    slots = {
        "Strength Build": {"resource_budget": {"Hacksilver": 5000}},
        "Runic Build": {"resource_budget": {"Hacksilver": 3000}},
    }
    _patch_runtime_with_slots(monkeypatch, state, slots)

    app = web.create_app({"TESTING": True})
    client = app.test_client()

    response = client.post(
        "/api/build-slots",
        json={"action": "delete", "name": "Strength Build"},
    )

    assert response.status_code == 200
    assert "Strength Build" not in slots
    assert "Runic Build" in slots
