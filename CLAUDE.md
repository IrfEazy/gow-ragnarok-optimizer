# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Start

```bash
# Install dependencies
uv sync

# First-time setup: generate CSV data from IGN wiki
python -m gow_optimizer.scraper

# Run tests
pytest

# Run a single test
pytest tests/test_config.py::test_load_config_has_expected_top_level_keys

# Start the web UI
python -m gow_optimizer
# Opens Flask dev server on http://localhost:5000
```

## Project Overview

**God of War Ragnarök — Build Optimizer** is a Flask web application that helps players optimize their armor and weapon builds using Pareto frontier optimization.

### Architecture Layers

1. **Scraper** (`scraper.py`): Parses IGN wiki using BeautifulSoup, extracts armor/weapon stats and upgrade costs, saves to CSV
   - **Entry point**: `python -m gow_optimizer.scraper` (standalone, not called during app startup)
   - Produces: `data/all_pieces.csv`, `data/all_weapons.csv`
   - Functions: `load_csvs()` (reads CSVs), `scrape_and_save()` (web scrape + save)

2. **Optimizer** (`optimizer.py`): Core computation engine
   - **Pareto frontier**: Identifies non-dominated upgrade options per armor/weapon slot
   - **Greedy solver**: Given a Hacksilver budget and materials, finds the best affordable upgrade path
   - **Step-by-step planner**: Recommends sequential upgrades by efficiency (stat gain per Hacksilver)
   - Pure functions, no I/O or Flask dependencies

3. **Web layer** (`web.py`): Flask endpoints + JSON API
   - **Static data cache**: Loads CSVs once, reuses for all requests
   - **4 required reports** (all computed in `_compute_all()`):
     1. **Current optimal build**: Best item for each armor/weapon slot within current inventory
     2. **Optimal plan**: One-shot Pareto optimization with resource constraints
     3. **Step-by-step plan**: Sequential greedy upgrade recommendations
     4. **Blocked items**: Armor/weapons locked by missing materials, plus ranking by total stats
   - **Endpoints**:
     - `GET /` — renders `index.html` with full computed data
     - `POST /api/recalc` — recalculate with modified resource budget (temporary)
     - `POST /api/save-inventory` — persist resources + armor/weapon choices to config.yaml
     - `POST /api/apply-upgrade` — apply a step-by-step upgrade (deduct resources, level up item)

4. **Configuration** (`config.py`): YAML + runtime inventory management
   - Loads `config.yaml`: material aliases, CSV paths, resource budget, inventory state
   - Functions bridge YAML serialization and in-memory data structures
   - Single source of truth: config.yaml (survives app restart)

5. **Paths** (`paths.py`): Resolves all file paths relative to project root, making the app independent of current working directory

### Data Flow

```
config.yaml (persistent state)
    ↓
config.load_web_inventory() → web_data dict
    ↓
web._compute_all(web_data)
    ├─ CSV data (cached): all_pieces_df, all_weapons_df
    ├─ optimizer.build_available_df() → filter inventory to current levels
    ├─ optimizer.collect_current_build() → best item per slot (read-only)
    ├─ optimizer.build_all_pareto() → frontier per slot with mats+costs
    ├─ optimizer.solve_with_resources() → best 1-shot path
    ├─ web._build_step_plan() → greedy sequential path
    └─ web._collect_blocked_items() → items locked by missing materials
    ↓
render_template("index.html", **data)
```

## Code Patterns

### Configuration Inventory

The YAML inventory (e.g., `chest_pieces`) is a list of pieces the player owns:
```yaml
chest_pieces:
  - { name: "Piece Name", level: 5, craft: true }
```

The web UI allows users to:
1. Edit which pieces they own and their current level (persisted to YAML via `save_web_inventory`)
2. Modify resource budget (Hacksilver + materials)

The optimizer then computes upgrade recommendations based on *this* inventory.

### Material Aliases

`mat_aliases` in config.yaml handles typos and pluralization differences in the CSV vs. upgrade costs. Example:
```yaml
mat_aliases:
  Smouldering Embers: Smoldering Embers  # CSV has "Smouldering", costs say "Smoldering"
```

### Pareto Frontier

Each armor/weapon slot has a Pareto frontier: a list of `(hacksilver_cost, total_stats, label, materials_dict)` tuples representing all non-dominated upgrade options.

- Dominated = higher cost but same/lower stats → pruned
- Non-dominated = lower cost, higher stats → kept

The solver picks the best frontier choice per slot that fits the budget and material constraints.

## Key Files & Responsibilities

| File | Lines | Purpose |
|---|---|---|
| `web.py` | ~670 | Flask app, API routes, report computation helpers |
| `optimizer.py` | ~305 | Pareto + greedy solver + inventory parsing |
| `scraper.py` | ~450 | IGN wiki parsing + CSV generation |
| `config.py` | ~84 | YAML load/save, inventory serialization |
| `paths.py` | ~21 | Path resolution helpers |
| `templates/index.html` | ~900 | Single-page app (Jinja2 + vanilla JS) |

## Testing

```bash
pytest                    # Run all tests
pytest -v                 # Verbose output
pytest tests/test_web.py  # Test specific module
pytest -k "armor"         # Run tests matching pattern
```

**Test structure:**
- `tests/test_config.py`: YAML load/save, inventory parsing
- `tests/test_web.py`: API routes, computation pipeline (uses mocked scraper data)

**Important**: Tests monkeypatch `_load_static()` to inject pre-computed CSV dataframes, avoiding expensive web scraping during test runs.

## Git Workflow

- **CSV data** (`data/all_pieces.csv`, `data/all_weapons.csv`) is **not committed**. Users run `python -m gow_optimizer.scraper` to generate it.
- `.gitignore` excludes: `data/`, `__pycache__/`, `.pytest_cache/`, `.venv/`, etc.
- Configuration (`config.yaml`) **is committed** with example inventory + resource budget

## Important Notes

1. **Web UI is the single interface**: No CLI. All user interactions go through the Flask app.

2. **Scraper is standalone**: Called manually, not during app startup. If CSVs are missing, `load_csvs()` raises `FileNotFoundError` with instructions to run the scraper.

3. **All reports are comprehensive**: The single `_compute_all()` computation returns all 4 required reports in one call. The template renders them all on the page.

4. **Italian code comments**: Some variable/function names and comments are in Italian (e.g., `normalize_mat` function comments, `optimizer.py` header). This is intentional domain-specific language for this project.

5. **Material cost tracking**: Upgrade costs are embedded in the CSV (e.g., `Upgrade_Smoldering Embers` column). The optimizer respects these costs when building Pareto frontiers.

## Common Tasks

### Add a new report or metric
1. Add computation logic to `web.py` (typically a new `_build_*()` helper)
2. Add the result to the dict returned by `_compute_all()`
3. Update `tests/test_web.py` to include the new key in `EMPTY_COMPUTE_RESULT`
4. Render it in `templates/index.html`

### Debug the Pareto optimization
- Add temporary `print()` statements to `optimizer.py` or call `_compute_all()` from a test
- The `pareto_data` in the response shows all frontier choices per slot; useful for verifying correctness

### Refresh game data
```bash
python -m gow_optimizer.scraper
```
This re-scrapes the IGN wiki and overwrites the CSVs. The web app will use the new data on next page load.

### Test an API endpoint manually
```bash
curl -X POST http://localhost:5000/api/recalc \
  -H "Content-Type: application/json" \
  -d '{"resource_budget": {"Hacksilver": 5000, "Petrified Bone": 10}}'
```
