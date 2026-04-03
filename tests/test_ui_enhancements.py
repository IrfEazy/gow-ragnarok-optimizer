"""Tests for UI/UX enhancements (accessibility, mobile, loading states)."""

import pytest

from gow_optimizer import web


def test_generate_loading_state_returns_spinner_markup():
    """RED: Should generate HTML markup for loading spinner."""
    markup = web.generate_loading_spinner("Calculating optimal build...")

    assert "spinner" in markup.lower() or "loading" in markup.lower()
    assert "Calculating optimal build..." in markup


def test_generate_error_alert_markup():
    """RED: Should generate accessible error alert HTML."""
    markup = web.generate_error_alert("Build data is invalid")

    assert "error" in markup.lower() or "alert" in markup.lower()
    assert "Build data is invalid" in markup
    assert "role=" in markup or "aria-" in markup  # Accessibility attributes


def test_generate_success_message_markup():
    """RED: Should generate success message HTML."""
    markup = web.generate_success_message("Build saved successfully!")

    assert "success" in markup.lower()
    assert "Build saved successfully!" in markup


def test_button_has_aria_label_for_accessibility():
    """RED: Should generate buttons with ARIA labels."""
    button = web.generate_button("Save", "Save current build")

    assert 'aria-label=' in button or 'title=' in button
    assert "Save" in button


def test_form_field_has_label_association():
    """RED: Should generate form fields with proper label association."""
    field = web.generate_form_field("build_name", "Build Name", "Enter a name")

    assert "label" in field.lower()
    assert "build_name" in field
    assert "Enter a name" in field


def test_mobile_responsive_grid_layout():
    """RED: Should generate responsive grid classes."""
    layout = web.generate_responsive_grid(["Item 1", "Item 2", "Item 3"])

    # Should contain responsive grid indicators
    assert "grid" in layout.lower() or "flex" in layout.lower()
    assert "Item 1" in layout
    assert "Item 3" in layout


def test_tooltip_with_accessible_content():
    """RED: Tooltips should have accessible descriptions."""
    tooltip = web.generate_tooltip("Hover text", "Detailed explanation")

    assert "Hover text" in tooltip or "tooltip" in tooltip.lower()
    assert "Detailed explanation" in tooltip or "aria-" in tooltip


def test_keyboard_navigation_focus_indicators():
    """RED: Should support keyboard navigation with focus indicators."""
    markup = web.generate_focusable_element("Click me")

    assert "tabindex" in markup or "focusable" in markup.lower()
    assert "outline" in markup.lower() or "focus" in markup.lower()


def test_color_contrast_validation_for_text():
    """RED: Should validate color contrast meets WCAG standards."""
    # Test that function validates proper contrast
    valid = web.validate_color_contrast("#FFFFFF", "#000000")  # White on black
    assert valid is True

    invalid = web.validate_color_contrast("#FFFF00", "#FFFF00")  # Yellow on yellow
    assert invalid is False


def test_generate_notification_center_markup():
    """RED: Should generate notification UI that works on mobile."""
    notifications = [
        {"type": "error", "message": "Error loading data"},
        {"type": "success", "message": "Build saved"},
    ]

    markup = web.generate_notification_center(notifications)

    assert "Error loading data" in markup
    assert "Build saved" in markup
