"""Tests for export/import API endpoints."""

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


def test_export_build_endpoint_returns_json(monkeypatch):
    """RED: POST /api/export-build should return exported build as JSON."""
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
    _patch_runtime_store(monkeypatch, state)

    app = web.create_app({"TESTING": True})
    client = app.test_client()

    response = client.post("/api/export-build", json={})

    assert response.status_code == 200
    data = response.get_json()
    assert "version" in data
    assert "timestamp" in data
    assert data["resource_budget"]["Hacksilver"] == 5000


def test_export_build_csv_endpoint_returns_csv_download(monkeypatch):
    """RED: GET /api/export-build-csv should return CSV file."""
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
    _patch_runtime_store(monkeypatch, state)

    app = web.create_app({"TESTING": True})
    client = app.test_client()

    response = client.get("/api/export-build-csv")

    assert response.status_code == 200
    assert "text/csv" in response.content_type
    assert b"Piece Type,Name,Level,Craft" in response.data


def test_import_build_endpoint_accepts_exported_data(monkeypatch):
    """RED: POST /api/import-build should restore exported build."""
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
    _patch_runtime_store(monkeypatch, state)

    app = web.create_app({"TESTING": True})
    client = app.test_client()

    exported_build = {
        "version": "0.1.0",
        "timestamp": "2026-04-03T12:00:00Z",
        "resource_budget": {"Hacksilver": 5000},
        "armor": {
            "chest": [{"name": "Lunda's Lost Cuirass", "level": 5, "craft": True}],
        },
        "weapons": {"axe": []},
    }

    response = client.post("/api/import-build", json=exported_build)

    assert response.status_code == 200
    assert state["resource_budget"]["Hacksilver"] == 5000
    assert state["chest_pieces"][0]["name"] == "Lunda's Lost Cuirass"


def test_share_build_endpoint_returns_shareable_url(monkeypatch):
    """RED: POST /api/share-build should return shareable URL."""
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

    response = client.post("/api/share-build", json={})

    assert response.status_code == 200
    data = response.get_json()
    assert "url" in data
    assert "?build=" in data["url"] or "#build=" in data["url"]
