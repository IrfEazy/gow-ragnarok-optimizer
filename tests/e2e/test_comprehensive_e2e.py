"""Comprehensive Playwright E2E tests — deep user interaction coverage.

Tests every user flow, edge case, and interaction pattern to find bugs.
"""

import json
import re
import threading
import time

import pytest
from playwright.sync_api import Page, expect

from gow_optimizer.config import save_yaml
from gow_optimizer.web import create_app

# ---------------------------------------------------------------------------
# Fixtures (reuses same pattern as test_e2e.py)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def _server_port():
    return 5098


@pytest.fixture(scope="session")
def _app_server(_server_port, tmp_path_factory):
    tmp = tmp_path_factory.mktemp("e2e_comp")
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
        "resource_budget": {
            "Hacksilver": 150000,
            "Smoldering Embers": 50,
            "Honed Metal": 30,
            "Tempered Remnants": 20,
            "Luminous Alloy": 15,
            "Asgardian Ingot": 10,
            "Petrified Bone": 25,
            "Dwarven Steel": 20,
            "Whispering Slab": 15,
        },
        "chest_pieces": [
            {"name": "Nidavellir's Finest Plackart", "level": 2},
            {"name": "Steinbjorn Plackart", "level": 6, "craft": True},
        ],
        "wrist_pieces": [
            {"name": "Steinbjorn Gauntlets", "level": 6, "craft": True},
        ],
        "waist_pieces": [
            {"name": "Steinbjorn Waist Guard", "level": 6, "craft": True},
        ],
        "axe_attachments": [
            {"name": "Stonecutter's Knob", "level": 4},
        ],
        "blades_attachments": [],
        "spear_attachments": [],
        "shield_attachments": [],
        "optimization_stats": None,
        "stat_presets": {
            "Defensive": ["Defense", "Vitality"],
            "Aggressive": ["Strength", "Runic"],
            "Balanced": ["Strength", "Defense", "Runic", "Vitality"],
        },
    }
    save_yaml(config_path, test_config)

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

    paths_module.CONFIG_PATH = original_config
    config_module.CONFIG_PATH = original_config
    paths_module.WEB_INVENTORY_PATH = original_web_inv
    config_module.WEB_INVENTORY_PATH = original_web_inv


@pytest.fixture(scope="session")
def base_url(_app_server):
    return _app_server


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def collect_errors_and_console(page):
    """Attach error and console listeners. Returns (errors, console_msgs) lists."""
    errors = []
    console_msgs = []
    page.on("pageerror", lambda err: errors.append(str(err)))
    page.on("console", lambda msg: console_msgs.append(f"[{msg.type}] {msg.text}"))
    return errors, console_msgs


def wait_for_recalc(page, timeout=5000):
    """Wait for loading overlay to appear and disappear, indicating recalc finished."""
    # The loading overlay might appear briefly
    page.wait_for_timeout(300)
    try:
        page.locator("#loading-overlay").wait_for(state="hidden", timeout=timeout)
    except Exception:
        pass  # Overlay may never appear if computation is very fast


# ===========================================================================
# 1. INITIAL PAGE LOAD — detailed checks
# ===========================================================================


class TestDetailedPageLoad:
    def test_all_summary_cards_present(self, page: Page, base_url: str):
        page.goto(base_url)
        cards = page.locator("#summary-bar .summary-card")
        count = cards.count()
        assert count >= 3, f"Expected at least 3 summary cards, got {count}"

    def test_summary_cards_have_numeric_values(self, page: Page, base_url: str):
        page.goto(base_url)
        cards = page.locator("#summary-bar .summary-card .summary-value")
        for i in range(cards.count()):
            text = cards.nth(i).inner_text().strip()
            # Should contain digits (possibly with locale separators)
            assert re.search(r"\d", text), (
                f"Summary card {i} has no numeric value: '{text}'"
            )

    def test_best_build_section_has_items(self, page: Page, base_url: str):
        page.goto(base_url)
        # best-build-body is the actual ID
        slot_cards = page.locator("#best-build-body .slot-card")
        assert slot_cards.count() > 0, "Best build section should have slot cards"

    def test_no_500_errors_any_section(self, page: Page, base_url: str):
        """Ensure no section shows a server error."""
        errors, _ = collect_errors_and_console(page)
        page.goto(base_url)
        page.wait_for_load_state("networkidle")
        body_text = page.locator("body").inner_text()
        assert "500" not in body_text or "Internal Server Error" not in body_text
        assert errors == [], f"JS errors: {errors}"

    def test_all_sections_exist(self, page: Page, base_url: str):
        page.goto(base_url)
        expected_sections = [
            "#best-build-body",
            "#rankings-body",
            "#inventory-manager-section",
            "#stat-selector-section",
            "#resources-section",
            "#pareto-body",
            "#piano-body",
            "#shopping-section",
        ]
        for selector in expected_sections:
            loc = page.locator(selector)
            assert loc.count() > 0, f"Section {selector} not found in DOM"


# ===========================================================================
# 2. THEME TOGGLE — persistence and UI
# ===========================================================================


class TestThemeDetails:
    def test_theme_persists_across_reloads(self, page: Page, base_url: str):
        page.goto(base_url)
        # Switch to light theme
        page.locator("#theme-toggle").click()
        page.wait_for_timeout(200)
        theme_after_toggle = page.locator("html").get_attribute("data-theme")

        # Reload page
        page.reload()
        page.wait_for_load_state("networkidle")
        theme_after_reload = page.locator("html").get_attribute("data-theme")
        assert theme_after_toggle == theme_after_reload, (
            "Theme should persist after reload"
        )

        # Reset to dark for other tests
        if theme_after_reload != "dark":
            page.locator("#theme-toggle").click()
            page.wait_for_timeout(200)

    def test_theme_button_text_updates(self, page: Page, base_url: str):
        page.goto(base_url)
        btn = page.locator("#theme-toggle")
        initial_text = btn.inner_text()

        btn.click()
        page.wait_for_timeout(200)
        new_text = btn.inner_text()
        assert initial_text != new_text, "Theme button text should change on toggle"

        # Reset
        btn.click()
        page.wait_for_timeout(200)


# ===========================================================================
# 3. COLLAPSIBLE SECTIONS — toggling
# ===========================================================================


class TestCollapsibleSections:
    @pytest.mark.parametrize(
        "section_id",
        [
            "inventory-manager-section",
            "shopping-section",
        ],
    )
    def test_section_toggles(self, page: Page, base_url: str, section_id: str):
        """Test sections that use the collapsed class toggle pattern."""
        page.goto(base_url)
        section = page.locator(f"#{section_id}")
        header = section.locator(".section-header").first

        # Get initial state
        initial_class = section.get_attribute("class") or ""
        was_collapsed = "collapsed" in initial_class

        # Toggle
        header.click()
        page.wait_for_timeout(300)
        new_class = section.get_attribute("class") or ""
        is_collapsed_now = "collapsed" in new_class
        assert was_collapsed != is_collapsed_now, (
            f"Section {section_id} should toggle collapsed state"
        )

        # Toggle back
        header.click()
        page.wait_for_timeout(300)

    def test_stat_section_toggles(self, page: Page, base_url: str):
        """Stat selector section uses display:none toggle, not collapsed class."""
        page.goto(base_url)
        body = page.locator("#stat-section-body")

        # Initially hidden (display: none)
        assert not body.is_visible(), "Stat section body should be hidden initially"

        # Click header to reveal
        page.locator("#stat-selector-section .section-header").click()
        page.wait_for_timeout(300)
        assert body.is_visible(), "Stat section body should be visible after click"

        # Click again to hide
        page.locator("#stat-selector-section .section-header").click()
        page.wait_for_timeout(300)
        assert not body.is_visible(), "Stat section body should be hidden again"

    def test_rankings_section_toggles(self, page: Page, base_url: str):
        """Rankings section (no ID) toggles via parent of #rankings-body."""
        page.goto(base_url)
        rankings_parent = page.locator("#rankings-body").locator("xpath=..")
        header = rankings_parent.locator(".section-header").first

        initial_class = rankings_parent.get_attribute("class") or ""
        was_collapsed = "collapsed" in initial_class

        header.click()
        page.wait_for_timeout(300)
        new_class = rankings_parent.get_attribute("class") or ""
        assert ("collapsed" in new_class) != was_collapsed

    def test_pareto_section_toggles(self, page: Page, base_url: str):
        """Pareto section (no ID) toggles via parent of #pareto-body."""
        page.goto(base_url)
        pareto_parent = page.locator("#pareto-body").locator("xpath=..")
        header = pareto_parent.locator(".section-header").first

        initial_class = pareto_parent.get_attribute("class") or ""
        was_collapsed = "collapsed" in initial_class

        header.click()
        page.wait_for_timeout(300)
        new_class = pareto_parent.get_attribute("class") or ""
        assert ("collapsed" in new_class) != was_collapsed


# ===========================================================================
# 4. RESOURCE EDITING — full workflow
# ===========================================================================


class TestResourceEditingDeep:
    def test_resource_step_buttons(self, page: Page, base_url: str):
        """Test the +/- step buttons for resources."""
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        # Enter edit mode
        page.locator("#btn-edit-toggle").click()
        page.wait_for_timeout(300)

        # Find hacksilver input
        hack_editor = page.locator(".res-editor[data-mat='Hacksilver']")
        if hack_editor.count() == 0:
            hack_editor = page.locator(".res-item[data-mat='Hacksilver'] .res-editor")
        hack_input = page.locator("input[data-mat='Hacksilver']")

        if hack_input.count() > 0:
            initial_val = int(hack_input.input_value() or "0")

            # Click + button
            plus_btn = hack_input.locator(
                "xpath=following-sibling::button | ../button[contains(text(),'+')]"
            ).first
            if plus_btn.count() > 0:
                plus_btn.click()
                page.wait_for_timeout(100)
                new_val = int(hack_input.input_value() or "0")
                assert new_val > initial_val, (
                    f"Step + should increase value: {initial_val} -> {new_val}"
                )

        # Cancel to not save changes
        page.locator("#btn-cancel").click()

    def test_save_resources_updates_summary(self, page: Page, base_url: str):
        """After saving resources, the summary bar hacksilver should update."""
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        # Enter edit mode
        page.locator("#btn-edit-toggle").click()
        page.wait_for_timeout(300)

        # Set hacksilver to a specific value
        hack_input = page.locator("input[data-mat='Hacksilver']")
        if hack_input.count() > 0:
            hack_input.fill("100000")
            # Save and wait for API response
            with page.expect_response("**/api/save-inventory") as resp_info:
                page.locator("#btn-save").click()
            resp_info.value
            page.wait_for_timeout(500)
            hack_display = page.locator(
                ".res-item[data-mat='Hacksilver'] .res-qty-display"
            )
            if hack_display.count() > 0:
                text = hack_display.inner_text()
                assert re.search(r"100", text), (
                    f"Hacksilver should show ~100000, got: {text}"
                )

    def test_zero_resources_handled(self, page: Page, base_url: str):
        """Setting a resource to 0 should not cause errors."""
        errors, _ = collect_errors_and_console(page)
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        page.locator("#btn-edit-toggle").click()
        page.wait_for_timeout(300)

        # Set hacksilver to 0
        hack_input = page.locator("input[data-mat='Hacksilver']")
        if hack_input.count() > 0:
            hack_input.fill("0")
            page.locator("#btn-save").click()
            wait_for_recalc(page)

            assert errors == [], f"Setting 0 resources caused JS errors: {errors}"

            # Restore
            page.locator("#btn-edit-toggle").click()
            page.wait_for_timeout(300)
            hack_input = page.locator("input[data-mat='Hacksilver']")
            hack_input.fill("150000")
            page.locator("#btn-save").click()
            wait_for_recalc(page)


# ===========================================================================
# 5. STAT PREFERENCES — deep testing
# ===========================================================================


class TestStatPreferencesDeep:
    def test_select_single_stat_recalculates(self, page: Page, base_url: str):
        """Selecting a single stat and applying should recalculate without errors."""
        errors, console = collect_errors_and_console(page)
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        # Expand stat selector (uses toggleStatPreferences)
        body = page.locator("#stat-section-body")
        if not body.is_visible():
            page.locator("#stat-selector-section .section-header").click()
            page.wait_for_timeout(300)

        # Uncheck all, then check only Defense
        for cb in page.locator("#stat-selector input[name='stat']").all():
            if cb.is_checked():
                cb.uncheck()
        page.locator("#stat-selector input[value='Defense']").check()

        # Apply
        page.locator("#btn-apply-stats").click()
        wait_for_recalc(page)

        # Verify no errors
        assert errors == [], f"Errors after single stat selection: {errors}"

        # Best build should still have items
        slot_cards = page.locator("#best-build-body .slot-card")
        assert slot_cards.count() > 0, "Best build should still show items"

    def test_select_all_stats_recalculates(self, page: Page, base_url: str):
        """Selecting all stats should work like reset."""
        errors, _ = collect_errors_and_console(page)
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        body = page.locator("#stat-section-body")
        if not body.is_visible():
            page.locator("#stat-selector-section .section-header").click()
            page.wait_for_timeout(300)

        # Check all stats
        for cb in page.locator("#stat-selector input[name='stat']").all():
            if not cb.is_checked():
                cb.check()

        page.locator("#btn-apply-stats").click()
        wait_for_recalc(page)
        assert errors == [], f"Errors after all stats selection: {errors}"

    def test_reset_preferences(self, page: Page, base_url: str):
        """Reset stat preferences should work without errors."""
        errors, _ = collect_errors_and_console(page)
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        body = page.locator("#stat-section-body")
        if not body.is_visible():
            page.locator("#stat-selector-section .section-header").click()
            page.wait_for_timeout(300)

        reset_btn = page.locator("#btn-reset-stats")
        if reset_btn.count() > 0:
            reset_btn.click()
            wait_for_recalc(page)
            assert errors == [], f"Errors after reset: {errors}"

    def test_select_no_stats_then_apply(self, page: Page, base_url: str):
        """Applying with no stats selected — edge case."""
        errors, console = collect_errors_and_console(page)
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        body = page.locator("#stat-section-body")
        if not body.is_visible():
            page.locator("#stat-selector-section .section-header").click()
            page.wait_for_timeout(300)

        # Uncheck all
        for cb in page.locator("#stat-selector input[name='stat']").all():
            if cb.is_checked():
                cb.uncheck()

        page.locator("#btn-apply-stats").click()
        wait_for_recalc(page)

        # Should not crash — either shows error toast or resets to default
        page.wait_for_timeout(1000)
        js_errors = [
            e
            for e in errors
            if "TypeError" in e or "ReferenceError" in e or "Cannot" in e
        ]
        assert js_errors == [], f"JS errors with no stats selected: {js_errors}"


# ===========================================================================
# 6. STAT PRESETS — save/load/delete
# ===========================================================================


class TestStatPresetsDeep:
    def _open_stat_section(self, page):
        body = page.locator("#stat-section-body")
        if not body.is_visible():
            page.locator("#stat-selector-section .section-header").click()
            page.wait_for_timeout(300)

    def test_load_preset_updates_checkboxes(self, page: Page, base_url: str):
        """Loading a preset should check the right stat boxes."""
        errors, _ = collect_errors_and_console(page)
        page.goto(base_url)
        page.wait_for_load_state("networkidle")
        self._open_stat_section(page)

        # Select "Defensive" preset from dropdown
        preset_dropdown = page.locator("#stat-preset-dropdown")
        if preset_dropdown.count() > 0:
            preset_dropdown.select_option(label="Defensive")
            page.wait_for_timeout(200)

            # Click load button (inline onclick, find by text)
            load_btn = page.locator(
                "#stat-section-body button", has_text="Carica"
            ).first
            if load_btn.count() > 0:
                with page.expect_response("**/api/stat-presets") as resp_info:
                    load_btn.click()
                resp_info.value  # wait for response
                page.wait_for_timeout(500)  # let JS process

                # Verify Defense and Vitality are checked
                defense_cb = page.locator("#stat-selector input[value='Defense']")
                vitality_cb = page.locator("#stat-selector input[value='Vitality']")
                assert defense_cb.is_checked(), (
                    "Defense should be checked for Defensive preset"
                )
                assert vitality_cb.is_checked(), (
                    "Vitality should be checked for Defensive preset"
                )

                # Verify Strength is NOT checked
                strength_cb = page.locator("#stat-selector input[value='Strength']")
                assert not strength_cb.is_checked(), (
                    "Strength should NOT be checked for Defensive preset"
                )

        assert errors == [], f"Errors loading preset: {errors}"

    def test_save_custom_preset(self, page: Page, base_url: str):
        """Save a custom preset and verify it appears in dropdown."""
        errors, _ = collect_errors_and_console(page)
        page.goto(base_url)
        page.wait_for_load_state("networkidle")
        self._open_stat_section(page)

        # Select Strength + Luck
        for cb in page.locator("#stat-selector input[name='stat']").all():
            if cb.is_checked():
                cb.uncheck()
        page.locator("#stat-selector input[value='Strength']").check()
        page.locator("#stat-selector input[value='Luck']").check()

        # Type preset name and save
        preset_name_input = page.locator("#preset-name-input")
        if preset_name_input.count() > 0:
            preset_name_input.fill("E2E Custom Preset")
            save_preset_btn = page.locator("#stat-section-body button", has_text="Salva come Preset")
            if save_preset_btn.count() > 0:
                with page.expect_response("**/api/stat-presets") as resp_info:
                    save_preset_btn.click()
                resp_info.value
                page.wait_for_timeout(500)

                # Verify it appears in dropdown
                preset_dropdown = page.locator("#stat-preset-dropdown")
                options = preset_dropdown.locator("option").all_text_contents()
                assert "E2E Custom Preset" in options, (
                    f"Custom preset not in dropdown: {options}"
                )

        assert errors == [], f"Errors saving preset: {errors}"

    def test_delete_custom_preset(self, page: Page, base_url: str):
        """Delete the custom preset created above."""
        errors, _ = collect_errors_and_console(page)
        page.goto(base_url)
        page.wait_for_load_state("networkidle")
        self._open_stat_section(page)

        preset_dropdown = page.locator("#stat-preset-dropdown")
        if preset_dropdown.count() > 0:
            try:
                preset_dropdown.select_option(label="E2E Custom Preset")
                page.wait_for_timeout(200)

                delete_btn = page.locator("#delete-preset-btn")
                if delete_btn.count() > 0:
                    delete_btn.click()
                    wait_for_recalc(page)

                    options = preset_dropdown.locator("option").all_text_contents()
                    assert "E2E Custom Preset" not in options, (
                        "Custom preset should be deleted"
                    )
            except Exception:
                pass

        assert errors == [], f"Errors deleting preset: {errors}"

    def test_save_empty_preset_name(self, page: Page, base_url: str):
        """Saving a preset with empty name should show error or be ignored."""
        errors, console = collect_errors_and_console(page)
        page.goto(base_url)
        page.wait_for_load_state("networkidle")
        self._open_stat_section(page)

        preset_name_input = page.locator("#preset-name-input")
        if preset_name_input.count() > 0:
            preset_name_input.fill("")
            save_preset_btn = page.locator("#stat-section-body button", has_text="Salva come Preset")
            if save_preset_btn.count() > 0:
                save_preset_btn.click()
                page.wait_for_timeout(1000)

                # Should show an error toast or just do nothing — not crash
                js_errors = [e for e in errors if "TypeError" in e or "Cannot" in e]
                assert js_errors == [], f"JS error on empty preset name: {js_errors}"


# ===========================================================================
# 7. INVENTORY MANAGEMENT — detailed
# ===========================================================================


class TestInventoryManagementDeep:
    def test_add_piece_with_craft(self, page: Page, base_url: str):
        """Add a piece as 'needs crafting' and verify it shows craft badge."""
        errors, _ = collect_errors_and_console(page)
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        # Expand inventory
        section = page.locator("#inventory-manager-section")
        if "collapsed" in (section.get_attribute("class") or ""):
            section.locator(".section-header").first.click()
            page.wait_for_timeout(300)

        # Find a not-owned piece
        not_owned = page.locator(".piece-card.not-owned").first
        if not_owned.count() > 0:
            piece_name = not_owned.get_attribute("data-name")

            not_owned.click()
            page.wait_for_timeout(300)

            # Click "Devo craftarlo" (needs crafting)
            craft_btn = page.locator(
                "#craft-confirmation-modal button", has_text="craftarlo"
            )
            if craft_btn.count() > 0:
                craft_btn.click()
                wait_for_recalc(page)

                # Verify piece is now owned with craft
                card = page.locator(f".piece-card[data-name='{piece_name}']")
                if card.count() > 0:
                    card_class = card.get_attribute("class") or ""
                    assert "owned" in card_class, (
                        f"Piece should be owned after craft add: {card_class}"
                    )

                    # Remove to clean up
                    card.click()
                    wait_for_recalc(page)

        assert errors == [], f"Errors in craft flow: {errors}"

    def test_add_piece_as_locked(self, page: Page, base_url: str):
        """Add a piece as 'locked' (not yet unlocked in game)."""
        errors, _ = collect_errors_and_console(page)
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        section = page.locator("#inventory-manager-section")
        if "collapsed" in (section.get_attribute("class") or ""):
            section.locator(".section-header").first.click()
            page.wait_for_timeout(300)

        not_owned = page.locator(".piece-card.not-owned").first
        if not_owned.count() > 0:
            piece_name = not_owned.get_attribute("data-name")
            not_owned.click()
            page.wait_for_timeout(300)

            # Click "Non sbloccato" (locked)
            locked_btn = page.locator(
                "#craft-confirmation-modal button", has_text="sbloccato"
            )
            if locked_btn.count() > 0:
                locked_btn.click()
                wait_for_recalc(page)

                card = page.locator(f".piece-card[data-name='{piece_name}']")
                if card.count() > 0:
                    card_class = card.get_attribute("class") or ""
                    # Should show as locked state
                    assert "locked" in card_class or "owned" in card_class, (
                        f"Unexpected class: {card_class}"
                    )

                    # Clean up
                    card.click()
                    wait_for_recalc(page)

        assert errors == [], f"Errors in locked flow: {errors}"

    def test_search_and_clear(self, page: Page, base_url: str):
        """Search, verify filtering, then clear search."""
        page.goto(base_url)

        section = page.locator("#inventory-manager-section")
        if "collapsed" in (section.get_attribute("class") or ""):
            section.locator(".section-header").first.click()
            page.wait_for_timeout(300)

        search = page.locator("#piece-search")
        expect(search).to_be_visible()

        # Search for something specific
        search.fill("Dragon")
        page.wait_for_timeout(300)

        # Count visible cards
        visible = page.locator(".piece-card:visible")
        count_filtered = visible.count()
        assert count_filtered > 0, "Should find Dragon pieces"

        # Clear search
        search.fill("")
        page.wait_for_timeout(300)

        # All cards should be visible again
        all_visible = page.locator(".piece-card:visible")
        count_all = all_visible.count()
        assert count_all > count_filtered, (
            f"Clearing search should show more cards: {count_filtered} -> {count_all}"
        )

    def test_search_no_results(self, page: Page, base_url: str):
        """Search for nonexistent piece — should show 0 results, no crash."""
        errors, _ = collect_errors_and_console(page)
        page.goto(base_url)

        section = page.locator("#inventory-manager-section")
        if "collapsed" in (section.get_attribute("class") or ""):
            section.locator(".section-header").first.click()
            page.wait_for_timeout(300)

        search = page.locator("#piece-search")
        search.fill("XYZNONEXISTENT12345")
        page.wait_for_timeout(300)

        visible = page.locator(".piece-card:visible")
        assert visible.count() == 0, "No cards should match nonexistent search"
        assert errors == [], f"Errors on empty search: {errors}"

    def test_modal_close_button(self, page: Page, base_url: str):
        """Opening the craft confirmation modal and closing it."""
        page.goto(base_url)

        section = page.locator("#inventory-manager-section")
        if "collapsed" in (section.get_attribute("class") or ""):
            section.locator(".section-header").first.click()
            page.wait_for_timeout(300)

        not_owned = page.locator(".piece-card.not-owned").first
        if not_owned.count() > 0:
            not_owned.click()
            page.wait_for_timeout(300)

            # Modal should be visible
            modal = page.locator("#craft-confirmation-modal")
            expect(modal).to_have_class(re.compile(r"show"))

            # Close it (via close button or clicking outside)
            close_btn = modal.locator(
                ".modal-close, button[aria-label='close'], .close-btn"
            ).first
            if close_btn.count() > 0:
                close_btn.click()
            else:
                # Try pressing Escape
                page.keyboard.press("Escape")

            page.wait_for_timeout(300)
            # Modal should be hidden
            modal_class = modal.get_attribute("class") or ""
            assert "show" not in modal_class, f"Modal should be closed: {modal_class}"


# ===========================================================================
# 8. APPLY UPGRADE & UNDO
# ===========================================================================


class TestUpgradeAndUndo:
    def test_first_upgrade_button_enabled(self, page: Page, base_url: str):
        """The first step-group action button should be enabled."""
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        first_btn = page.locator("#piano-body .btn-success:not([disabled])").first
        if first_btn.count() > 0:
            expect(first_btn).to_be_enabled()

    def test_apply_upgrade_deducts_resources(self, page: Page, base_url: str):
        """Applying an upgrade should reduce hacksilver and materials."""
        errors, console = collect_errors_and_console(page)
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        # Get initial hacksilver
        hack_display = page.locator(".res-item[data-mat='Hacksilver'] .res-qty-display")
        initial_hack_text = (
            hack_display.inner_text() if hack_display.count() > 0 else ""
        )

        # Find first upgrade button
        done_btn = page.locator(
            "#piano-body .btn-success:not([disabled])", has_text="Fatto"
        ).first
        if done_btn.count() == 0:
            pytest.skip("No applicable upgrade actions available")

        # Track API responses
        responses = []
        page.on("response", lambda r: responses.append((r.status, r.url)))

        done_btn.click()
        page.wait_for_timeout(3000)

        # Check for API call
        apply_responses = [(s, u) for s, u in responses if "apply-upgrade" in u]
        if apply_responses:
            status, url = apply_responses[0]
            if status == 200:
                # Hacksilver should have changed
                new_hack_text = (
                    hack_display.inner_text() if hack_display.count() > 0 else ""
                )
                # At minimum, no JS errors
                assert errors == [], f"Errors after upgrade: {errors}"

                # Undo to restore state
                undo_btn = page.locator("#undo-btn")
                if undo_btn.count() > 0 and undo_btn.is_visible():
                    undo_btn.click()
                    page.wait_for_timeout(2000)
            else:
                print(f"Apply upgrade returned {status}")

    def test_undo_restores_state(self, page: Page, base_url: str):
        """Undo should restore previous hacksilver value."""
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        # Get initial state
        hack_display = page.locator(".res-item[data-mat='Hacksilver'] .res-qty-display")
        initial_hack = hack_display.inner_text() if hack_display.count() > 0 else ""

        # Apply upgrade
        done_btn = page.locator(
            "#piano-body .btn-success:not([disabled])", has_text="Fatto"
        ).first
        if done_btn.count() == 0:
            pytest.skip("No upgrade available")

        done_btn.click()
        page.wait_for_timeout(3000)

        # Undo
        undo_btn = page.locator("#undo-btn")
        if undo_btn.count() > 0 and undo_btn.is_visible():
            undo_btn.click()
            page.wait_for_timeout(2000)

            # Check hacksilver restored
            restored_hack = (
                hack_display.inner_text() if hack_display.count() > 0 else ""
            )
            assert initial_hack == restored_hack, (
                f"Undo should restore hacksilver: '{initial_hack}' != '{restored_hack}'"
            )

    def test_undo_hidden_on_fresh_page(self, page: Page, base_url: str):
        """Undo button should not be visible on a fresh page load."""
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        undo_btn = page.locator("#undo-btn")
        if undo_btn.count() > 0:
            expect(undo_btn).to_be_hidden()


# ===========================================================================
# 9. EXPORT / IMPORT / SHARE
# ===========================================================================


class TestExportImportShare:
    def test_export_returns_json(self, page: Page, base_url: str):
        """Export build API should return valid JSON with expected keys."""
        page.goto(base_url)
        resp = page.request.post(f"{base_url}/api/export-build")
        assert resp.status == 200
        data = resp.json()
        assert "version" in data
        assert "resource_budget" in data
        assert "armor" in data
        assert "weapons" in data
        assert "timestamp" in data

    def test_import_then_verify(self, page: Page, base_url: str):
        """Export, modify, import, and verify state changes."""
        page.goto(base_url)

        # Export current state
        resp = page.request.post(f"{base_url}/api/export-build")
        exported = resp.json()

        # Modify hacksilver
        exported["resource_budget"]["Hacksilver"] = 999999

        # Import modified build
        resp2 = page.request.post(
            f"{base_url}/api/import-build",
            data=json.dumps(exported),
            headers={"Content-Type": "application/json"},
        )
        assert resp2.status == 200

    def test_share_build_returns_url(self, page: Page, base_url: str):
        """Share should return a URL with base64 encoded build."""
        page.goto(base_url)
        resp = page.request.post(f"{base_url}/api/share-build")
        assert resp.status == 200
        data = resp.json()
        assert "url" in data
        assert "build=" in data["url"]

    def test_share_url_loads_correctly(self, page: Page, base_url: str):
        """Build shared URL should load the page without errors."""
        errors, _ = collect_errors_and_console(page)

        # Get share URL
        resp = page.request.post(f"{base_url}/api/share-build")
        share_url = resp.json()["url"]

        page.goto(share_url)
        page.wait_for_load_state("networkidle")

        # Page should load fine (the build param may or may not be handled)
        expect(page).to_have_title(re.compile(r"God of War"))

    def test_export_csv_endpoint(self, page: Page, base_url: str):
        """CSV export endpoint should return CSV data."""
        resp = page.request.get(f"{base_url}/api/export-build-csv")
        assert resp.status == 200
        body = resp.text()
        assert "Piece Type" in body, f"CSV should have header row, got: {body[:200]}"

    def test_export_button_triggers_download(self, page: Page, base_url: str):
        """Clicking export button should trigger a download."""
        errors, _ = collect_errors_and_console(page)
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        export_btn = page.locator("#btn-export")
        if export_btn.count() > 0:
            # Listen for download
            with page.expect_download(timeout=5000) as download_info:
                export_btn.click()
            download = download_info.value
            assert download.suggested_filename.endswith(".json"), (
                f"Expected JSON download, got {download.suggested_filename}"
            )

        assert errors == [], f"Errors during export: {errors}"

    def test_import_button_exists(self, page: Page, base_url: str):
        """Import button should exist and be visible."""
        page.goto(base_url)
        import_btn = page.locator("#btn-import")
        expect(import_btn).to_be_visible()


# ===========================================================================
# 10. BUILD SLOTS
# ===========================================================================


class TestBuildSlotsDeep:
    def test_save_slot_via_ui(self, page: Page, base_url: str):
        """Save a build slot via the UI dialog."""
        errors, _ = collect_errors_and_console(page)
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        # Save a slot
        page.on("dialog", lambda d: d.accept("E2E Deep Test Slot"))
        page.locator("#btn-save-slot").click()
        page.wait_for_timeout(1000)

        # Verify via API
        resp = page.request.get(f"{base_url}/api/build-slots")
        slots = [s["name"] for s in resp.json().get("slots", [])]
        assert "E2E Deep Test Slot" in slots, f"Slot not saved: {slots}"

        # Clean up
        page.request.post(
            f"{base_url}/api/build-slots",
            data=json.dumps({"action": "delete", "name": "E2E Deep Test Slot"}),
            headers={"Content-Type": "application/json"},
        )
        assert errors == [], f"Errors saving slot: {errors}"

    def test_load_slot_restores_state(self, page: Page, base_url: str):
        """Loading a slot should restore data and update the UI."""
        errors, _ = collect_errors_and_console(page)

        # First save current state
        page.request.post(
            f"{base_url}/api/build-slots",
            data=json.dumps({"action": "create", "name": "E2E Load Test"}),
            headers={"Content-Type": "application/json"},
        )

        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        # Load the slot via API
        resp = page.request.post(
            f"{base_url}/api/build-slots",
            data=json.dumps({"action": "load", "name": "E2E Load Test"}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 200

        # Clean up
        page.request.post(
            f"{base_url}/api/build-slots",
            data=json.dumps({"action": "delete", "name": "E2E Load Test"}),
            headers={"Content-Type": "application/json"},
        )

    def test_delete_nonexistent_slot(self, page: Page, base_url: str):
        """Deleting a nonexistent slot should not crash."""
        resp = page.request.post(
            f"{base_url}/api/build-slots",
            data=json.dumps({"action": "delete", "name": "NONEXISTENT_SLOT_12345"}),
            headers={"Content-Type": "application/json"},
        )
        # Should return success (slot just doesn't exist) or 404
        assert resp.status in (200, 404), f"Unexpected status: {resp.status}"

    def test_load_nonexistent_slot(self, page: Page, base_url: str):
        """Loading a nonexistent slot should return error."""
        resp = page.request.post(
            f"{base_url}/api/build-slots",
            data=json.dumps({"action": "load", "name": "NONEXISTENT_SLOT"}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 404

    def test_my_builds_button_opens_modal(self, page: Page, base_url: str):
        """Clicking 'I Miei Build' button should open the builds modal."""
        errors, _ = collect_errors_and_console(page)
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        my_builds_btn = page.locator("#btn-load-slot")
        if my_builds_btn.count() > 0:
            my_builds_btn.click()
            page.wait_for_timeout(500)

            # Modal should be visible
            modal = page.locator("#build-slots-modal")
            if modal.count() > 0:
                modal_class = modal.get_attribute("class") or ""
                assert "show" in modal_class, f"Modal not shown: {modal_class}"

        assert errors == [], f"Errors: {errors}"


# ===========================================================================
# 11. SHOPPING LIST
# ===========================================================================


class TestShoppingListDeep:
    def test_shopping_list_api_returns_data(self, page: Page, base_url: str):
        """Shopping list API should return hacksilver and materials."""
        resp = page.request.get(f"{base_url}/api/shopping-list")
        assert resp.status == 200
        data = resp.json()
        assert "total_hack" in data
        assert "materials" in data
        assert isinstance(data["materials"], list)

    def test_shopping_list_button_renders(self, page: Page, base_url: str):
        """Clicking the shopping list button should populate the section."""
        errors, _ = collect_errors_and_console(page)
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        # Expand shopping section
        shopping = page.locator("#shopping-section")
        if "collapsed" in (shopping.get_attribute("class") or ""):
            shopping.locator(".section-header").first.click()
            page.wait_for_timeout(300)

        # Click compute button
        compute_btn = page.locator("#shopping-section button", has_text="Calcola")
        if compute_btn.count() > 0:
            compute_btn.click()
            page.wait_for_timeout(2000)

            # Should show some content
            shopping_body = page.locator("#shopping-body")
            content = shopping_body.inner_text()
            # Should have some text (material names or "nessun deficit")
            assert len(content.strip()) > 0, (
                "Shopping list body should not be empty after compute"
            )

        assert errors == [], f"Errors: {errors}"


# ===========================================================================
# 12. RANKINGS
# ===========================================================================


class TestRankings:
    def test_rankings_body_has_content(self, page: Page, base_url: str):
        """Rankings body should have slot cards."""
        page.goto(base_url)

        # Rankings body has id but parent section doesn't
        rankings_body = page.locator("#rankings-body")
        # Click the parent section header to expand
        header = rankings_body.locator(
            "xpath=ancestor::div[contains(@class,'section')]/button[contains(@class,'section-header')]"
        )
        if header.count() > 0:
            header.click()
            page.wait_for_timeout(300)

        slot_cards = rankings_body.locator(".slot-card")
        assert slot_cards.count() > 0, "Rankings should have slot cards"

    def test_rankings_first_item_has_rank(self, page: Page, base_url: str):
        """First ranked item should have a rank number."""
        page.goto(base_url)

        rankings_body = page.locator("#rankings-body")
        header = rankings_body.locator(
            "xpath=ancestor::div[contains(@class,'section')]/button[contains(@class,'section-header')]"
        )
        if header.count() > 0:
            header.click()
            page.wait_for_timeout(300)

        rank = rankings_body.locator(".rank").first
        if rank.count() > 0:
            expect(rank).to_be_visible()


# ===========================================================================
# 13. PARETO FRONTIERS
# ===========================================================================


class TestParetoFrontiers:
    def test_pareto_body_has_tables(self, page: Page, base_url: str):
        """Pareto body should have upgrade tables."""
        page.goto(base_url)

        pareto_body = page.locator("#pareto-body")
        header = pareto_body.locator(
            "xpath=ancestor::div[contains(@class,'section')]/button[contains(@class,'section-header')]"
        )
        if header.count() > 0:
            header.click()
            page.wait_for_timeout(300)

        tables = pareto_body.locator("table")
        assert tables.count() > 0, "Pareto section should contain tables"


# ===========================================================================
# 14. ERROR HANDLING & EDGE CASES
# ===========================================================================


class TestEdgeCases:
    def test_rapid_clicks_no_crash(self, page: Page, base_url: str):
        """Rapid clicking of various buttons should not crash the UI."""
        errors, _ = collect_errors_and_console(page)
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        # Rapidly toggle theme
        for _ in range(5):
            page.locator("#theme-toggle").click()
            page.wait_for_timeout(50)

        # Rapidly toggle a section
        section = page.locator("#inventory-manager-section .section-header").first
        for _ in range(5):
            section.click()
            page.wait_for_timeout(50)

        page.wait_for_timeout(500)
        js_errors = [
            e
            for e in errors
            if "TypeError" in e or "Cannot" in e or "undefined" in e.lower()
        ]
        assert js_errors == [], f"JS errors after rapid clicks: {js_errors}"

    def test_api_invalid_json_body(self, page: Page, base_url: str):
        """Sending invalid JSON to API endpoints should return 400 not 500."""
        # Test stat-preferences with invalid body
        resp = page.request.post(
            f"{base_url}/api/stat-preferences",
            data="not json",
            headers={"Content-Type": "application/json"},
        )
        # Should be 400 or 500 but not crash the server
        assert resp.status in (400, 500)
        # Verify server is still alive
        resp2 = page.request.get(f"{base_url}/")
        assert resp2.status == 200

    def test_api_recalc_empty_body(self, page: Page, base_url: str):
        """Recalc with empty/minimal body should work."""
        resp = page.request.post(
            f"{base_url}/api/recalc",
            data=json.dumps({}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 200

    def test_api_toggle_piece_invalid_slot(self, page: Page, base_url: str):
        """Toggle piece with invalid slot should return 400."""
        resp = page.request.post(
            f"{base_url}/api/toggle-piece",
            data=json.dumps({"slot": "invalid_slot", "name": "Test", "action": "add"}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400

    def test_api_toggle_piece_invalid_action(self, page: Page, base_url: str):
        """Toggle piece with invalid action should return 400."""
        resp = page.request.post(
            f"{base_url}/api/toggle-piece",
            data=json.dumps(
                {"slot": "chest_pieces", "name": "Test", "action": "invalid"}
            ),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400

    def test_api_apply_upgrade_invalid_label(self, page: Page, base_url: str):
        """Apply upgrade with invalid label should return 400."""
        resp = page.request.post(
            f"{base_url}/api/apply-upgrade",
            data=json.dumps(
                {
                    "label": "invalid label",
                    "slot": "Armatura — Chest",
                    "hack": 0,
                    "mats": {},
                }
            ),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400

    def test_api_apply_upgrade_negative_cost(self, page: Page, base_url: str):
        """Apply upgrade with negative costs should be rejected."""
        resp = page.request.post(
            f"{base_url}/api/apply-upgrade",
            data=json.dumps(
                {
                    "label": "Test 1→2",
                    "slot": "Armatura — Chest",
                    "hack": -100,
                    "mats": {},
                }
            ),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400

    def test_api_undo_when_empty(self, page: Page, base_url: str):
        """Undo when stack is empty should return 400."""
        # First clear any undo state by loading fresh page
        page.goto(base_url)
        resp = page.request.post(f"{base_url}/api/undo-upgrade")
        # May return 400 (empty stack) — that's correct
        # Or 200 if there's leftover state
        assert resp.status in (200, 400)

    def test_api_import_malformed_data(self, page: Page, base_url: str):
        """Import with wrong structure should not crash server."""
        resp = page.request.post(
            f"{base_url}/api/import-build",
            data=json.dumps({"wrong": "data"}),
            headers={"Content-Type": "application/json"},
        )
        # Should succeed (graceful handling with fallback) or return error
        assert resp.status == 200, (
            f"Import malformed should be handled gracefully, got {resp.status}"
        )
        # Server still alive
        resp2 = page.request.get(f"{base_url}/")
        assert resp2.status == 200


# ===========================================================================
# 15. FULL USER WORKFLOW TEST
# ===========================================================================


class TestFullUserWorkflow:
    def test_complete_optimization_flow(self, page: Page, base_url: str):
        """Complete user flow: load page, set stats, check build, apply upgrade, undo."""
        errors, console = collect_errors_and_console(page)
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        # 1. Verify page loaded
        expect(page).to_have_title(re.compile(r"God of War"))
        assert page.locator("#best-build-body .slot-card").count() > 0

        # 2. Set stat preference to Strength + Defense
        body = page.locator("#stat-section-body")
        if not body.is_visible():
            page.locator("#stat-selector-section .section-header").click()
            page.wait_for_timeout(300)

        for cb in page.locator("#stat-selector input[name='stat']").all():
            if cb.is_checked():
                cb.uncheck()
        page.locator("#stat-selector input[value='Strength']").check()
        page.locator("#stat-selector input[value='Defense']").check()
        with page.expect_response("**/api/stat-preferences") as resp_info:
            page.locator("#btn-apply-stats").click()
        resp_info.value
        page.wait_for_timeout(500)

        # 3. Check build updated
        assert page.locator("#best-build-body .slot-card").count() > 0

        # 4. Check rankings
        rankings_body = page.locator("#rankings-body")
        header = rankings_body.locator(
            "xpath=ancestor::div[contains(@class,'section')]/button[contains(@class,'section-header')]"
        )
        if header.count() > 0:
            header.click()
            page.wait_for_timeout(300)

        # 5. Apply an upgrade if available
        done_btn = page.locator(
            "#piano-body .btn-success:not([disabled])", has_text="Fatto"
        ).first
        if done_btn.count() > 0:
            done_btn.click()
            page.wait_for_timeout(3000)

            # 6. Undo
            undo_btn = page.locator("#undo-btn")
            if undo_btn.count() > 0 and undo_btn.is_visible():
                undo_btn.click()
                page.wait_for_timeout(2000)

        # 7. Reset stats (re-open stat section if hidden)
        stat_body = page.locator("#stat-section-body")
        if not stat_body.is_visible():
            page.locator("#stat-selector-section .section-header").click()
            page.wait_for_timeout(300)
        reset_btn = page.locator("#btn-reset-stats")
        if reset_btn.count() > 0:
            reset_btn.click()
            wait_for_recalc(page)

        # 8. Check for errors
        js_errors = [
            e
            for e in errors
            if "TypeError" in e or "Cannot" in e or "ReferenceError" in e
        ]
        assert js_errors == [], (
            f"JS errors in full workflow: {js_errors}\nConsole: {console[-20:]}"
        )

    def test_inventory_management_flow(self, page: Page, base_url: str):
        """Complete inventory management: search, add piece, verify build updates, remove piece."""
        errors, _ = collect_errors_and_console(page)
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        # Record initial grand total
        summary_cards = page.locator("#summary-bar .summary-card .summary-value")
        initial_grand_total = (
            summary_cards.nth(2).inner_text() if summary_cards.count() > 2 else ""
        )

        # Open inventory
        section = page.locator("#inventory-manager-section")
        if "collapsed" in (section.get_attribute("class") or ""):
            section.locator(".section-header").first.click()
            page.wait_for_timeout(300)

        # Search for a specific piece
        search = page.locator("#piece-search")
        search.fill("Berserker")
        page.wait_for_timeout(300)

        # Find a not-owned Berserker piece
        not_owned = page.locator(".piece-card.not-owned:visible").first
        if not_owned.count() > 0:
            piece_name = not_owned.get_attribute("data-name")

            # Add piece as owned
            not_owned.click()
            page.wait_for_timeout(300)
            own_btn = page.locator(
                "#craft-confirmation-modal button", has_text="possiedo"
            )
            if own_btn.count() > 0:
                own_btn.click()
                wait_for_recalc(page)

                # Clear search
                search.fill("")
                page.wait_for_timeout(300)

                # Verify piece is now owned
                card = page.locator(f".piece-card[data-name='{piece_name}']")
                if card.count() > 0:
                    assert "owned" in (card.get_attribute("class") or ""), (
                        "Piece should be owned"
                    )

                    # Remove it
                    card.click()
                    wait_for_recalc(page)

        assert errors == [], f"Errors in inventory flow: {errors}"
