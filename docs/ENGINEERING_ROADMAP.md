# Engineering Roadmap

The roadmap prioritises preserving and measuring the current trading edge. New research should not outrank ingestion correctness or alert reliability.

| Priority | Work item | Current evidence | Why it matters | Dependencies | Acceptance criteria |
|---:|---|---|---|---|---|
| P0 | Restore missing normalizer dependency | `normalizers.py` imports absent `.db` | Clean recovery clone cannot start | None | Import and dry-run smoke test pass |
| P0 | Add fixture contract tests | No tests/fixtures | Prevent silent payload and Telegram regressions | Missing module fix | Polling, outcome, normalisation and send tests run offline |
| P0 | Repair root-send claim recovery | Thread inserted before send; null ID blocks retry | Prevents qualified alerts from disappearing | Telegram fixture tests | Failed send can retry once without duplicate successful sends |
| P0 | Add task health supervision | Only polling/WebSocket wrapped | Outcome/daily task may die silently | Logging design | Every long-running task reports health and restarts or stops process clearly |
| P1 | Version SQLite migrations | One monolithic schema plus runtime tables | Safe upgrades and rollback | Schema inventory | Version table, ordered migrations, legacy DB test, rollback/backup steps |
| P1 | Consolidate configuration | Thresholds/cutoffs hard-coded across modules | Reduces conflicting production rules | Product approval | One validated config source with startup log and tests |
| P1 | Build safe SQLite backup/recovery | No command/runbook | Historical outcomes are irreplaceable | Migration versioning | Online backup command and restore drill verified |
| P1 | Add API freshness/health reporting | Logs and audit tables only | Detect upstream outage before missed trades | Task health | Operator can see last signal/outcome success and error rate |
| P1 | Bound raw-data retention | Raw JSON and errors unbounded | Controls DB growth without losing audit value | Product retention decision | Retention/archive policy with protected canonical evidence |
| P2 | Separate operational and research schema ownership | Research writes run inline | Reduces event-loop delay and leakage risk | Tests/migrations | Operational collector can run without destructive research rebuilds |
| P2 | Canonical data contract | Flexible key aliases but no fixtures/version | Protects first-seen and outcome truth | API samples | Versioned schemas and rejected/unknown field reporting |
| P2 | State/lifecycle authority specification | State split across outcome, schedule and Telegram tables | Avoids contradictory states | Schema consolidation | Documented state transitions with invariant tests |
| P2 | Token intelligence quality | Existing metrics and field catalog | Improve buy/avoid ranking only after reliability | Canonical contract | Coverage report and timestamp-safe feature definitions |
| P3 | Wallet intelligence | Absent | Potential future signal quality | Approved provider and identity model | Timestamp-safe wallet data with coverage and provenance |
| P3 | Wallet-token affinity | Absent | Potential ranking edge | Wallet intelligence | Chronological validation proves incremental trading value |
| P3 | Historical formation matching | Not production in repo | Potential alert ranking | Stable feature warehouse | Forward-tested lift with sample size and leakage audit |
| P2 | API/terminal delivery | No API/UI | Useful only if operational need exists | Product owner decision | Read-only authenticated interface with source definitions |
| P1 | Security hardening | `.env` excluded; no CI secret scan | Public repository and live credentials | GitHub workflow | Secret scan, dependency scan and key-rotation runbook |
| P1 | Deployment readiness | Manual PC process only | Uptime directly affects signal capture | Tests/health/backup | Managed service, restart policy, persistent volume and rollback verified |

## Research classification

- Ingestion reliability, tests, recovery and observability: **Direct Trading Edge support** because missed or duplicate alerts directly damage execution.
- Token/wallet intelligence: **Supporting Research** until chronological and live-forward validation shows better decisions.
- New algorithms before reliable data and forward validation: **Distraction**.

