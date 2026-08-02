# Development Setup

## Prerequisites

- Git.
- Python 3.12 recommended (audit environment: Python 3.12.3).
- Network access to the approved Vlak API and Telegram API.
- A valid Vlak API key.
- Telegram bot token and destination chat ID for live sends.
- Windows is the currently documented operating environment; code is mostly portable but contains Windows-specific default paths.

No Redis, PostgreSQL, Rust toolchain, Node.js, Docker or Vulcan service is required by this repository.

## Clone and virtual environment

```powershell
git clone https://github.com/olamilekanalaga/aladdin-bot.git
cd aladdin-bot
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

The repository declares `httpx`, `python-dotenv`, and `websockets`.

## Environment variables

Never commit real values.

| Variable | Required | Purpose |
|---|---:|---|
| `VLAK_API_KEY` | Yes | Authenticates Vlak HTTP/WebSocket requests |
| `VLAK_BASE_URL` | Yes in clean setup | Base URL for `/api/signals` and outcome endpoint |
| `VLAK_WS_URL` | For websocket/both | WebSocket endpoint |
| `VLAK_SIGNAL_INGEST_MODE` | No | `polling` (default), `websocket`, or `both` |
| `SIGNAL_POLL_SECONDS` | No | Polling interval, default 10 |
| `DATABASE_PATH` | Recommended | SQLite database path |
| `TELEGRAM_BOT_TOKEN` | For Telegram | Bot token |
| `TELEGRAM_CHAT_ID` | For Telegram | Public destination |
| `TELEGRAM_SURVIVOR_ALERTS_ENABLED` | No | Public send switch; default false |
| `TELEGRAM_SURVIVOR_DRY_RUN` | No | Prevents real sends; default true |
| `TELEGRAM_SURVIVOR_TEST_LIMIT` | No | Present in configuration; enforcement not clearly connected |
| `TELEGRAM_SURVIVOR_LIVE_START_AT` | No | Explicit replay boundary; generated at first live run when absent |
| Shadow DM variables | No | Deprecated/inactive shadow code only |

The `.env.example` also lists Solana Tracker and generic strategy variables that are not read by the tracked engine runtime. Treat them as legacy until code evidence changes.

## Known setup blocker

At audited commit `e0660ba`, clean startup fails with:

```text
ModuleNotFoundError: No module named 'aladdin_research_engine.db'
```

`normalizers.py` imports `json_dumps` from that missing module. Restore a minimal reviewed module or move the JSON helper into a shipped module before expecting a clean clone to run. Do not bypass the error by copying an unknown production directory wholesale.

## Database creation

After the missing module is fixed, the collector calls `migrate(DATABASE_PATH)` automatically. A standalone safe check using a temporary path is:

```powershell
.venv\Scripts\python.exe -c "from pathlib import Path; from migrate_vlak_long_run_schema import migrate; migrate(Path('dev_vlak.sqlite'))"
```

Do not run standalone module mains without checking their hard-coded default path. Several research modules default to the operator's historical Windows path.

## Safe start order

1. Confirm `.env` points to a development/test database.
2. Set `TELEGRAM_SURVIVOR_ALERTS_ENABLED=true` and `TELEGRAM_SURVIVOR_DRY_RUN=true`.
3. Run the migration against the development DB.
4. Start the collector:

```powershell
.venv\Scripts\python.exe vlak_long_run_collector.py
```

5. Confirm logs show migration, collector start, ingestion mode and baseline load.
6. Observe database writes and errors before considering a live send.

## Validation commands

```powershell
.venv\Scripts\python.exe -m compileall -q .
.venv\Scripts\python.exe -c "import vlak_long_run_collector"
```

Audit results:

- Compile command: **passed**.
- Temporary migration: **passed**, creating 18 base tables.
- Collector import: **failed** on the missing `aladdin_research_engine.db` module.
- End-to-end API/Telegram test: **not run**, because credentials and network side effects are outside a documentation audit.

## Health checks

There is no HTTP health endpoint. Use:

- process presence;
- `logs/vlak_long_run_collector.log` heartbeat lines;
- recent `vlak_api_payload_audit` rows;
- recent `vlak_outcome_snapshots` rows;
- `vlak_ingestion_errors` count;
- recent `last_outcome_refresh_at` in daily summaries.

## Troubleshooting

**Collector says another process is running**  
Port 49322 is already bound. Identify the existing collector; do not start a second one.

**No raw alerts**  
Check Vlak key/base URL, ingestion mode, `/api/signals` status, audit rows and ingestion errors.

**No Telegram alerts**  
Check enabled/dry-run flags, chat credentials, live-start exclusions, 1.4x-2.5x window and null root claims.

**No milestones**  
Check outcome freshness, active polling state, root date cutoff, existing milestone rows and Telegram errors.

**Database locked/slow**  
Confirm only one collector, inspect long research operations, and avoid copying a live WAL database without a SQLite-safe backup procedure.

## Fixtures and replay

No fixtures, replay CLI or automated tests are shipped. Building them is a recommended first engineering task.

