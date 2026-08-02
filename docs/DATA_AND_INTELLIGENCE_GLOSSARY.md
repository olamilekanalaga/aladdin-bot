# Data and Intelligence Glossary

## Core data terms

**Raw event**  
One Vlak signal payload received through polling or WebSocket and stored in `vlak_alert_events.raw_json` with a hash.

**Canonical event**  
No table uses this exact official name. In this repository, the closest equivalent is a normalised alert row produced by `normalize_signal` and stored in `vlak_alert_events`. There is no independent canonical-event service.

**Canonical trade**  
Not implemented. Vlak Bot does not store a transaction ledger or execute trades.

**Canonical identity**  
The Solana token mint is the primary identity used across operational tables. Pair address is metadata, not primary identity.

**First spotted / first Vlak detection**  
The earliest stored Vlak event for a mint. Its first-call market cap is the baseline for multiples.

**Snapshot**  
A point-in-time normalised observation. Alert, metric, API metric and outcome snapshots have different source tables.

**Deduplication**  
Preventing the same logical work from being stored or sent repeatedly. The code uses payload hashes, signal keys, unique schedule labels, one thread per mint, and one milestone per mint/threshold.

## Outcome terms

**Current market cap**  
The latest market cap returned by the outcome API. It may rise or fall.

**ATH market cap**  
The highest market cap preserved by Vlak Bot from available outcome evidence.

**Maximum multiple**  
`ATH market cap / first-call market cap`. The stored value is monotonic.

**Survivor**  
A token that reaches at least `1.4x` from first spotted. Crossing the research survivor threshold does not by itself prove a Telegram message was sent.

**Root alert**  
The first public Telegram message for a mint. Current eligibility is 1.4x through 2.5x plus live/deduplication safeguards.

**Milestone**  
A later multiple such as 2x, 3x, 4x, 5x or 10x, or an additional 0.5x ATH update used for a Telegram reply.

**Completed outcome**  
`completed_24h=1` from normalised API evidence. The repository does not fully document upstream completion semantics.

## Intelligence terms

**Token intelligence**  
Structured token metrics, risk fields, links, and outcomes. There is no separate production token-intelligence service in this repository.

**Participation intelligence**  
Not an authoritative module here. Buys, holders, buy volume and average buy size are available as participation proxies.

**Wallet intelligence**  
Not implemented in this repository. No wallet-level ledger, labels, balances or quality engine is shipped.

**Wallet-token affinity**  
Not implemented.

**Formation**  
A research rule or pattern combining features. Formation logic is not part of the current public Telegram gate in this repository.

**Signal**  
Ambiguous term. It may mean an upstream raw Vlak call or a derived row in `vlak_survivor_signals`. Code and documentation should state which meaning is intended.

**Enrichment**  
Adding information after the raw event, usually through the Vlak outcome endpoint or local derivation. External Solana enrichment is not present in this engine-only repository.

**Shadow state**  
Research-only tracking that should not alter public decisions. Shadow code/tables remain, but candidate processing is disabled.

## State and authority terms

**Authority**  
The source allowed to decide a specific fact. Raw payload tables own evidence; `vlak_token_outcomes` owns current/max operational outcome; Telegram tables own send state.

**Pending data**  
Expected information that has not arrived yet, such as a due outcome refresh.

**Unavailable data**  
Information not supplied or not parseable from the available source. It must not be fabricated.

**Incomplete data**  
A row with known missing fields or an unresolved outcome. API failure is incomplete evidence, not failure of the token.

**Token lifecycle**  
The sequence from first Vlak event through scheduled outcome checks, survivor qualification, Telegram, milestones and completion.

**Wallet state / cost basis / realised P&L / unrealised P&L**  
Not implemented or authoritatively defined in this repository.

