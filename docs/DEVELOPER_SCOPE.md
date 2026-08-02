# Developer Scope

## First-week objective

**RECOMMENDATION:** Make a clean clone reproducibly importable and testable without changing public trading behaviour.

The first week should end with a fixed missing module, a temporary-database migration test, fixture-based signal/outcome tests, and a dry-run collector smoke test.

## First-month objective

**RECOMMENDATION:** Establish reliability around the existing edge before adding features: contract tests, root-send recovery, task health, schema versioning, backup/replay procedure, and observable API freshness.

## Recommended first task

Restore the missing `aladdin_research_engine.db.json_dumps` dependency with the smallest reviewed implementation, then add an import/smoke test that would have caught the packaging failure.

Why: the code-only recovery repository cannot currently start, so every other developer task rests on an unverified environment.

## Owned components

**PRODUCT OWNER INPUT REQUIRED:** final ownership assignments.

**RECOMMENDATION:** the incoming developer may own:

- dependency and packaging integrity;
- automated tests and fixtures;
- ingestion/outcome reliability;
- SQLite migrations and backup tooling;
- observability and runbooks;
- documentation accuracy.

## Inspect-only components

**VERIFIED FROM REPOSITORY:** these affect trading output and require understanding before change:

- `FIRST_ALERT_MIN_MULTIPLE`, `FIRST_ALERT_MAX_MULTIPLE`;
- milestone thresholds and ATH update step;
- first-spotted market-cap baseline;
- monotonic ATH/multiple preservation;
- Telegram live-start and historical cutoffs;
- active/inactive polling rules.

## Approval-required changes

**RECOMMENDATION:** obtain product-owner approval before changing:

- public Telegram formatting or destination;
- 1.4x/2.5x gates or milestone thresholds;
- polling frequency/API consumption;
- first-seen or multiplier calculations;
- raw data deletion/retention;
- research fields promoted into decisions;
- database migrations on production data;
- replay/backfill that could send Telegram messages;
- credentials, deployment target or network mode.

## Deliverables

- Focused pull request with explicit scope/non-goals.
- Tests demonstrating normal and failure behaviour.
- Database reconciliation query when persistence changes.
- Rollback notes.
- Documentation update.
- Dry-run and, when approved, controlled live verification.

## Review and communication

**RECOMMENDATION:**

- One behaviour change per pull request.
- Product owner reviews trading-rule and Telegram changes.
- Technical reviewer checks data integrity, idempotency and failure recovery.
- Record unresolved architecture choices in `OPEN_DECISIONS.md` or a numbered ADR under `docs/adr/`.
- Report blockers with evidence: command, error, table/query and affected decision.

## Architectural decision records

Use an ADR for changes to database authority, identity, multiplier truth, queueing, deployment, API source, or production alert semantics. Include context, decision, alternatives, consequences, migration and rollback.

