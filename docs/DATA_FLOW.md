# Data Flow

This trace follows one mint through the actual code.

## 1. Signal entry

`CollectorConfig.from_env` loads Vlak connection settings. In polling mode, `VlakLongRunCollector.fetch_signals` calls:

```text
GET {VLAK_BASE_URL}/api/signals?apikey=...
```

`polling_loop` treats the first response as a baseline and later compares `signal_key(raw)` values. WebSocket mode instead receives JSON messages from the configured URL and passes each extracted signal to the same save path.

There is no webhook authentication because this repository has no webhook.

## 2. Validation and normalisation

`extract_signal_list` accepts list or wrapped-list payloads. `normalized_alert_metrics` calls `normalize_signal`, then derives holder/tracker fields, market-cap ratios, capture lag, missing fields, and a SHA-256 hash of the raw JSON.

Required practical fields are mint, alert timestamp and first-call market cap. Missing values are recorded rather than silently invented.

## 3. Deduplication and raw writes

`save_alert` opens SQLite with WAL and performs:

1. Determine whether this is the first alert for the mint.
2. Count prior rows with the notification ID.
3. `INSERT OR IGNORE` into `vlak_alert_events` using `UNIQUE(raw_payload_hash)`.
4. Write `vlak_metric_snapshots` and `vlak_api_metric_snapshots`.
5. Write an API audit row.
6. Create scheduled outcome checks.

If the payload hash already exists, the function returns without creating another event.

## 4. Outcome queue and API request

`vlak_tracking_schedule` is the durable due-work table. `outcome_loop` selects due rows plus active Telegram survivors. `process_outcome_for_mint` calls `fetch_outcome`:

```text
GET {VLAK_BASE_URL}/api/signal/{mint}/outcome?apikey=...
```

Transient calls retry with bounded delay. Failures are written to `vlak_ingestion_errors` and `vlak_api_payload_audit`; an API failure is not a losing outcome.

## 5. Outcome persistence

`save_outcome` writes the entire response to `vlak_outcome_snapshots`, a normalised metric record, and milestone evidence. `upsert_latest_outcome` updates `vlak_token_outcomes`.

The key preservation rule is:

```text
saved ATH/multiple = max(existing value, new value)
```

Current market cap can rise or fall; the historical maximum cannot decrease.

## 6. Survivor state and Telegram decision

After persistence, `process_outcome_for_mint` calls `SurvivorTelegramAlerts.process_mint`.

The mint is armed at `1.4x`. A public root alert is eligible only when:

- Telegram is enabled;
- maximum multiple is at least `1.4x` and no greater than `2.5x`;
- qualification happened after the live-start boundary;
- the mint has no thread and no exclusion.

`send_root_alert` inserts `telegram_survivor_threads` first. If the insert succeeds, it formats a MarkdownV2 photo/text message and calls Telegram. The returned message ID is saved and reached thresholds are inserted into `telegram_survivor_milestones`.

## 7. Milestone and active tracking

Once a thread exists, the collector creates `telegram_survivor_active_polling` state. Buy-count growth keeps a mint active. No growth for 30 minutes marks it inactive; missing buy count does not. Active tokens are checked every two minutes, inactive survivors enter a 12-hour long-tail cycle.

`process_mint` compares the saved maximum against fixed thresholds (`2`, `3`, `4`, `5`, `10`) and a 0.5x ATH-update step. The mint/threshold unique constraint suppresses duplicate milestone rows.

## 8. Derived research writes

After each outcome:

- `upsert_survivor_signal` derives a compact survivor record.
- `upsert_alert_entry_row` combines alert-time features with post-alert labels.

These are derived research records, not raw authority. Future labels in the feature matrix must never be used as alert-time inputs.

## Failure paths

| Failure | Recorded response | Recovery |
|---|---|---|
| Signal HTTP failure | ingestion error + payload audit | polling loop sleeps and retries |
| Polling/WebSocket crash | exception log | supervisor restarts task |
| Outcome 429/transient error | bounded retry and error row | schedule remains available |
| Missing buy count | counter increment | token is not marked inactive from missing data alone |
| Telegram root HTTP failure | log; thread claim may remain with null message ID | manual inspection currently required |
| Process restart | SQLite state retained | baseline/live-start protections prevent broad replay |

