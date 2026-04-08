# God of War Ragnarök Build Optimizer

[![CI](https://github.com/IrfEazy/gow-ragnarok-optimizer/actions/workflows/ci.yml/badge.svg)](https://github.com/IrfEazy/gow-ragnarok-optimizer/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/downloads/)

A Python tool to optimize armor and weapon builds in God of War Ragnarök. It scrapes equipment data from the IGN wiki, computes upgrade paths using Pareto frontier optimization, and presents results through an interactive Flask web UI.

## ✨ Features

- **Data Scraping**: Automatically fetch the latest armor and weapon stats from the IGN wiki
- **Pareto Optimization**: Identify non-dominated upgrade choices per armor/weapon slot
- **Resource Solver**: Find the best upgrade path given constraints on Hacksilver and materials
- **Step-by-Step Planning**: Get sequential upgrade recommendations ranked by efficiency (stats per Hacksilver spent)
- **Interactive Web UI**: Manage inventory, adjust resources, apply upgrades in real-time
- **Material Tracking**: See which pieces are blocked by missing materials and what's needed

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/getting-started/) for dependency management

### Installation & Setup

```bash
# Clone the repository
git clone https://github.com/IrfEazy/gow-ragnarok-optimizer.git
cd gow-ragnarok-optimizer

# Install dependencies
uv sync

# Generate CSV data from IGN wiki (first time only)
python -m gow_optimizer.scraper

# Start the web UI
python -m gow_optimizer
```

The web UI will open at **<http://localhost:5000>**.

## 📖 Usage

### Web UI (Recommended)

The web interface provides an interactive way to optimize your build:

1. **Inventory**: Add the armor and weapons you currently own (with their current level)
2. **Resources**: Set your available Hacksilver and crafting materials
3. **Optimization**: View four key reports:
   - **Current Best Build**: Highest-stat item for each slot from your current inventory
   - **Optimal Plan**: Best single-shot upgrade path respecting all constraints
   - **Step-by-Step Plan**: Sequential upgrades ranked by efficiency
   - **Blocked Items**: Pieces locked by missing materials, ranked by total stats
4. **Apply Upgrades**: Click "Apply" on any step to deduct resources and update your inventory

### Data Updates

If the game receives patches that change armor/weapon stats:

```bash
python -m gow_optimizer.scraper
```

The web UI will use the updated data on the next page load.

## 🏗️ Architecture

### Core Components

| Component     | Purpose                                                |
| ------------- | ------------------------------------------------------ |
| **Scraper**   | Parses IGN wiki → generates CSV files                  |
| **Optimizer** | Pareto frontier + greedy solver → upgrade paths        |
| **Web Layer** | Flask app + JSON API → interactive UI                  |
| **Config**    | YAML state management → persistent inventory/resources |

### Data Flow

```text
config.yaml (persistent state)
    ↓
Load inventory & resources
    ↓
Scraper: load CSVs or fetch from web
    ↓
Optimizer: compute Pareto frontiers + plans
    ↓
Web UI: render interactive reports
    ↓
User applies upgrades → updates config.yaml
```

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_web.py

# Run tests matching a pattern
pytest -k "armor"
```

**Test Coverage:**

- Configuration loading and YAML serialization
- Inventory parsing and data validation
- Pareto frontier computation
- Resource-constrained optimization
- Web API endpoints and data mutations

## 📋 Configuration

The app is configured via `config.yaml`:

```yaml
# Load CSV files (if they exist) or scrape from web
force_scrape: false

# CSV file locations
armor_csv: data/all_pieces.csv
weapons_csv: data/all_weapons.csv

# Material name normalization (handles typos/plurals in wiki)
mat_aliases:
  Smouldering Embers: Smoldering Embers
  Petrified Bones: Petrified Bone

# Your inventory (name, level, craft flag)
chest_pieces:
  - { name: "Lunda's Lost Cuirass", level: 5, craft: true }
  - { name: "Spiritual Shoulder Straps", level: 4, craft: true }

# Your resources
resource_budget:
  Hacksilver: 15000
  Petrified Bone: 8
  Smoldering Embers: 5
```

See `config.yaml` in the repo for a complete example.

## 🎮 Game Context

The optimizer is designed for **New Game+ (NG+)** and **Muspelheim** challenges where:

- You own multiple armor pieces and weapon attachments
- Upgrading items requires both **Hacksilver** (primary currency) and **crafting materials**
- Your goal is to reach the best-stat build or maximize stat gains within a resource budget

The **Pareto frontier** for each slot shows all non-dominated upgrade options:

- Dominated = higher cost but same/lower stats → pruned out
- Non-dominated = best bang for buck → included

The **solver** then picks frontier options per slot that fit your total budget while maximizing total stat gain.

## 📂 Project Structure

```text
gow_optimizer/
  ├── web.py              # Flask app, API routes, report computation
  ├── optimizer.py        # Pareto frontiers, greedy solver, inventory parsing
  ├── scraper.py          # IGN wiki scraping, CSV generation
  ├── config.py           # YAML load/save, state management
  ├── paths.py            # Path resolution helpers
  ├── __main__.py         # Entry point: python -m gow_optimizer
  └── templates/
      └── index.html      # Single-page web UI (Jinja2 + inline CSS/JS)

tests/
  ├── test_config.py      # Config loading and serialization
  └── test_web.py         # API endpoints and computation pipeline

data/
  ├── all_pieces.csv      # Armor pieces (generated by scraper)
  └── all_weapons.csv     # Weapon attachments (generated by scraper)

config.yaml               # User configuration (committed)
CLAUDE.md                 # Developer guide for Claude Code
```

## 🛠️ Development

### Common Tasks

**Add a new report:**

1. Write computation logic in `web.py` (e.g., `_build_new_report()`)
2. Add result to dict returned by `_compute_all()`
3. Update `tests/test_web.py` to include it in `EMPTY_COMPUTE_RESULT`
4. Render in `templates/index.html`

**Debug the optimizer:**

- Add print statements to `optimizer.py` functions
- Call `_compute_all()` from a test with known data
- Check `pareto_data` in response to verify frontier choices

**Test an API endpoint:**

```bash
curl -X POST http://localhost:5000/api/recalc \
  -H "Content-Type: application/json" \
  -d '{"resource_budget": {"Hacksilver": 10000}}'
```

### Code Standards

- All file paths are resolved relative to project root (independent of `cwd`)
- Use package-qualified imports: `from gow_optimizer.module import func`
- Configuration is YAML with unicode support
- Tests monkeypatch scraper data to avoid expensive web scraping
- Italian domain language in some comments/variables (intentional)

## 🐛 Troubleshooting

### "FileNotFoundError: data/all_pieces.csv not found"

```bash
python -m gow_optimizer.scraper
```

### CSV data is outdated after game patch

```bash
python -m gow_optimizer.scraper
```

### Web UI shows stale data

- Hard refresh the browser: `Ctrl+Shift+R` (or `Cmd+Shift+R` on Mac)
- Clear browser cache if using the same URL

### Tests fail with network errors

- Tests use mocked CSV data; no network access required
- If failure persists, check that `pytest` is installed: `uv sync --dev`

## 📝 License

This project is provided as-is for personal use and educational purposes.

## 🤝 Contributing

This is a personal project. Contributions are welcome via issues and pull requests!

## 📚 References

- [IGN - God of War Ragnarök Wiki](https://www.ign.com/wikis/god-of-war-ragnarok/)
- Pareto Frontier concept: [Wikipedia](https://en.wikipedia.org/wiki/Pareto_efficiency)
- Flask Web Framework: [flask.palletsprojects.com](https://flask.palletsprojects.com/)
- uv Package Manager: [docs.astral.sh/uv](https://docs.astral.sh/uv/)

---

**Last Updated**: 2026-04-03 | **Python**: 3.12+ | **Status**: Active Development
