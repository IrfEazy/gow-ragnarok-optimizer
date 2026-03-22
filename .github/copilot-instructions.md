# Copilot Instructions — God of War Ragnarök Build Optimizer

## Project Overview

Build optimizer for God of War Ragnarök. Scrapes armor/weapon data from IGN wiki, computes optimal upgrade paths using Pareto frontiers and resource-constrained solving, and presents results via CLI and a Flask web UI.

## Tech Stack

- **Python 3.12** with **uv** for dependency management
- **Flask** for the web UI (Norse-themed dark UI, single-page with AJAX)
- **pandas** for data manipulation
- **requests + BeautifulSoup (lxml)** for web scraping
- **PyYAML** for configuration and runtime state
- **Playwright** (via MCP) for browser testing

## Project Structure

```
main.py                     # CLI entry point — runs full optimizer report
config.yaml                 # User configuration (inventory, resources, aliases)
web_inventory.yaml          # Runtime state for web UI (gitignored, auto-seeded from config.yaml)
pyproject.toml              # Project metadata and dependencies
gow_optimizer/              # Main Python package
  __init__.py
  scraper.py                # IGN wiki scraper + CSV loader
  optimizer.py              # Inventory parsing, Pareto frontiers, solver, CLI reports
  web.py                    # Flask app — routes, API endpoints, compute pipeline
  templates/
    index.html              # Single Jinja2 template (includes CSS + JS inline)
data/                       # Scraped CSV data (committed)
  all_pieces.csv            # Armor pieces with stats and upgrade costs
  all_weapons.csv           # Weapon attachments with stats and upgrade costs
notebooks/                  # Jupyter notebooks
  scrape_armor.ipynb        # Original scraping notebook
```

## Key Architectural Patterns

### Two entry points

- **CLI**: `uv run python main.py` — reads `config.yaml`, prints full report to console
- **Web**: `uv run python -m gow_optimizer.web` — Flask on port 5000, reads `config.yaml` for static data and `web_inventory.yaml` for mutable state

### Data flow

- `config.yaml` is the source of truth for initial inventory and is never modified by the app
- `web_inventory.yaml` stores mutable state (piece levels + resource quantities) for the web UI; auto-seeded from `config.yaml` on first access
- CSV files in `data/` contain scraped stats; regenerated only when `force_scrape: true`

### Optimizer label format

Labels follow the regex `^(★craft\+)?(.+?) (\d+)→(\d+)$`:

- `"Spiritual Shoulder Straps 4→5"` — simple upgrade
- `"★craft+Nidavellir's Finest Plackart 2→5"` — craft then upgrade

### Inventory tuples

`parse_inventory_from_config()` returns tuples: `(name, level, slot_type, needs_craft)`

### Piece keys in YAML

`chest_pieces`, `wrist_pieces`, `waist_pieces`, `axe_attachments`, `blades_attachments`, `spear_attachments`, `shield_attachments`

### Slot-to-key mapping

- `"Armatura — Chest/Wrist/Waist"` → `chest_pieces/wrist_pieces/waist_pieces`
- `"Arma — Leviathan Axe/Blades of Chaos/Draupnir Spear/Shield"` → `axe_attachments/blades_attachments/spear_attachments/shield_attachments`

## Run Commands

```bash
uv run python main.py                  # CLI report
uv run python -m gow_optimizer.web     # Web UI (Flask, port 5000)
```

## Conventions

- All imports use package-qualified paths: `from gow_optimizer.optimizer import ...`
- Logging via `logging` module, no `print()` in library code
- YAML files use `allow_unicode=True, sort_keys=False`
- Web UI uses inline CSS/JS in a single Jinja2 template
- Italian language in user-facing strings and UI labels
- All file I/O paths are relative to the workspace root
