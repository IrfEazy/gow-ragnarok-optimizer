# Data Directory

This directory contains the CSV files with God of War Ragnarök armor and weapon data scraped from the IGN wiki.

## Generating the Data

The CSV files in this directory are **not committed to the repository** because they are generated dynamically.

To generate them, run the scraper script:

```bash
python -m gow_optimizer.scraper
```

This will create:

- `all_pieces.csv` — armor pieces (chest, wrist, waist) with stats and upgrade costs
- `all_weapons.csv` — weapon attachments (axes, blades, spears, shields) with stats and upgrade costs

The scraper may take a few minutes as it downloads and parses data from the IGN wiki.

## Data Updates

If the game receives patches that change armor/weapon stats or add new pieces, re-run the scraper to refresh the data:

```bash
python -m gow_optimizer.scraper
```

The web UI will automatically use the updated CSVs on the next page load.
