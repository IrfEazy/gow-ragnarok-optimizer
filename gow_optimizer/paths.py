"""Project-relative path helpers.

This module makes CLI and web entry points independent from the current
working directory.
"""

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_PATH = PROJECT_ROOT / "config.yaml"
WEB_INVENTORY_PATH = PROJECT_ROOT / "web_inventory.yaml"
TEMPLATES_DIR = PACKAGE_DIR / "templates"


def resolve_project_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path
