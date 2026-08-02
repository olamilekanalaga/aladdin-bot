# Open Decisions

Only decisions that cannot be resolved from repository evidence are listed.

## 1. Production alert objective

- Decision: Is the public channel optimising probability of 2x from first spotted, remaining upside after entry, or another trading target?
- Why it matters: determines gate evaluation and success metrics.
- Evidence: current code uses a 1.4x-2.5x confirmation window; research intent is not authoritative here.
- Options: confirmation quality, remaining opportunity, ranked hybrid.
- Consequence: changes labels, reports and possibly thresholds.
- Owner: product owner.
- Blocking: blocks rule redesign, not reliability work.
- Required answer: What exact trade and outcome should the public alert optimise?

## 2. API source contract and ownership

- Decision: What uptime, rate limit and payload contract does Vlak guarantee?
- Evidence: flexible key aliases and retry logic; no checked-in contract/fixture.
- Options: documented Vlak contract, tolerant adapter with versioning, secondary recovery source.
- Owner: product owner/API owner.
- Blocking: blocks robust contract testing.

## 3. Live operating environment

- Decision: Keep Windows PC operation or move to a managed server?
- Evidence: Windows paths and manual startup; no deployment files.
- Options: Windows service, VPS service, container/cloud worker.
- Consequence: backup, persistence, monitoring and credentials differ.
- Owner: product owner + lead developer.
- Blocking: non-blocking for local reliability; blocking for deployment roadmap.

## 4. Historical data retention

- Decision: How long must raw payloads, snapshots, errors and Telegram ledgers be retained?
- Evidence: no deletion/archive policy.
- Options: indefinite, tiered archive, bounded operational DB plus immutable backup.
- Owner: product owner/data owner.
- Blocking: blocks cleanup automation.

## 5. Research versus production database

- Decision: Should derived research writes remain inline in the live DB/process?
- Evidence: outcome path synchronously upserts research tables; feature rebuild can be destructive.
- Options: keep inline, queue asynchronously, separate read-only research replica.
- Owner: lead developer with research owner.
- Blocking: non-blocking, but important for scale and safety.

## 6. Shadow code disposition

- Decision: remove deprecated Strong Watch code/tables or restore it as a supported experiment?
- Evidence: candidate processor returns zero, yet methods/schema remain.
- Owner: product owner/research owner.
- Blocking: no; affects maintenance clarity.

## 7. Root-send failure semantics

- Decision: retry automatically after a claimed thread has no Telegram message ID?
- Evidence: current path logs and leaves the claim.
- Options: transactional outbox state machine, bounded retry, manual repair.
- Owner: lead developer/product owner.
- Blocking: blocks final fix acceptance criteria.

## 8. Collaborator access and repository visibility

- Decision: keep repository public or private once a developer joins?
- Evidence: repository is currently public; proprietary trading logic is visible although secrets are excluded.
- Owner: product owner.
- Blocking: non-blocking technically; security/IP decision.

