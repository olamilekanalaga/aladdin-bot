from __future__ import annotations

import sqlite3
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("DATABASE_PATH", str(ROOT / "vlak_aladdin_research.sqlite")))

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS vlak_alert_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    notification_id TEXT,
    mint TEXT NOT NULL,
    symbol TEXT,
    name TEXT,
    alert_time TEXT,
    first_call_market_cap REAL,
    market_cap REAL,
    liquidity REAL,
    volume REAL,
    buys INTEGER,
    holders INTEGER,
    bundle_percent REAL,
    sniper_percent REAL,
    top10_percent REAL,
    source TEXT NOT NULL DEFAULT 'vlak_websocket',
    inserted_at TEXT NOT NULL,
    capture_lag_seconds REAL,
    is_first_alert_per_mint INTEGER NOT NULL DEFAULT 0,
    is_clean_first_snapshot INTEGER NOT NULL DEFAULT 0,
    missing_fields TEXT,
    api_error TEXT,
    duplicate_alert_count INTEGER NOT NULL DEFAULT 0,
    raw_payload_hash TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    UNIQUE(raw_payload_hash)
);

CREATE INDEX IF NOT EXISTS idx_vlak_alert_events_mint_time ON vlak_alert_events(mint, alert_time);
CREATE INDEX IF NOT EXISTS idx_vlak_alert_events_first_clean ON vlak_alert_events(is_first_alert_per_mint, is_clean_first_snapshot);
CREATE INDEX IF NOT EXISTS idx_vlak_alert_events_notification ON vlak_alert_events(notification_id);

CREATE TABLE IF NOT EXISTS vlak_metric_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    notification_id TEXT,
    mint TEXT NOT NULL,
    snapshot_time TEXT NOT NULL,
    snapshot_kind TEXT NOT NULL,
    first_call_market_cap REAL,
    market_cap REAL,
    liquidity REAL,
    price REAL,
    volume REAL,
    buy_volume_sol REAL,
    sell_volume_sol REAL,
    buys INTEGER,
    sells INTEGER,
    holders INTEGER,
    bundle_percent REAL,
    sniper_percent REAL,
    top10_percent REAL,
    liq_to_mc REAL,
    vol_to_mc REAL,
    avg_buy_size_sol REAL,
    max_multiple REAL,
    source TEXT NOT NULL,
    capture_lag_seconds REAL,
    is_clean_snapshot INTEGER NOT NULL DEFAULT 0,
    missing_fields TEXT,
    api_error TEXT,
    raw_payload_hash TEXT NOT NULL,
    raw_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_vlak_metric_snapshots_mint_time ON vlak_metric_snapshots(mint, snapshot_time);
CREATE INDEX IF NOT EXISTS idx_vlak_metric_snapshots_kind ON vlak_metric_snapshots(snapshot_kind);

CREATE TABLE IF NOT EXISTS vlak_outcome_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mint TEXT NOT NULL,
    snapshot_time TEXT NOT NULL,
    current_mc REAL,
    first_call_market_cap REAL,
    ath_market_cap REAL,
    max_multiple REAL,
    liquidity REAL,
    price REAL,
    market_cap REAL,
    updated_at TEXT,
    source TEXT NOT NULL DEFAULT 'vlak_outcome_endpoint',
    api_error TEXT,
    missing_fields TEXT,
    raw_payload_hash TEXT NOT NULL,
    raw_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_vlak_outcome_snapshots_mint_time ON vlak_outcome_snapshots(mint, snapshot_time);
CREATE INDEX IF NOT EXISTS idx_vlak_outcome_snapshots_multiple ON vlak_outcome_snapshots(max_multiple);

CREATE TABLE IF NOT EXISTS vlak_token_outcomes (
    mint TEXT PRIMARY KEY,
    first_alert_time TEXT,
    first_call_market_cap REAL,
    latest_snapshot_time TEXT,
    current_mc REAL,
    ath_market_cap REAL,
    max_multiple REAL,
    hit_2x INTEGER NOT NULL DEFAULT 0,
    hit_5x INTEGER NOT NULL DEFAULT 0,
    hit_10x INTEGER NOT NULL DEFAULT 0,
    rugged INTEGER,
    completed_24h INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    raw_payload_hash TEXT
);

CREATE TABLE IF NOT EXISTS vlak_ingestion_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    source TEXT NOT NULL,
    endpoint TEXT,
    mint TEXT,
    notification_id TEXT,
    error_type TEXT,
    error_message TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    raw_payload_hash TEXT,
    raw_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_vlak_ingestion_errors_time ON vlak_ingestion_errors(occurred_at);
CREATE INDEX IF NOT EXISTS idx_vlak_ingestion_errors_mint ON vlak_ingestion_errors(mint);

CREATE TABLE IF NOT EXISTS vlak_api_payload_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    received_at TEXT NOT NULL,
    source TEXT NOT NULL,
    endpoint TEXT,
    method TEXT,
    mint TEXT,
    notification_id TEXT,
    status_code INTEGER,
    success INTEGER NOT NULL DEFAULT 1,
    api_error TEXT,
    raw_payload_hash TEXT NOT NULL,
    payload_bytes INTEGER,
    top_level_keys TEXT
);

CREATE INDEX IF NOT EXISTS idx_vlak_api_payload_audit_time ON vlak_api_payload_audit(received_at);
CREATE INDEX IF NOT EXISTS idx_vlak_api_payload_audit_hash ON vlak_api_payload_audit(raw_payload_hash);

CREATE TABLE IF NOT EXISTS vlak_tracking_schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mint TEXT NOT NULL,
    first_alert_time TEXT NOT NULL,
    checkpoint_label TEXT NOT NULL,
    checkpoint_minutes REAL NOT NULL,
    due_at TEXT NOT NULL,
    completed_at TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(mint, checkpoint_label)
);

CREATE INDEX IF NOT EXISTS idx_vlak_tracking_schedule_due ON vlak_tracking_schedule(completed_at, due_at);
CREATE INDEX IF NOT EXISTS idx_vlak_tracking_schedule_mint ON vlak_tracking_schedule(mint);


CREATE TABLE IF NOT EXISTS telegram_survivor_armed (
    mint TEXT PRIMARY KEY,
    armed_threshold REAL NOT NULL DEFAULT 1.4,
    armed_multiple REAL,
    armed_at TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'vlak'
);

CREATE INDEX IF NOT EXISTS idx_telegram_survivor_armed_at ON telegram_survivor_armed(armed_at);

CREATE TABLE IF NOT EXISTS telegram_survivor_live_state (
    source TEXT PRIMARY KEY DEFAULT 'vlak',
    survivor_alerts_live_start_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS telegram_survivor_shadow_exclusions (
    mint TEXT PRIMARY KEY,
    reason TEXT NOT NULL,
    first_qualified_at TEXT,
    max_multiple_at_mark REAL,
    survivor_alerts_live_start_at TEXT,
    marked_at TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'vlak'
);

CREATE INDEX IF NOT EXISTS idx_telegram_survivor_shadow_reason ON telegram_survivor_shadow_exclusions(reason);

CREATE TABLE IF NOT EXISTS telegram_survivor_threads (
    mint TEXT PRIMARY KEY,
    chat_id TEXT,
    root_message_id INTEGER,
    first_alert_threshold REAL NOT NULL DEFAULT 1.5,
    first_alert_multiple REAL,
    first_alerted_at TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'vlak'
);

CREATE TABLE IF NOT EXISTS telegram_survivor_milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mint TEXT NOT NULL,
    threshold REAL NOT NULL,
    multiple_at_send REAL,
    telegram_message_id INTEGER,
    sent_at TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'vlak',
    UNIQUE(mint, threshold)
);

CREATE INDEX IF NOT EXISTS idx_telegram_survivor_milestones_mint ON telegram_survivor_milestones(mint);

CREATE TABLE IF NOT EXISTS telegram_entry_outcomes (
    mint TEXT PRIMARY KEY,
    telegram_alerted_at TEXT,
    telegram_entry_multiple REAL,
    telegram_entry_market_cap REAL,
    latest_snapshot_time TEXT,
    current_mc REAL,
    ath_market_cap REAL,
    max_multiple_from_first_spotted REAL,
    max_multiple_from_telegram_entry REAL,
    hit_20pct_after_telegram INTEGER DEFAULT 0,
    hit_50pct_after_telegram INTEGER DEFAULT 0,
    hit_2x_after_telegram INTEGER DEFAULT 0,
    hit_3x_after_telegram INTEGER DEFAULT 0,
    hit_5x_after_telegram INTEGER DEFAULT 0,
    hit_10x_after_telegram INTEGER DEFAULT 0,
    outcome_source TEXT NOT NULL DEFAULT 'derived_from_existing_outcomes',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS telegram_entry_outcome_milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mint TEXT NOT NULL,
    threshold REAL NOT NULL,
    multiple_at_send REAL,
    overall_multiple_at_send REAL,
    telegram_message_id INTEGER,
    sent_at TEXT NOT NULL,
    threshold_observed_at TEXT,
    source TEXT NOT NULL DEFAULT 'telegram_entry',
    UNIQUE(mint, threshold)
);

CREATE INDEX IF NOT EXISTS idx_telegram_entry_outcome_milestones_mint ON telegram_entry_outcome_milestones(mint);

CREATE TABLE IF NOT EXISTS telegram_survivor_active_polling (
    mint TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'active',
    first_alerted_at TEXT,
    last_checked_at TEXT,
    next_due_at TEXT,
    last_buy_count INTEGER,
    last_buy_count_at TEXT,
    no_buy_increase_since TEXT,
    inactive_at TEXT,
    missing_buy_count_count INTEGER NOT NULL DEFAULT 0,
    checks_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_telegram_survivor_active_polling_due ON telegram_survivor_active_polling(status, next_due_at);
CREATE INDEX IF NOT EXISTS idx_telegram_survivor_active_polling_status ON telegram_survivor_active_polling(status);
CREATE TABLE IF NOT EXISTS vlak_survivor_signals (
    mint TEXT PRIMARY KEY,
    token_name TEXT,
    symbol TEXT,
    first_spotted_at TEXT,
    survivor_crossed_at TEXT,
    survivor_threshold REAL NOT NULL,
    root_multiple REAL,
    first_spotted_mc REAL,
    survivor_mc REAL,
    mc_gain_to_root REAL,
    time_since_first_spotted_seconds INTEGER,
    buys_at_survivor INTEGER,
    sells_at_survivor INTEGER,
    holders_at_survivor INTEGER,
    liquidity_at_survivor REAL,
    volume_at_survivor REAL,
    price_at_survivor REAL,
    buy_volume_sol_at_survivor REAL,
    avg_buy_size_sol_at_survivor REAL,
    liq_to_mc_at_survivor REAL,
    vol_to_mc_at_survivor REAL,
    sniper_percent REAL,
    bundler_percent REAL,
    top10_percent REAL,
    dev_sold INTEGER,
    dev_hold_percent REAL,
    dex_paid INTEGER,
    lp_burned_percent REAL,
    mintable INTEGER,
    freezable INTEGER,
    dex_boost_score REAL,
    image_url TEXT,
    website_url TEXT,
    telegram_url TEXT,
    twitter_url TEXT,
    pair_address TEXT,
    factory TEXT,
    created_on TEXT,
    raw_api_source TEXT,
    telegram_sent INTEGER NOT NULL DEFAULT 0,
    telegram_message_id INTEGER,
    shadow_only INTEGER NOT NULL DEFAULT 0,
    pre_live_qualified INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    ath_multiple REAL,
    ath_market_cap REAL,
    hit_2x INTEGER NOT NULL DEFAULT 0,
    hit_3x INTEGER NOT NULL DEFAULT 0,
    hit_5x INTEGER NOT NULL DEFAULT 0,
    hit_10x INTEGER NOT NULL DEFAULT 0,
    time_to_2x_seconds INTEGER,
    time_to_3x_seconds INTEGER,
    time_to_5x_seconds INTEGER,
    time_to_10x_seconds INTEGER,
    latest_outcome_updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_vlak_survivor_signals_crossed ON vlak_survivor_signals(survivor_crossed_at);
CREATE INDEX IF NOT EXISTS idx_vlak_survivor_signals_hits ON vlak_survivor_signals(hit_2x, hit_5x, hit_10x);

CREATE TABLE IF NOT EXISTS vlak_api_field_catalog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint TEXT NOT NULL,
    field_name TEXT NOT NULL,
    example_value TEXT,
    observed_type TEXT,
    stored_in_table TEXT,
    stored_column TEXT,
    notes TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    UNIQUE(endpoint, field_name)
);

CREATE INDEX IF NOT EXISTS idx_vlak_api_field_catalog_endpoint ON vlak_api_field_catalog(endpoint);


CREATE TABLE IF NOT EXISTS vlak_api_metric_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    endpoint TEXT,
    mint TEXT,
    notification_id TEXT,
    observed_at TEXT NOT NULL,
    payload_time TEXT,
    raw_payload_hash TEXT NOT NULL,
    token_name TEXT,
    symbol TEXT,
    image_url TEXT,
    first_call_market_cap REAL,
    market_cap REAL,
    current_mc REAL,
    ath_market_cap REAL,
    max_multiple REAL,
    price_usd REAL,
    liquidity_usd REAL,
    volume_usd REAL,
    volume_1h_usd REAL,
    volume_24h_usd REAL,
    buy_volume_sol REAL,
    sell_volume_sol REAL,
    buys INTEGER,
    sells INTEGER,
    avg_buy_size_sol REAL,
    holders_total INTEGER,
    sniper_percent REAL,
    bundler_percent REAL,
    top10_percent REAL,
    dev_hold_percent REAL,
    dev_sold INTEGER,
    dex_paid INTEGER,
    lp_burned_percent REAL,
    mintable INTEGER,
    freezable INTEGER,
    dex_boost_score REAL,
    website_url TEXT,
    telegram_url TEXT,
    twitter_url TEXT,
    pair_address TEXT,
    factory TEXT,
    created_on TEXT,
    stored_at TEXT NOT NULL,
    UNIQUE(raw_payload_hash)
);

CREATE INDEX IF NOT EXISTS idx_vlak_api_metric_snapshots_mint_time ON vlak_api_metric_snapshots(mint, observed_at);
CREATE INDEX IF NOT EXISTS idx_vlak_api_metric_snapshots_source ON vlak_api_metric_snapshots(source, endpoint);
CREATE INDEX IF NOT EXISTS idx_vlak_api_metric_snapshots_multiple ON vlak_api_metric_snapshots(max_multiple);

CREATE TABLE IF NOT EXISTS vlak_outcome_milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mint TEXT NOT NULL,
    threshold_label TEXT NOT NULL,
    threshold_multiple REAL,
    hit INTEGER NOT NULL DEFAULT 0,
    hit_at TEXT,
    milestone_market_cap REAL,
    first_seen_snapshot_time TEXT,
    latest_snapshot_time TEXT,
    source_raw_payload_hash TEXT,
    source TEXT NOT NULL DEFAULT 'vlak_outcome_endpoint',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(mint, threshold_label)
);

CREATE INDEX IF NOT EXISTS idx_vlak_outcome_milestones_mint ON vlak_outcome_milestones(mint);
CREATE INDEX IF NOT EXISTS idx_vlak_outcome_milestones_hit ON vlak_outcome_milestones(threshold_label, hit, hit_at);
CREATE TABLE IF NOT EXISTS vlak_daily_summaries (
    report_date TEXT PRIMARY KEY,
    generated_at TEXT NOT NULL,
    new_alerts_collected INTEGER NOT NULL DEFAULT 0,
    unique_mints_collected INTEGER NOT NULL DEFAULT 0,
    outcome_snapshots_collected INTEGER NOT NULL DEFAULT 0,
    completed_24h_outcomes INTEGER NOT NULL DEFAULT 0,
    rate_2x REAL,
    rate_5x REAL,
    rate_10x REAL,
    missing_field_rates_json TEXT,
    ingestion_errors INTEGER NOT NULL DEFAULT 0,
    db_size_bytes INTEGER NOT NULL DEFAULT 0,
    last_websocket_message_at TEXT,
    last_outcome_refresh_at TEXT,
    report_markdown TEXT
);
"""


def migrate(db_path: Path = DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        try:
            conn.execute("ALTER TABLE telegram_entry_outcome_milestones ADD COLUMN threshold_observed_at TEXT")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
        conn.commit()


if __name__ == "__main__":
    migrate(DB_PATH)
    print(f"Vlak long-run schema ready: {DB_PATH}")



