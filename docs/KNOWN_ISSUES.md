# Known Issues

## 1. Clean collector import is broken

- Severity: **Critical**
- Component: normalisation/startup.
- Evidence: `aladdin_research_engine/normalizers.py:6` imports `.db.json_dumps`; `aladdin_research_engine/db.py` is absent.
- Impact: a clean clone raises `ModuleNotFoundError` before the collector starts.
- Detection: `python -c "import vlak_long_run_collector"`.
- Remediation: restore a minimal reviewed `db.py` or move `json_dumps` into a shipped utility; add import test.
- Blocks: onboarding and recovery deployment.

## 2. Optional CatBoost scorer is referenced but absent

- Severity: **Medium**
- Component: post-root shadow scoring.
- Evidence: `send_root_alert` dynamically imports `survivor_stage_ml_shadow`; file/models are not tracked.
- Impact: public alert can still send because exception is caught, but each root may log a scoring warning and no score is produced.
- Remediation: remove the dead hook or ship a separately configured optional package.
- Blocks: shadow scoring only, not intended public delivery.

## 3. Root alert claim can become stuck after send failure

- Severity: **High**
- Component: Telegram delivery.
- Evidence: `send_root_alert` inserts `telegram_survivor_threads` with null message ID before calling Telegram; `process_mint` returns when such a row exists.
- Impact: a qualified token may never receive its root alert after a transient failure.
- Detection: query threads where `root_message_id IS NULL`.
- Remediation: explicit send-state/outbox with bounded retries and idempotency.
- Blocks: production reliability, not onboarding.

## 4. Daily summary has similar pre-send claim risk

- Severity: **Medium**
- Component: daily Top Gains.
- Evidence: summary row is inserted before Telegram call; later runs treat the date as already processed.
- Impact: process/network failure can permanently skip the day's message.
- Detection: summary row with null Telegram message ID.
- Remediation: pending/sent/failed states with retry.

## 5. Late-entry reason contradicts active threshold

- Severity: **Low**
- Component: exclusion diagnostics.
- Evidence: active max is `2.5`; persisted reason is `FIRST_ALERT_TOO_LATE_ABOVE_3X`.
- Impact: reports/operators may misinterpret why a token was suppressed.
- Remediation: migrate to neutral `FIRST_ALERT_TOO_LATE_ABOVE_CAP` plus stored cap.

## 6. Schema default contradicts runtime root threshold

- Severity: **Low**
- Component: `telegram_survivor_threads` schema.
- Evidence: DDL default is 1.5, runtime inserts 1.4 explicitly.
- Impact: manual/incomplete inserts can carry the wrong default.
- Remediation: versioned migration to align default or remove misleading default.

## 7. Schema ownership is split and unversioned

- Severity: **High**
- Component: database migrations.
- Evidence: 18 tables in monolithic migration; shadow/config, daily summary and feature matrix created elsewhere.
- Impact: clean and legacy databases can drift; rollback is unclear.
- Remediation: ordered schema versions and migration tests.

## 8. Research matrix rebuild is destructive by default

- Severity: **High**
- Component: alert-entry research.
- Evidence: `create_table(reset=True)` drops `vlak_alert_entry_feature_matrix`.
- Impact: accidental loss of derived rows and interruption of concurrent readers.
- Remediation: default non-destructive migration; explicit rebuild command on a copy.

## 9. Outcome and daily tasks lack equivalent supervision

- Severity: **Medium**
- Component: process reliability.
- Evidence: polling/WebSocket use `supervise`; outcome, heartbeat and daily loops are plain tasks.
- Impact: an unexpected uncaught exception may stop an important loop while process remains alive.
- Remediation: supervise all critical loops and expose last-success health.

## 10. No automated test suite or fixtures

- Severity: **High**
- Component: repository-wide.
- Evidence: no tests, fixtures or test dependencies are tracked.
- Impact: threshold, payload, database and Telegram regressions can reach production.
- Remediation: begin with import, normalisation, migration, outcome monotonicity and Telegram-state tests.
- Blocks: safe rapid development.

## 11. Hard-coded local paths and operational constants

- Severity: **Medium**
- Component: portability/configuration.
- Evidence: several module defaults point to the operator's Windows path; thresholds/cutoffs are code constants.
- Impact: standalone scripts can target the wrong DB; deployments require edits instead of validated config.
- Remediation: one environment/config object and explicit CLI database argument.

## 12. No deployment, backup or health service definition

- Severity: **High**
- Component: operations.
- Evidence: no Dockerfile, service unit, CI workflow, backup script or health endpoint.
- Impact: uptime and recovery depend on manual operator action.
- Remediation: after tests, add managed service, SQLite-safe backup, health monitor and rollback runbook.

