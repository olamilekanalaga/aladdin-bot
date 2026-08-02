# Current Status

## Implementation matrix

| Component | Status | Evidence | Current behaviour | Missing work | Risk |
|---|---|---|---|---|---|
| Main collector | Implemented but incomplete | `vlak_long_run_collector.py:VlakLongRunCollector.run` | Starts polling/WebSocket, outcomes, heartbeat and daily summary tasks | Missing imported module blocks a clean checkout at startup | Critical onboarding blocker |
| Vlak polling | Operational in code | `fetch_signals`, `polling_loop` | Calls `GET /api/signals`; first response becomes baseline; later unseen keys are saved | No automated integration test | Upstream response shape and availability |
| Vlak WebSocket | Operational in code | `ws_url_with_key`, `websocket_loop` | Connects with API key, parses messages, reconnects with exponential delay | Endpoint protocol not documented by fixture | Duplicate delivery if upstream identifiers are unstable |
| Task supervision | Operational in code | nested `supervise` in `run` | Restarts crashed polling/WebSocket loops | Outcome and daily tasks are not supervised by the same wrapper | Silent task death remains possible outside ingestion tasks |
| Alert normalisation | Implemented but currently broken in checkout | `aladdin_research_engine/normalizers.py` | Maps alternate payload keys into canonical alert fields | Imports missing `aladdin_research_engine.db` | Collector import fails |
| Raw alert persistence | Operational in code | `save_alert` | Stores raw JSON, hash, first-seen metrics, metric snapshot and schedule | No fixture test; raw payload retention unbounded | Database growth and sensitive payload retention |
| Alert deduplication | Operational in code | `raw_payload_hash UNIQUE`, `signal_key`, first-mint query | Deduplicates payloads and tracks duplicate notification count | No cross-process test | Hash/notification semantics depend on upstream stability |
| Outcome API client | Operational in code | `fetch_outcome` | Calls `GET /api/signal/{mint}/outcome`, retries three times, backs off on 429 | No contract test | Upstream failures delay milestones |
| Outcome truth | Operational in code | `save_outcome`, `upsert_latest_outcome` | Preserves maximum ATH/multiple with SQL `MAX`; updates current MC | Outcome completion semantics depend on API | Incorrect API values can become preserved maxima |
| Pre-survivor polling | Operational in code | `PRE_SURVIVOR_POLL_SECONDS=15`, `schedule_next_pre_survivor_check` | Rechecks every 15 seconds until survivor state or completion | High API-cost guardrail is hard-coded | Cost/rate-limit pressure |
| Post-Telegram polling | Operational in code | active polling methods and constants | Checks every 2 minutes while active; inactive after 30 minutes without buy growth; 12-hour long tail | Buy-count availability is variable | Activity state can remain unresolved when buy count is missing |
| Public Telegram gate | Operational in code | `FIRST_ALERT_MIN_MULTIPLE=1.4`, `FIRST_ALERT_MAX_MULTIPLE=2.5`, `process_mint` | One first alert per mint in the live window; late tokens suppressed | Thresholds are hard-coded | Rule changes require code release |
| Telegram formatting | Operational in code | `format_root_message`, `format_milestone_message` | Sends photo when available, text fallback, links and buy button | No snapshot tests | Markdown escaping regressions |
| Telegram deduplication | Operational in code | `telegram_survivor_threads` PK and milestone unique constraint | Claims root before send; one row per mint; one row per mint/threshold | Failed root claim may leave `root_message_id=NULL` and block retry | Lost alert after transient Telegram failure |
| Historical replay protection | Operational in code | live-state and shadow-exclusion methods | Suppresses pre-live root alerts; milestone cutoff at 2026-07-10 | Cutoff is hard-coded and reason string says above 3x while cap is 2.5x | Confusing operations and future migrations |
| Daily Top Gains | Operational in code | `daily_top_gains_loop` | At 23:59 London, sends top five >=5x tokens first seen that day | No catch-up scheduler if process is down at 23:59 | Missed daily summary |
| SQLite migration | Operational | `migrate_vlak_long_run_schema.py:migrate` | Creates 18 base tables with WAL | Migration is a monolithic `CREATE IF NOT EXISTS` script; no version table | Weak upgrade/rollback discipline |
| Runtime-created tables | Implemented but incomplete | Telegram `ensure_shadow_alerts_table`; collector daily table | Creates shadow/config and daily-summary tables at runtime | Schema ownership split across modules | Schema drift |
| Survivor research table | Experimental | `vlak_survivor_research.py` | Derives one row per mint crossing 1.4x and outcome labels | Mixes current research fields with outcome-derived fields | Leakage if used carelessly |
| Alert-entry feature matrix | Experimental | `vlak_alert_entry_feature_matrix.py` | Combines alert-time features with future outcome labels | `create_table(reset=True)` drops/rebuilds table by default | Destructive if run against the live DB without intent |
| Metric snapshot store | Implemented but incomplete | `vlak_research_metrics_store.py` | Normalises metric payloads and milestones | Also depends on missing normalizer import | Backfill/startup failure |
| Shadow Strong Watch | Deprecated/inactive | `process_snapshot_a_shadow_candidates` returns `0` | Candidate processor deliberately disabled | Dead code and tables remain | Maintainer confusion |
| CatBoost shadow scoring | Planned but missing | dynamic import in `send_root_alert` | Import is attempted after a root alert and caught on failure | `survivor_stage_ml_shadow.py` and model artifacts are absent | Warning on each root alert; no scoring |
| Automated tests | Planned but missing | no test directory or test dependency | None | Unit, contract, migration and Telegram tests | High regression risk |
| HTTP API/UI | Planned but missing/absent | no FastAPI/Flask/Streamlit route in tracked files | None | Product owner decision | Not a current runtime capability |
| Redis/PostgreSQL/Rust/Vulcan | Absent | no crates, migrations, clients, streams or handlers | None | Not part of this repository | Do not document as implemented |
| Deployment automation | Planned but missing | no Dockerfile, service unit, workflow or cloud config | Manual Python execution only | Reproducible service deployment | Process availability depends on operator machine |

## What can currently be run

- `migrate_vlak_long_run_schema.migrate(temp_path)` was verified and created 18 SQLite tables.
- `python -m compileall` was verified successfully.
- The clean collector import was tested and fails because `aladdin_research_engine/db.py` is missing.

## What is not connected

- CatBoost shadow scorer.
- Any web API or UI.
- Any external database or queue.
- Any continuous deployment or service manager.

## Current blockers

1. Restore or replace the missing `aladdin_research_engine.db.json_dumps` dependency.
2. Add an integration smoke test that imports and starts the collector in dry-run mode.
3. Decide how failed Telegram root claims should retry.
4. Move schema ownership and hard-coded operational thresholds into controlled configuration/migrations.

