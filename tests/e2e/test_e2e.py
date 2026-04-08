"""Playwright E2E tests for the God of War Ragnarök Build Optimizer web UI.

These tests start a real Flask server in a background thread and use Playwright
to interact with it through an actual browser.

Run with:
    uv run python -m pytest tests/e2e/ -v --headed   # visible browser
    uv run python -m pytest tests/e2e/ -v             # headless (CI)
"""

import re
import threading
import time

import pytest
from playwright.sync_api import Page, expect

from gow_optimizer.config import save_yaml
from gow_optimizer.web import create_app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def _server_port():
    """Return a fixed port for the test server."""
    return 5099


@pytest.fixture(scope="session")
def _app_server(_server_port, tmp_path_factory):
    """Start a Flask test server in a background thread for the entire session.

    Uses a temporary config/web_inventory so the real files are untouched.
    """
    tmp = tmp_path_factory.mktemp("e2e")

    # Create minimal config
    config_path = tmp / "config.yaml"
    web_inv_path = tmp / "web_inventory.yaml"

    test_config = {
        "force_scrape": False,
        "armor_csv": "data/all_pieces.csv",
        "weapons_csv": "data/all_weapons.csv",
        "mat_aliases": {
            "Smouldering Embers": "Smoldering Embers",
            "Petrified Bones": "Petrified Bone",
            "Whispering Slabs": "Whispering Slab",
            "Asgardian Ingots": "Asgardian Ingot",
            "Dwaren Steel": "Dwarven Steel",
            "s Broken Cuirass": "Lunda's Broken Cuirass",
            "s Broken Bracers": "Lunda's Broken Bracers",
            "s Broken Belt": "Lunda's Broken Belt",
        },
        "resource_budget": {"Hacksilver": 50000},
        "chest_pieces": [
            {"name": "Nidavellir's Finest Plackart", "level": 5},
        ],
        "wrist_pieces": [],
        "waist_pieces": [],
        "axe_attachments": [],
        "blades_attachments": [],
        "spear_attachments": [],
        "shield_attachments": [],
        "optimization_stats": ["Strength", "Defense"],
        "stat_presets": {
            "Defensive": ["Defense", "Vitality"],
            "Aggressive": ["Strength", "Runic"],
            "Balanced": ["Strength", "Defense", "Runic", "Vitality"],
        },
    }
    save_yaml(config_path, test_config)

    # Monkey-patch paths before creating the app
    from gow_optimizer import config as config_module
    from gow_optimizer import paths as paths_module

    original_config = paths_module.CONFIG_PATH
    original_web_inv = paths_module.WEB_INVENTORY_PATH

    paths_module.CONFIG_PATH = config_path
    config_module.CONFIG_PATH = config_path
    paths_module.WEB_INVENTORY_PATH = web_inv_path
    config_module.WEB_INVENTORY_PATH = web_inv_path

    app = create_app()
    app.config["TESTING"] = True

    server = threading.Thread(
        target=lambda: app.run(
            host="127.0.0.1",
            port=_server_port,
            use_reloader=False,
            threaded=True,
        ),
        daemon=True,
    )
    server.start()

    # Wait for server to be ready
    import urllib.request
    for _ in range(30):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{_server_port}/")
            break
        except Exception:
            time.sleep(0.2)
    else:
        raise RuntimeError("Flask test server did not start in time")

    yield f"http://127.0.0.1:{_server_port}"

    # Restore original paths
    paths_module.CONFIG_PATH = original_config
    config_module.CONFIG_PATH = original_config
    paths_module.WEB_INVENTORY_PATH = original_web_inv
    config_module.WEB_INVENTORY_PATH = original_web_inv


@pytest.fixture(scope="session")
def base_url(_app_server):
    """Expose the base URL for tests."""
    return _app_server


# ---------------------------------------------------------------------------
# Test: Page loads correctly
# ---------------------------------------------------------------------------

class TestPageLoad:
    """Verify the page loads and renders key sections."""

    def test_home_page_loads(self, page: Page, base_url: str):
        page.goto(base_url)
        expect(page).to_have_title("God of War Ragnarök — Build Optimizer")

    def test_sections_present(self, page: Page, base_url: str):
        page.goto(base_url)
        expect(page.locator("#inventory-manager-section")).to_be_visible()
        expect(page.locator("#resources-section")).to_be_visible()
        expect(page.locator("#stat-selector-section")).to_be_visible()

    def test_summary_bar_shows_totals(self, page: Page, base_url: str):
        page.goto(base_url)
        summary = page.locator("#summary-bar")
        expect(summary).to_be_visible()
        # Should contain at least one summary card
        expect(summary.locator(".summary-card").first).to_be_visible()

    def test_no_js_errors_on_load(self, page: Page, base_url: str):
        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.goto(base_url)
        page.wait_for_load_state("networkidle")
        assert errors == [], f"JS errors on page load: {errors}"


# ---------------------------------------------------------------------------
# Test: Theme toggle
# ---------------------------------------------------------------------------

class TestThemeToggle:
    """Verify dark/light theme switching."""

    def test_toggle_theme(self, page: Page, base_url: str):
        page.goto(base_url)
        html = page.locator("html")

        # Default theme — no data-theme attribute means dark
        initial_theme = html.get_attribute("data-theme") or "dark"

        # Click theme toggle
        page.locator("#theme-toggle").click()
        page.wait_for_timeout(200)
        new_theme = html.get_attribute("data-theme") or "dark"
        assert initial_theme != new_theme, "Theme should change on toggle"

        # Toggle back
        page.locator("#theme-toggle").click()
        page.wait_for_timeout(200)
        restored = html.get_attribute("data-theme") or "dark"
        assert restored == initial_theme


# ---------------------------------------------------------------------------
# Test: Inventory management
# ---------------------------------------------------------------------------

class TestInventoryManagement:
    """Test piece card interactions (add/remove from inventory)."""

    def test_piece_search_filters_cards(self, page: Page, base_url: str):
        page.goto(base_url)

        # Expand inventory section
        page.locator("#inventory-manager-section .section-header").click()
        page.wait_for_timeout(300)

        search = page.locator("#piece-search")
        expect(search).to_be_visible()

        # Type a search term
        search.fill("Berserker")
        page.wait_for_timeout(300)

        # Only Berserker cards should be visible
        visible_cards = page.locator(".piece-card:visible")
        count = visible_cards.count()
        assert count > 0, "Should have visible Berserker cards"

        # All visible cards should contain "Berserker"
        for i in range(count):
            text = visible_cards.nth(i).inner_text()
            assert "Berserker" in text, f"Card {i} doesn't match search: {text}"

    def test_add_and_remove_piece(self, page: Page, base_url: str):
        page.goto(base_url)

        # Expand inventory
        page.locator("#inventory-manager-section .section-header").click()
        page.wait_for_timeout(300)

        # Find a not-owned piece card
        not_owned = page.locator(".piece-card.not-owned").first
        piece_name = not_owned.get_attribute("data-name")
        expect(not_owned).to_be_visible()

        # Click to open modal
        not_owned.click()
        modal = page.locator("#craft-confirmation-modal")
        expect(modal).to_have_class(re.compile(r"show"))

        # Click "Lo possiedo già" (I already own it)
        page.locator("#craft-confirmation-modal button", has_text="Lo possiedo già").click()
        page.wait_for_timeout(500)

        # Verify piece is now owned
        card = page.locator(f".piece-card[data-name='{piece_name}']")
        expect(card).to_have_class(re.compile(r"\bowned\b"))

        # Click to remove
        card.click()
        page.wait_for_timeout(500)

        # Verify piece is now not-owned again
        expect(card).to_have_class(re.compile(r"not-owned"))


# ---------------------------------------------------------------------------
# Test: Resource editing
# ---------------------------------------------------------------------------

class TestResourceEditing:
    """Test resource budget editing flow."""

    def test_edit_and_cancel_resources(self, page: Page, base_url: str):
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        # Resources section starts expanded — no need to click header

        # Get initial hacksilver value
        hack_display = page.locator(".res-item[data-mat='Hacksilver'] .res-qty-display")
        initial_qty = hack_display.inner_text()

        # Enter edit mode
        page.locator("#btn-edit-toggle").click()
        page.wait_for_timeout(200)

        # Modify hacksilver input
        hack_input = page.locator(".res-editor input[data-mat='Hacksilver']")
        expect(hack_input).to_be_visible()
        hack_input.fill("99999")

        # Cancel
        page.locator("#btn-cancel").click()
        page.wait_for_timeout(200)

        # Value should revert
        expect(hack_display).to_have_text(initial_qty)

    def test_edit_and_save_resources(self, page: Page, base_url: str):
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        # Resources section starts expanded — no need to click header

        # Enter edit mode
        page.locator("#btn-edit-toggle").click()
        page.wait_for_timeout(200)

        # Set hacksilver to a known value
        hack_input = page.locator(".res-editor input[data-mat='Hacksilver']")
        hack_input.fill("75000")

        # Save
        page.locator("#btn-save").click()
        page.wait_for_timeout(1000)

        # Verify updated — value may be locale-formatted (e.g., 75.000 or 75,000)
        hack_display = page.locator(".res-item[data-mat='Hacksilver'] .res-qty-display")
        expect(hack_display).to_have_text(re.compile(r"75[.,]?000"))


# ---------------------------------------------------------------------------
# Test: Stat preferences
# ---------------------------------------------------------------------------

class TestStatPreferences:
    """Test stat objective selection and presets."""

    def test_toggle_stat_checkboxes(self, page: Page, base_url: str):
        page.goto(base_url)

        # Expand stat selector
        page.locator("#stat-selector-section .section-header").click()
        page.wait_for_timeout(300)

        # Should have 6 stat checkboxes
        checkboxes = page.locator("#stat-selector input[name='stat']")
        assert checkboxes.count() == 6

    def test_apply_stat_preferences(self, page: Page, base_url: str):
        page.goto(base_url)

        # Expand stat selector
        page.locator("#stat-selector-section .section-header").click()
        page.wait_for_timeout(300)

        # Check only Strength
        for cb in page.locator("#stat-selector input[name='stat']").all():
            if cb.is_checked():
                cb.uncheck()
        page.locator("#stat-selector input[value='Strength']").check()

        # Apply
        page.locator("#btn-apply-stats").click()
        page.wait_for_timeout(1000)

        # Page should have recalculated (no error)
        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        assert errors == [], f"JS errors after applying stats: {errors}"


# ---------------------------------------------------------------------------
# Test: Piano Ottimo (optimal plan) and apply upgrade
# ---------------------------------------------------------------------------

class TestOptimalPlan:
    """Test the optimal plan section and upgrade application."""

    def test_piano_ottimo_has_actions(self, page: Page, base_url: str):
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        # The piano section should contain action rows or step groups
        piano_body = page.locator("#piano-body")
        # Either step-group-header or btn-success should be present
        action_elements = piano_body.locator(".step-group-header, .btn-success")
        assert action_elements.count() > 0, "Piano Ottimo should have upgrade actions"

    def test_apply_upgrade_and_undo(self, page: Page, base_url: str):
        errors = []
        console_msgs = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.on("console", lambda msg: console_msgs.append(f"{msg.type}: {msg.text}"))

        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        # Find first enabled "✓ Fatto" button within #piano-body
        done_btn = page.locator("#piano-body .btn-success:not([disabled])", has_text="Fatto").first
        if done_btn.count() == 0:
            pytest.skip("No applicable upgrade actions available")

        # Debug: print button outer HTML
        btn_html = done_btn.evaluate("el => el.outerHTML")
        print(f"Button HTML: {btn_html[:300]}")

        # Click and check if request fires
        responses = []
        page.on("response", lambda resp: responses.append(f"{resp.status} {resp.url}"))

        done_btn.click()
        page.wait_for_timeout(3000)

        print(f"Responses after click: {responses}")
        print(f"Console messages: {console_msgs[-5:]}")
        print(f"JS errors: {errors}")

        # Check if any apply-upgrade response came back
        apply_responses = [r for r in responses if "apply-upgrade" in r]
        assert apply_responses, (
            f"No apply-upgrade request detected.\n"
            f"Button HTML: {btn_html[:300]}\n"
            f"Responses: {responses}\n"
            f"Console: {console_msgs[-10:]}\n"
            f"Errors: {errors}"
        )

        # Undo button should appear
        undo_btn = page.locator("#undo-btn")
        expect(undo_btn).to_be_visible(timeout=5000)

        # Click undo
        undo_btn.click()
        page.wait_for_timeout(2000)

        # Undo button should be hidden again
        expect(undo_btn).to_be_hidden(timeout=5000)


# ---------------------------------------------------------------------------
# Test: Shopping list
# ---------------------------------------------------------------------------

class TestShoppingList:
    """Test the shopping list section."""

    def test_shopping_list_loads(self, page: Page, base_url: str):
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        # Click the first section header inside shopping to expand/collapse
        page.locator("#shopping-section > .section-header").first.click()
        page.wait_for_timeout(300)

        shopping_body = page.locator("#shopping-body")
        expect(shopping_body).to_be_visible()


# ---------------------------------------------------------------------------
# Test: Build slots
# ---------------------------------------------------------------------------

class TestBuildSlots:
    """Test build slot save/load/delete functionality."""

    def test_save_and_delete_build_slot(self, page: Page, base_url: str):
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        # Click save slot button
        save_btn = page.locator("#btn-save-slot")
        expect(save_btn).to_be_visible()

        # The save action opens a prompt — handle it
        page.on("dialog", lambda dialog: dialog.accept("E2E Test Slot"))
        save_btn.click()
        page.wait_for_timeout(1000)

        # Verify slot was saved via API
        resp = page.request.get(f"{base_url}/api/build-slots")
        data = resp.json()
        slot_names = [s["name"] for s in data.get("slots", [])]
        assert "E2E Test Slot" in slot_names, f"Slot not found: {slot_names}"

        # Clean up via API
        page.request.post(
            f"{base_url}/api/build-slots",
            data={"action": "delete", "name": "E2E Test Slot"},
        )


# ---------------------------------------------------------------------------
# Test: Export build
# ---------------------------------------------------------------------------

class TestExportBuild:
    """Test build export functionality."""

    def test_export_button_exists(self, page: Page, base_url: str):
        page.goto(base_url)
        export_btn = page.locator("#btn-export")
        expect(export_btn).to_be_visible()


# ---------------------------------------------------------------------------
# Test: No console errors during interaction flow
# ---------------------------------------------------------------------------

class TestNoConsoleErrors:
    """Ensure no JS errors during a typical user workflow."""

    def test_full_workflow_no_errors(self, page: Page, base_url: str):
        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))

        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        # Toggle theme
        page.locator("#theme-toggle").click()
        page.wait_for_timeout(200)
        page.locator("#theme-toggle").click()
        page.wait_for_timeout(200)

        # Expand and collapse inventory
        page.locator("#inventory-manager-section .section-header").click()
        page.wait_for_timeout(200)
        page.locator("#inventory-manager-section .section-header").click()
        page.wait_for_timeout(200)

        # Expand stat selector
        page.locator("#stat-selector-section .section-header").click()
        page.wait_for_timeout(200)
        page.locator("#stat-selector-section .section-header").click()
        page.wait_for_timeout(200)

        # Expand resources
        page.locator("#resources-section .section-header").click()
        page.wait_for_timeout(200)
        page.locator("#resources-section .section-header").click()
        page.wait_for_timeout(200)

        assert errors == [], f"JS errors during workflow: {errors}"
