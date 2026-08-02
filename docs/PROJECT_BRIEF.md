# Project Brief

## What Vlak Bot is

Vlak Bot is a single-process Python service that consumes token calls from an external Vlak API, stores the original call and subsequent outcomes in SQLite, and sends selected continuation alerts to Telegram.

The current public decision is simple: a newly observed token may receive one first Telegram alert when its canonical maximum multiple is between `1.4x` and `2.5x`, measured from the first Vlak market-cap baseline. Later progress is sent as threaded milestone replies.

## Problem being solved

Raw Vlak calls contain many weak tokens. Vlak Bot delays public delivery until a token demonstrates continuation, while retaining the raw call and outcome history for audit and research. The trading decisions supported are:

- **Buy or avoid:** whether a token qualifies for the public survivor channel.
- **Timing:** avoid first alerts that are below confirmation or already beyond the late-entry cap.
- **Monitoring:** show later `2x`, `3x`, `4x`, `5x`, and `10x` progress.

## Expected users

- A Telegram trading community receiving public survivor alerts.
- The operator maintaining the collector and Telegram bot.
- Researchers using preserved snapshots and outcomes.
- Developers responsible for ingestion reliability and data integrity.

## Current product boundary

The repository currently contains:

- Vlak polling and WebSocket ingestion.
- SQLite schema and persistence.
- Outcome polling and retry scheduling.
- Telegram root alerts, milestone replies, and deduplication.
- Daily Top Gains Telegram summary.
- Derived survivor and alert-entry research tables.

It does **not** contain a trading execution engine, portfolio manager, sell logic, web API, UI, Redis, PostgreSQL, Rust, Vulcan webhook, or deployment service definition.

## Long-term vision

Repository evidence shows an intended progression from raw alerts to structured survivor research, feature matrices, and shadow intelligence. The exact commercial product, execution model, and final role of ML require `PRODUCT OWNER INPUT REQUIRED`.

## Research versus production

**Production path:** `vlak_long_run_collector.py` -> Vlak API -> SQLite -> `SurvivorTelegramAlerts` -> public Telegram.

**Research/derived path:** `vlak_survivor_research.py`, `vlak_research_metrics_store.py`, and `vlak_alert_entry_feature_matrix.py` build research-friendly records from stored evidence. These tables must not silently become public decision authority.

Shadow Strong Watch structures remain in `vlak_survivor_telegram.py`, but the repository explicitly disables the shadow candidate processor. The optional CatBoost scorer module referenced after root send is absent.

## Explicitly outside current scope

- Automated buying or selling.
- Custody of funds or private keys.
- Profit guarantees.
- Changes to Vlak's upstream detection logic.
- Reconstructing missing historical market data without an approved source.
- Promoting research labels to production without chronological and live-forward validation.

