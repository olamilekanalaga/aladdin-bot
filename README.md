# Aladdin Bot

> New developer? Start with the [developer onboarding guide](docs/README.md).

This bot receives raw token calls from the Vlak API, records them, checks their performance, and sends selected tokens to Telegram.

The important point is:

> Vlak supplies the original calls. This bot waits for evidence that a call is performing before it sends a Telegram alert.

## What the bot does

1. Requests the latest calls from Vlak.
2. Saves every call and its first-seen market cap in SQLite.
3. Checks each token's outcome through the Vlak outcome endpoint.
4. Calculates the token's multiplier from its original first-seen market cap.
5. Sends one Telegram alert when a new token qualifies between `1.4x` and `2.5x`.
6. Replies to that Telegram alert when later milestones are reached.
7. Preserves snapshots, milestones, maximum market cap, and errors for auditing.

The bot does not create Vlak calls and it does not decide which tokens Vlak initially detects.

## Simple data flow

```text
Vlak API
   |
   | raw token call
   v
Collector -> SQLite database
   |
   | outcome checks
   v
Multiplier calculated from first-seen market cap
   |
   | 1.4x to 2.5x, new live token, not previously sent
   v
Telegram root alert
   |
   | later progress
   v
2x / 3x / 4x / 5x / 10x milestone replies
```

## How the multiplier works

The original Vlak market cap is the baseline.

```text
multiplier = highest market cap observed / first-seen market cap
```

Example:

```text
First-seen market cap: $20,000
Highest market cap:    $28,000
Multiplier:            1.4x
```

The first-seen value is preserved. Later market-cap changes do not replace the original baseline.

## Current Telegram alert rule

A token can receive its first public Telegram alert only when all these conditions are true:

- It is a newly observed live token.
- Its multiplier is at least `1.4x`.
- Its multiplier is no greater than `2.5x`.
- The mint has not already received a root alert.
- Telegram sending is enabled and dry-run mode is off.

Tokens below `1.4x` remain tracked but are not sent.

Tokens first observed above `2.5x` remain stored but are suppressed as late entries.

Only one root Telegram alert is allowed per mint. A unique database record prevents duplicate root messages.

## Why old calls do not flood Telegram after restart

The bot records when live Telegram operation begins. Calls that qualified before that point are treated as historical and are not replayed as new alerts.

The first polling response is also loaded as a baseline. Existing API rows are recorded, but they are not treated as newly arrived calls.

## Milestone replies

After the root alert, the bot can send progress replies for:

- `2x`
- `3x`
- `4x`
- `5x`
- `10x`

It can also send an update when the recorded maximum rises by another `0.5x` beyond the last sent level.

Milestone rows use unique mint-and-threshold records so the same milestone is not intentionally sent twice.

Historical milestone replay is blocked for root alerts created before `2026-07-10 00:00 UTC`. Their data remains in the database.

## Checking frequency

- New Vlak calls: every `10 seconds` by default when polling is enabled.
- Before Telegram qualification: every `15 seconds`.
- After the Telegram root alert: every `2 minutes` while the token is active.
- A token is considered inactive after its buy count has not increased for `30 minutes`.
- Missing or unreadable buy count does not mark a token inactive.
- Inactive tokens return to long-tail checks, currently every `12 hours`.

The current and highest market caps are different values. Current market cap may fall; the saved maximum can only stay the same or increase.

## Daily Telegram summary

At `11:59 PM Europe/London` time, the collector prepares the daily Top Aladdin Gains message.

It ranks up to five tokens first detected that day whose saved maximum multiple reached at least `5x`.

## API endpoints used

The configured Vlak base URL is used for:

```text
GET /api/signals
GET /api/signal/{mint}/outcome
```

The API key is supplied through `.env`. It is never stored in this repository.

The collector supports these signal modes:

- `polling`
- `websocket`
- `both`

Polling is the default.

## Main files

- `vlak_long_run_collector.py` - receives calls, schedules outcome checks, stores results, and runs the service.
- `vlak_survivor_telegram.py` - applies Telegram eligibility, formats messages, prevents duplicates, and sends milestones.
- `migrate_vlak_long_run_schema.py` - creates and upgrades the SQLite tables.
- `vlak_alert_entry_feature_matrix.py` - stores the feature snapshot associated with an alert.
- `vlak_research_metrics_store.py` - stores API metric snapshots and milestones.
- `vlak_survivor_research.py` - stores survivor signal records.
- `aladdin_research_engine/normalizers.py` - converts Vlak payloads into consistent fields.
- `aladdin_research_engine/utils.py` - shared value and timestamp helpers.

## Important database tables

- `vlak_alert_events` - raw Vlak calls and first-seen values.
- `vlak_outcome_snapshots` - each outcome response over time.
- `vlak_token_outcomes` - latest and maximum outcome per mint.
- `vlak_outcome_milestones` - milestone evidence returned by the API.
- `telegram_survivor_threads` - one public root Telegram alert per mint.
- `telegram_survivor_milestones` - Telegram milestone replies already sent.
- `vlak_tracking_schedule` - pending outcome checks.
- `vlak_api_payload_audit` - captured API evidence for debugging.
- `vlak_ingestion_errors` - API and ingestion failures.

## Installation

```powershell
git clone https://github.com/olamilekanalaga/aladdin-bot.git
cd aladdin-bot
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

Open `.env` and enter the private values locally.

## Required settings

```dotenv
VLAK_API_KEY=
VLAK_BASE_URL=
VLAK_SIGNAL_INGEST_MODE=polling
SIGNAL_POLL_SECONDS=10

TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_SURVIVOR_ALERTS_ENABLED=true
TELEGRAM_SURVIVOR_DRY_RUN=false

DATABASE_PATH=vlak_aladdin_research.sqlite
```

Never commit `.env`.


## Railway deployment

Deploy this repository as a Railway worker service, not as a website.

Start command:

```bash
python vlak_long_run_collector.py
```

Attach a Railway persistent volume mounted at `/data` and set:

```dotenv
DATABASE_PATH=/data/vlak_aladdin_research.sqlite
TZ=Europe/London
```

Put real secrets only in Railway Variables. Do not commit `.env`.

Required Railway variables are listed in `.env.example`.
## Starting the bot

```powershell
.venv\Scripts\python.exe vlak_long_run_collector.py
```

Only one collector can run at a time. A local process lock makes a duplicate collector exit instead of sending duplicate alerts.

## Safe first test

Before enabling live Telegram sending, use:

```dotenv
TELEGRAM_SURVIVOR_ALERTS_ENABLED=true
TELEGRAM_SURVIVOR_DRY_RUN=true
```

Check the logs, then set `TELEGRAM_SURVIVOR_DRY_RUN=false` only when ready.

## Failure handling

- Signal polling and WebSocket tasks are supervised and restart after unexpected errors.
- Failed outcome requests retry up to three times with delay.
- HTTP `429` responses trigger a backoff.
- Errors and unsuccessful payloads are recorded for investigation.
- Existing SQLite data is kept across restarts.
- API failures are not treated as token failures.

## What is deliberately not in GitHub

- `.env` and API keys
- Telegram credentials
- SQLite databases
- CSV exports and raw payloads
- Logs and generated reports
- Research experiments
- ML training scripts and model files

This repository is a code backup. Restoring historical data requires a separate private database backup.

