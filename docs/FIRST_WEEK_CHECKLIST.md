# First Week Checklist

## Day 1: understand and reproduce

- [ ] Clone the repository using [DEVELOPMENT_SETUP.md](DEVELOPMENT_SETUP.md).
- [ ] Read [PROJECT_BRIEF.md](PROJECT_BRIEF.md) and [CURRENT_STATUS.md](CURRENT_STATUS.md).
- [ ] Confirm audited branch/commit with `git status -sb` and `git log -1 --oneline`.
- [ ] Create `.env` from `.env.example` using placeholders/test credentials only.
- [ ] Run `python -m compileall -q .`.
- [ ] Run `python -c "import vlak_long_run_collector"` and reproduce the missing-module blocker.

## Day 2: database and data flow

- [ ] Read [ARCHITECTURE.md](ARCHITECTURE.md), [DATA_FLOW.md](DATA_FLOW.md), and [DATABASE_REFERENCE.md](DATABASE_REFERENCE.md).
- [ ] Create a temporary development SQLite DB with `migrate(Path('dev_vlak.sqlite'))`.
- [ ] Confirm 18 base tables with `sqlite_master`.
- [ ] Trace `fetch_signals -> polling_loop -> save_alert -> process_outcome_for_mint -> process_mint` in code.
- [ ] Identify raw, canonical outcome, schedule, Telegram and research authority tables.

## Day 3: repair packaging and add the first tests

- [ ] Implement the smallest reviewed fix for missing `aladdin_research_engine.db.json_dumps`.
- [ ] Add an import smoke test.
- [ ] Add a signal normalisation fixture with alternate key names.
- [ ] Add an outcome fixture proving ATH/multiple cannot decrease.
- [ ] Keep Telegram dry-run enabled.

## Day 4: Telegram and failure paths

- [ ] Read `vlak_survivor_telegram.py` alongside [ENGINEERING_GUARDRAILS.md](ENGINEERING_GUARDRAILS.md).
- [ ] Test below-1.4, eligible, above-2.5, pre-live and duplicate cases offline.
- [ ] Reproduce the null root-message claim risk with a mocked Telegram failure.
- [ ] Draft a bounded, idempotent recovery design without changing public rules.

## Day 5: propose first production-safe pull request

- [ ] Review [KNOWN_ISSUES.md](KNOWN_ISSUES.md) and [ENGINEERING_ROADMAP.md](ENGINEERING_ROADMAP.md).
- [ ] Select a narrow reliability task.
- [ ] Write scope, non-goals, acceptance criteria and rollback using [DEFINITION_OF_DONE.md](DEFINITION_OF_DONE.md).
- [ ] Confirm product-owner approval for any alert, cadence, schema or replay change.
- [ ] Open a reviewed pull request with tests and documentation updates.

## End-of-week proof

The developer should be able to explain:

- what creates a Vlak Bot alert;
- why first-spotted market cap must not change;
- which tables are authority versus derived;
- how replay and deduplication work;
- what currently prevents a clean clone from running;
- which changes require product-owner approval.

