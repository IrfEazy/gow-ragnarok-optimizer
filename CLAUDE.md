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

## GitHub Issues and Pull Requests

### Creating and Linking Issues with PRs

**Standard workflow for features and bug fixes:**

1. **Create the GitHub Issue** (if not already open)
   ```bash
   gh issue create --title "Brief description of feature or bug" \
     --body "## Description
   Detailed explanation of what needs to be done.
   
   ## Acceptance Criteria
   - [ ] Criterion 1
   - [ ] Criterion 2
   - [ ] All tests passing"
   ```
   This creates issue #N (note the issue number)

2. **Create a feature branch** (naming convention: `feat/`, `fix/`, `refactor/`, etc.)
   ```bash
   git checkout -b feat/short-description main
   ```

3. **Make commits with proper linking**
   - Make real changes to the codebase (not empty commits)
   - Include `Closes #N` in commit message to auto-link the issue:
   ```bash
   git commit -m "feat: Add feature description
   
   Detailed explanation of changes.
   
   Closes #N
   
   Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
   ```

4. **Push the branch and create a PR**
   ```bash
   git push -u origin feat/short-description
   ```
   
   Then create the PR with proper linking:
   ```bash
   gh pr create --title "feat: Feature title" \
     --body "## Summary
   Brief summary of changes.
   
   ## Related Issue
   Closes #N
   
   ## Acceptance Criteria
   - [ ] Criterion 1
   - [ ] Criterion 2
   
   🤖 Generated with [Claude Code](https://claude.com/claude-code)"
   ```

### Pre-Merge Checklist (CRITICAL)

**NEVER merge to main without verifying ALL of these:**

1. ✅ **Sourcery AI Review Comments**
   - Check the PR for comments from `sourcery-ai` bot
   - Read all suggestions and issues raised
   - Address every Sourcery comment before merging
   - Mark comments as resolved once addressed
   - If disagreeing with a suggestion, document your reasoning
   - **Do not merge with unresolved Sourcery comments**
   ```
   Steps:
   1. View the "Conversation" tab on the PR
   2. Look for comments from sourcery-ai
   3. Read each suggestion carefully
   4. Either fix the code or reply explaining why you're not following it
   5. Click "Resolve conversation" once addressed
   ```

2. ✅ **CI/CD Passes**
   - All automated tests pass in the PR checks
   - No flaky tests or intermittent failures
   - If CI fails, fix the code — do not merge
   ```bash
   # Verify locally before pushing
   pytest -xvs
   ```

3. ✅ **No Conflicts with Main**
   - Rebase or merge main into the feature branch to resolve any conflicts
   - Test after resolving conflicts
   ```bash
   git fetch origin
   git rebase origin/main
   # or
   git merge origin/main
   pytest -xvs
   ```

4. ✅ **Code Quality Standards**
   - **New functions have docstrings**: Every new function must have a clear docstring explaining its purpose, parameters, and return value
   - **Tests verify functionality**: New code must have corresponding tests; test coverage should be >80%
   - **No test placeholders**: Don't commit tests for unimplemented functions (TDD red phase tests are OK locally, but don't merge red tests to main)
   - **Code is formatted correctly**: Follow PEP 8 for Python; use existing code style as reference
   - **No debugging artifacts**: Remove `print()`, `console.log()`, debugger statements, and commented-out code

5. ✅ **All Tests Pass** (both new and existing)
   ```bash
   pytest                          # All tests pass
   pytest -v                       # View full output
   pytest --cov                    # Check coverage (if available)
   ```

6. ✅ **Main Branch Health**
   - After merging, verify main branch still works:
   ```bash
   git checkout main
   git pull origin main
   pytest -xvs
   ```
   - If tests fail after merge, revert immediately and fix the issue

### Merge Process

7. **When merging the PR to main** (after pre-merge checklist passes)
   ```bash
   git checkout main
   git merge --ff-only feat/short-description
   git push origin main
   ```
   
   The `Closes #N` in the commit automatically closes the issue when merged.

8. **Clean up after merge and verify**
   - Delete the feature branch:
   ```bash
   git push origin --delete feat/short-description
   # or
   gh pr close N --delete-branch
   ```
   - Verify main branch is still healthy:
   ```bash
   git checkout main
   git pull origin main
   pytest -xvs
   ```
   - Verify issue closed and PR merged:
   ```bash
   gh issue list --state open    # Linked issue should be gone
   gh pr list --state open       # PR should be gone
   ```
   - **If any tests fail after merge**: Revert the merge immediately
   ```bash
   git revert <merge-commit-hash>
   git push origin main
   ```

### Critical Rule: Main Branch Must Always Be Deployable

**The main branch must NEVER have failing tests.** This is non-negotiable.

**Common mistakes that break this rule:**
- ❌ Merging tests for unimplemented functions (TDD red phase tests belong locally, not in main)
- ❌ Committing code without corresponding tests
- ❌ Merging without running full test suite locally
- ❌ Ignoring CI/CD failures
- ❌ Committing placeholder functions without implementation
- ❌ Merging incomplete features with scaffolding code

**If main branch breaks:**
1. Immediately revert the breaking commit/PR
2. Fix the issue on a feature branch
3. Re-test thoroughly before attempting merge again
4. Document what went wrong in the PR description

### Key Points

- **One issue per feature/bug**: Each GitHub issue represents one distinct problem or feature
- **One PR per issue**: Each PR should have exactly one associated issue via `Closes #N`
- **Real commits only**: Don't create empty placeholder commits; implement the feature completely
- **Complete tests only**: Only commit tests for code that exists and passes. Don't commit tests for future/unimplemented functions
- **Consistent linking**: Both commit messages and PR description should reference the issue
- **Auto-closure**: When a PR with `Closes #N` is merged, the issue automatically closes
- **No orphaned issues/PRs**: Before considering work done:
  - ✅ Issue has associated PR
  - ✅ PR has `Closes #N` in title or body
  - ✅ Issue closes automatically when PR merges
  - ✅ Both are in correct state after merge
  - ✅ All tests pass on main branch after merge

### Example Workflow (Complete)

```bash
# 1. Create issue
gh issue create --title "feat: Add caching to API responses" \
  --body "Improve performance by caching expensive computations"
# Output: https://github.com/user/repo/issues/8

# 2. Create branch
git checkout -b feat/api-caching main

# 3. Make changes
# ... implement feature ...

# 4. Commit with issue link
git commit -m "feat: Add caching to API responses

Cache expensive pareto frontier computations for 5 minutes.
Improves response time by 60% for typical usage patterns.

Closes #8

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"

# 5. Push and create PR
git push -u origin feat/api-caching
gh pr create --title "feat: Add caching to API responses" \
  --body "Closes #8

Implements 5-minute cache for pareto frontier calculations."

# 6. After review/testing, merge to main
git checkout main
git merge --ff-only feat/api-caching
git push origin main
# Issue #8 automatically closes

# 7. Clean up
gh pr close 9 --delete-branch
# Verify state
gh issue list --state open  # Issue #8 should not be listed
gh pr list --state open     # PR #9 should not be listed
```

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
