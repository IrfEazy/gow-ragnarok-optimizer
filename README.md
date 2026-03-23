## God of War Ragnarök Build Optimizer

[![CI](https://github.com/IrfEazy/gow-ragnarok-optimizer/actions/workflows/ci.yml/badge.svg)](https://github.com/IrfEazy/gow-ragnarok-optimizer/actions/workflows/ci.yml)

Applicazione Python 3.12 per analizzare build, materiali e percorsi di upgrade in God of War Ragnarök.

Il progetto combina:

- caricamento dati da CSV o scraping IGN
- ranking e Pareto frontier per slot
- solver per il piano ottimale sotto vincoli di Hacksilver e materiali
- web UI Flask con stato runtime separato

### Obiettivo

Il tool legge l'inventario disponibile, valuta armature e attachment sbloccati, costruisce le alternative migliori per slot e produce:

- la build migliore raggiungibile con i pezzi correnti
- un piano ottimale globale di upgrade
- una sequenza step-by-step applicabile dalla UI

### Struttura del workspace

- `gow_optimizer/cli.py`: entry point CLI principale
- `gow_optimizer/web.py`: Flask app, rendering pagina e API `/api/*`
- `gow_optimizer/config.py`: lettura di `config.yaml` e gestione di `web_inventory.yaml`
- `gow_optimizer/paths.py`: path assoluti risolti dalla root del repository
- `gow_optimizer/optimizer.py`: ranking, Pareto, solver e parsing inventario
- `gow_optimizer/scraper.py`: scraping IGN e caricamento dataset CSV
- `gow_optimizer/templates/index.html`: template unico con CSS e JS inline
- `gow_optimizer/__main__.py`: supporto a `python -m gow_optimizer`
- `main.py`: wrapper di compatibilità verso la CLI del package
- `config.yaml`: configurazione iniziale e inventario sorgente
- `web_inventory.yaml`: stato runtime della UI web, non versionato
- `data/all_pieces.csv`: dataset armature
- `data/all_weapons.csv`: dataset attachment armi
- `tests/test_config.py`: test sui path e seed dello stato runtime
- `tests/test_web.py`: test su app Flask e mutazioni inventario/risorse
- `notebooks/scrape_armor.ipynb`: notebook storico di scraping

### Avvio

CLI:

```bash
uv run gow-cli
```

Web UI:

```bash
uv run gow-web
```

Alternative equivalenti:

```bash
uv run python main.py
uv run python -m gow_optimizer
uv run python -m gow_optimizer.web
```

### Sviluppo

Installazione dipendenze:

```bash
uv sync
```

Esecuzione test:

```bash
uv run pytest
```

### Stato dei dati

- `config.yaml` resta la sorgente iniziale di inventario e budget risorse.
- `web_inventory.yaml` viene usato dalla UI come stato mutabile separato.
- Se `web_inventory.yaml` non esiste, viene generato automaticamente a partire da `config.yaml`.
- `web_inventory.yaml` è gitignored e non viene pubblicato nel repository.

### Note tecniche

- I path non dipendono dalla working directory corrente.
- Il progetto è configurato come package installabile per `uv`, quindi gli script console `gow-cli` e `gow-web` vengono installati correttamente con `uv sync`.
- Restano comunque supportati anche i comandi basati su `uv run python ...`.
- I test attuali coprono config runtime, bootstrap della web app e mutazioni degli endpoint principali.
