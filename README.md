## God of War Ragnarök Build Optimizer

Applicazione Python 3.12 che combina scraping, ottimizzazione build e interfaccia web Flask.

### Obiettivo

Il progetto legge inventario e risorse, carica i dataset delle armature e degli attachment, costruisce frontiere di Pareto per slot e calcola il piano di upgrade migliore sotto vincoli di Hacksilver e materiali.

### Struttura

- `gow_optimizer/cli.py`: entry point CLI applicativo
- `gow_optimizer/web.py`: app factory Flask e API web
- `gow_optimizer/config.py`: lettura config e stato runtime
- `gow_optimizer/paths.py`: path risolti rispetto alla root del progetto
- `gow_optimizer/optimizer.py`: logica di ranking, Pareto e solver
- `gow_optimizer/scraper.py`: scraping IGN e caricamento CSV
- `gow_optimizer/templates/index.html`: template unico della web UI
- `main.py`: wrapper di compatibilità verso la CLI del package
- `config.yaml`: configurazione sorgente
- `web_inventory.yaml`: stato runtime della UI web
- `tests/`: smoke test essenziali su config e app web

### Avvio

CLI:

```bash
uv run gow-cli
```

Web:

```bash
uv run gow-web
```

Alternativa compatibile:

```bash
uv run python main.py
uv run python -m gow_optimizer.web
```

### Sviluppo

Installazione dipendenze:

```bash
uv sync
```

Test:

```bash
uv run pytest
```

### Note di struttura

- I path dei file non dipendono piu dalla working directory corrente.
- `config.yaml` resta la sorgente di verita iniziale.
- `web_inventory.yaml` continua a essere runtime state separato e gitignored.
- Il retrofit applica una struttura da application template senza introdurre database, auth o frontend build pipeline non necessari.
