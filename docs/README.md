# Vlak Bot Developer Documentation

This directory is the onboarding and operating reference for Vlak Bot.

## Recommended reading order

1. [PROJECT_BRIEF.md](PROJECT_BRIEF.md) - what Vlak Bot is and is not.
2. [CURRENT_STATUS.md](CURRENT_STATUS.md) - what actually works today.
3. [ARCHITECTURE.md](ARCHITECTURE.md) - services, boundaries, and reliability model.
4. [DATA_FLOW.md](DATA_FLOW.md) - one token from Vlak to SQLite and Telegram.
5. [DATABASE_REFERENCE.md](DATABASE_REFERENCE.md) - tables, writers, and authority.
6. [DATA_AND_INTELLIGENCE_GLOSSARY.md](DATA_AND_INTELLIGENCE_GLOSSARY.md) - project vocabulary.
7. [DEVELOPMENT_SETUP.md](DEVELOPMENT_SETUP.md) - setup, commands, and troubleshooting.
8. [ENGINEERING_GUARDRAILS.md](ENGINEERING_GUARDRAILS.md) - changes that require care or approval.
9. [KNOWN_ISSUES.md](KNOWN_ISSUES.md) - verified defects and risks.
10. [DEVELOPER_SCOPE.md](DEVELOPER_SCOPE.md) and [FIRST_WEEK_CHECKLIST.md](FIRST_WEEK_CHECKLIST.md).
11. [ENGINEERING_ROADMAP.md](ENGINEERING_ROADMAP.md), [OPEN_DECISIONS.md](OPEN_DECISIONS.md), and [PRODUCT_OWNER_QUESTIONS.md](PRODUCT_OWNER_QUESTIONS.md).
12. [DEFINITION_OF_DONE.md](DEFINITION_OF_DONE.md) and [REPOSITORY_MAP.md](REPOSITORY_MAP.md).

## Audit basis

- Repository: `olamilekanalaga/aladdin-bot` (product name: **Vlak Bot**)
- Branch: `main`
- Audited commit: `e0660ba91898eb19120b2367fc8013d52685c2e0`
- Repository audit date: **2026-08-02**
- Scope: all 13 tracked files and approximately 5,100 lines

## Ownership and updates

The product owner owns trading rules, Telegram policy, API access, and production activation. The lead developer owns technical accuracy and should update the relevant document in the same pull request as a behaviour, schema, configuration, or operational change.

Documentation is considered stale when it contradicts code. If behaviour is uncertain, label it `Unknown or unverified`; do not guess.

## Status labels

- **Operational** - connected to the main runtime path and supported by code evidence.
- **Implemented but incomplete** - substantial code exists, but a dependency, test, or reliability gap remains.
- **Experimental** - research-oriented code not suitable as production authority.
- **Shadow-only** - records or scores without changing public decisions.
- **Mocked** - simulated implementation. None found.
- **Planned but missing** - implied by code or product direction but absent.
- **Deprecated** - retained but intentionally inactive.
- **Unknown or unverified** - cannot be proven from this repository alone.

