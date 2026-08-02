# Repository Map

## Recommended code reading order

1. `vlak_long_run_collector.py`
2. `vlak_survivor_telegram.py`
3. `migrate_vlak_long_run_schema.py`
4. `aladdin_research_engine/normalizers.py`
5. `vlak_research_metrics_store.py`
6. `vlak_survivor_research.py`
7. `vlak_alert_entry_feature_matrix.py`

## Root files

### `vlak_long_run_collector.py`

Main executable. Owns configuration, API clients, signal ingestion, raw writes, scheduling, outcome polling, active/inactive tracking, daily summary, task startup and duplicate-process lock.

Active, but clean import is blocked by missing shared module.

### `vlak_survivor_telegram.py`

Public Telegram gate, formatting, replay protection, root/milestone deduplication and Telegram HTTP calls. Also contains dormant shadow Strong Watch code.

Active public path; shadow candidate processor inactive.

### `migrate_vlak_long_run_schema.py`

Monolithic SQLite base schema. Creates 18 tables with `CREATE IF NOT EXISTS`.

Active. Default DB path is operator-specific, so callers should pass an explicit path.

### `vlak_research_metrics_store.py`

Normalises API metric snapshots and milestone labels; provides historical backfill/report helpers.

Active store functions are called inline from collector. Standalone reporting is research-oriented.

### `vlak_survivor_research.py`

Builds one derived survivor row per mint, field catalog and quality summaries.

Experimental research layer, though upsert is called by live outcome processing.

### `vlak_alert_entry_feature_matrix.py`

Selects alert-time snapshot features and computes future post-alert labels.

Experimental. Live upsert is called after outcomes; standalone reset/rebuild is potentially destructive.

### `requirements.txt`

Runtime dependencies: `httpx`, `python-dotenv`, `websockets`. No test dependencies.

### `.env.example`

Configuration template. Contains no secret values. Some Solana/strategy variables are not read by tracked runtime.

### `.gitignore`

Excludes secrets, databases, data, logs, outputs, reports, models and caches.

### `README.md`

Plain-English operator overview. `/docs` is the deeper developer reference.

## Package directory

### `aladdin_research_engine/__init__.py`

Package marker only. The folder retains a historical name; the product is Vlak Bot.

### `aladdin_research_engine/normalizers.py`

Vlak signal/outcome/token-quality normalisation and milestone helpers. Active dependency. Currently imports missing `.db` module.

### `aladdin_research_engine/utils.py`

Shared timestamp, field selection, numeric conversion and display helpers. Active.

## Locations absent from this repository

- No `tests/` or `fixtures/`.
- No Rust workspace/crates.
- No SQL migration directory or PostgreSQL schema.
- No Redis streams/consumers.
- No webhook server.
- No HTTP API server.
- No frontend/terminal UI.
- No deployment configuration.
- No trained models or live database by design.

