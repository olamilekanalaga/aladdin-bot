# Engineering Guardrails

## Production and Telegram

- Default to dry-run for development.
- Never test against the public chat without explicit approval.
- Preserve one root alert per mint and one send record per milestone marker.
- Any replay must have an explicit time boundary and send-disabled mode.
- Do not alter public thresholds, formatting, late cap or milestone cadence inside an unrelated change.

## Secrets

- Keep `.env` untracked.
- Never print API keys or bot tokens; use redacted startup logs.
- Do not place credentials in fixtures, docs, issue text or SQL dumps.
- Rotate a credential immediately if committed anywhere in Git history.

## Production data

- Never delete or truncate raw alerts, outcomes or Telegram ledgers without written approval and a verified backup.
- Do not copy a live SQLite file while writes are active unless using SQLite's backup mechanism and including WAL state correctly.
- Treat raw payloads as potentially sensitive operational data.

## Migrations and destructive SQL

- Back up and test against a production-shaped copy first.
- Make migrations idempotent and versioned.
- Report row counts and invariant checks before/after.
- Do not run `vlak_alert_entry_feature_matrix.create_table(reset=True)` against production casually; it drops the table.
- Never use destructive Git or filesystem commands to hide migration mistakes.

## Canonical identity and baseline

- Mint is the token identity.
- Preserve the earliest trusted first-spotted timestamp and first-call market cap.
- Do not silently replace first-seen baseline with current MC, survivor MC or a later API value.
- Resolve conflicting mints/pairs explicitly; pair address is not the canonical token key.

## Outcome and multiplier integrity

- Current values may change in either direction.
- ATH and maximum multiple may only stay the same or increase unless a documented data-correction migration proves the old value invalid.
- API errors and missing data are not losing outcomes.
- Future outcome fields must never enter alert-time feature inputs.

## Replay and backfill

- Separate calculation from Telegram sending.
- Cache/source-tag recovered data.
- Make work idempotent by mint, source and event key.
- Dry-run the exact candidate count and date range.
- Provide stop/resume and bounded retry.

## Authority ownership

- Raw receipt authority: raw alert/outcome tables.
- Operational outcome authority: `vlak_token_outcomes`.
- Send authority: Telegram thread/milestone tables.
- Schedule authority: tracking/active polling tables.
- Research tables are never production authority by default.

## Wallet and P&L calculations

Wallet state and P&L are absent. If added, define token quantities, fees, decimals, cost-basis method, realised/unrealised boundaries, transfer treatment and timestamp authority before publishing values.

## Deployment

- One collector process per database/API stream.
- Use a managed restart policy only after duplicate-process and replay tests pass.
- Persist database, WAL/backups and configuration outside ephemeral storage.
- Deployment must include health checks, log retention, secret injection and rollback.

## Rollback

Every production change needs:

- previous commit/version;
- schema compatibility statement;
- data backup location;
- commands to disable new behaviour;
- confirmation that rollback cannot replay historical Telegram alerts.

## Missing safeguards

- No CI tests or secret scan.
- No versioned migration framework.
- No formal backup/recovery command.
- No health endpoint/service manager.
- No root-send recovery state machine.
- No declared foreign keys.

