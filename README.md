# Aladdin Vlak Bot Engine

Code-only recovery repository for the live Vlak collection, survivor alert, Telegram, milestone, and outcome-tracking engine.

## Entry point

```powershell
python vlak_long_run_collector.py
```

The collector creates and migrates its SQLite runtime database locally. Runtime databases, credentials, logs, model artifacts, generated reports, and captured payloads are intentionally excluded from Git.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

Populate `.env` locally. Never commit it.

## Engine modules

- `vlak_long_run_collector.py`: live Vlak ingestion, polling, outcome scheduling, milestones, and daily summaries.
- `vlak_survivor_telegram.py`: public survivor alerts, deduplication, milestone replies, and Telegram formatting.
- `migrate_vlak_long_run_schema.py`: canonical runtime database schema and migrations.
- `vlak_alert_entry_feature_matrix.py`: alert-entry feature persistence.
- `vlak_research_metrics_store.py`: metric snapshots and outcome milestone persistence.
- `vlak_survivor_research.py`: survivor signal persistence.
- `aladdin_research_engine/`: shared payload normalization and numeric utilities.

## Not included

Research reports, experiment scripts, dashboards, datasets, SQLite databases, CSV exports, trained models, logs, raw payloads, and API credentials are deliberately excluded.
