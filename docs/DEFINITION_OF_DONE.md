# Definition of Done

A Vlak Bot engineering change is done only when all applicable items below are satisfied.

## Scope and decision impact

- The changed trading decision is named: buy/avoid, ranking, timing, position size, monitoring, or none.
- Scope and non-goals are explicit.
- Production and research behaviour are separated.
- Threshold or Telegram changes have product-owner approval.

## Code and tests

- New/changed behaviour has deterministic unit tests.
- API changes have fixtures for valid, missing, malformed and error payloads.
- Idempotency and duplicate-delivery cases are tested.
- Time-based logic uses controlled timestamps.
- Full compile/import/smoke suite passes from a clean checkout.

## Data and database

- Writer, reader and authority table are identified.
- Migration is versioned, idempotent and tested on a production-shaped copy.
- Before/after row counts and invariants reconcile.
- No raw evidence or historical maximum is silently lost.
- Outcome/future fields are excluded from timestamp-safe inputs.

## Error handling and observability

- Timeouts, retries and terminal failure states are defined.
- Failures are visible in logs/health metrics without exposing secrets.
- API failure is not converted into a losing token.
- An operator can detect and recover the failure.

## Compatibility and rollback

- Existing database/schema compatibility is documented.
- Rollback steps and previous version are recorded.
- Rollback cannot trigger historical Telegram replay.
- Data written by the new version remains understandable or has a down migration.

## Security

- No secrets, tokens, private keys, live database, or raw production export is committed.
- Credential-shaped literal scan passes.
- New dependencies are justified and reviewed.
- Public-repository IP exposure is considered.

## Deployment verification

- Dry-run succeeds first.
- One controlled live event is verified only with approval.
- Duplicate process protection remains active.
- Signal freshness, outcome freshness, error count and Telegram result are checked.

## Documentation and acceptance

- Relevant `/docs` files and root README are updated.
- Commands and paths were verified.
- Acceptance criteria are shown with evidence, not assertion.
- Reviewer and product owner sign off where required.

