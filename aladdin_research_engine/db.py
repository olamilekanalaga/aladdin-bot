from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .config import settings
from .utils import utc_now_iso

logger = logging.getLogger(__name__)


SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS alerts (
    notification_id TEXT PRIMARY KEY,
    mint TEXT,
    symbol TEXT,
    name TEXT,
    chain TEXT,
    notification_type TEXT,
    sent_at TEXT,
    market_cap REAL,
    first_call_market_cap REAL,
    liquidity REAL,
    price_usd REAL,
    vol_1h REAL,
    vol_24h REAL,
    chg_1h REAL,
    chg_24h REAL,
    total_buy REAL,
    count_buy INTEGER,
    label TEXT,
    sentence TEXT,
    paragraph TEXT,
    factory TEXT,
    pre_factory TEXT,
    total_fee REAL,
    created_at TEXT,
    first_call_time TEXT,
    created_on TEXT,
    raw_json TEXT
);

CREATE TABLE IF NOT EXISTS token_quality_metrics (
    mint TEXT PRIMARY KEY,
    holder_count INTEGER,
    top10_percent REAL,
    dev_hold_percent REAL,
    sniper_hold_percent REAL,
    bundle_hold_percent REAL,
    phishing_hold_percent REAL,
    dex_paid INTEGER,
    dex_boost_score REAL,
    freezable INTEGER,
    mintable INTEGER,
    lp_burned_percent REAL,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS top_holders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mint TEXT,
    wallet TEXT,
    amount REAL,
    percent REAL,
    name TEXT,
    kol_name TEXT,
    kol_twitter TEXT,
    snapshot_time TEXT
);

CREATE TABLE IF NOT EXISTS solana_tracker_enrichment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    notification_id TEXT,
    mint TEXT,
    enriched_at TEXT,
    buy_volume_1m_usd REAL,
    buy_volume_5m_usd REAL,
    buy_volume_10m_usd REAL,
    buy_volume_1m_sol REAL,
    buy_volume_5m_sol REAL,
    buy_volume_10m_sol REAL,
    buy_count_1m INTEGER,
    buy_count_5m INTEGER,
    buy_count_10m INTEGER,
    sell_count_1m INTEGER,
    sell_count_5m INTEGER,
    sell_count_10m INTEGER,
    unique_buyers_1m INTEGER,
    unique_buyers_5m INTEGER,
    unique_buyers_10m INTEGER,
    net_buy_volume_1m REAL,
    net_buy_volume_5m REAL,
    net_buy_volume_10m REAL,
    top_buyer_share_10m REAL,
    raw_json TEXT
);

CREATE TABLE IF NOT EXISTS alert_trade_windows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    notification_id TEXT,
    mint TEXT,
    strategy_name TEXT,
    alert_time TEXT,
    window_label TEXT,
    buy_volume_usd REAL,
    sell_volume_usd REAL,
    net_volume_usd REAL,
    buy_count INTEGER,
    sell_count INTEGER,
    unique_buyers INTEGER,
    unique_sellers INTEGER,
    avg_buy_size_usd REAL,
    top_buyer_share REAL,
    created_at TEXT,
    raw_json TEXT,
    UNIQUE(notification_id, strategy_name, window_label)
);

CREATE TABLE IF NOT EXISTS outcomes (
    mint TEXT PRIMARY KEY,
    call_mc REAL,
    call_at TEXT,
    current_mc REAL,
    ath_mc REAL,
    ath_at TEXT,
    max_multiple REAL,
    outcome_bucket TEXT,
    rugged INTEGER,
    next_milestone REAL,
    updated_at TEXT,
    raw_json TEXT
);

CREATE TABLE IF NOT EXISTS milestone_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mint TEXT,
    milestone REAL,
    multiple REAL,
    mc REAL,
    hit_at TEXT,
    telegram_sent INTEGER,
    telegram_message_id TEXT,
    UNIQUE(mint, milestone)
);

CREATE TABLE IF NOT EXISTS telegram_sent_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_type TEXT,
    notification_id TEXT,
    mint TEXT,
    milestone REAL,
    sent_at TEXT,
    telegram_message_id TEXT
);

CREATE TABLE IF NOT EXISTS alert_filter_metrics (
    notification_id TEXT PRIMARY KEY,
    mint TEXT,
    symbol TEXT,
    filter_name TEXT,
    filter_passed INTEGER,
    market_cap REAL,
    liquidity REAL,
    age_minutes REAL,
    volume_usd REAL,
    buy_volume_sol REAL,
    sell_volume_sol REAL,
    buy_sell_volume_ratio REAL,
    buys INTEGER,
    holders INTEGER,
    unique_buyers REAL,
    top_buyer_share REAL,
    bundle_hold_percent REAL,
    sniper_hold_percent REAL,
    dev_hold_percent REAL,
    top10_percent REAL,
    phishing_hold_percent REAL,
    dex_paid INTEGER,
    lp_burned_percent REAL,
    liq_to_mc REAL,
    vol_to_mc REAL,
    avg_buy_size_sol REAL,
    top10_holder_pct REAL,
    bundle_pct REAL,
    sniper_pct REAL,
    rejection_reason TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS explosive_runner_candidates (
    notification_id TEXT PRIMARY KEY,
    mint TEXT,
    symbol TEXT,
    market_cap REAL,
    liquidity REAL,
    age_minutes REAL,
    volume_usd REAL,
    sol_volume REAL,
    buys INTEGER,
    holders INTEGER,
    liq_to_mc REAL,
    vol_to_mc REAL,
    avg_buy_size_sol REAL,
    top10_holder_pct REAL,
    bundle_pct REAL,
    sniper_pct REAL,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS strategy_evaluations (
    evaluation_id TEXT PRIMARY KEY,
    notification_id TEXT,
    mint TEXT,
    symbol TEXT,
    strategy_name TEXT NOT NULL,
    filter_version TEXT NOT NULL,
    filter_passed INTEGER,
    rejection_reason TEXT,
    market_cap REAL,
    liquidity REAL,
    age_minutes REAL,
    volume_usd REAL,
    sol_volume REAL,
    liq_to_mc REAL,
    vol_to_mc REAL,
    buys INTEGER,
    holders INTEGER,
    top10_holder_pct REAL,
    bundle_pct REAL,
    sniper_pct REAL,
    buy_sell_volume_ratio REAL,
    evaluated_at TEXT,
    raw_metrics_json TEXT,
    UNIQUE(notification_id, strategy_name, filter_version)
);

CREATE INDEX IF NOT EXISTS idx_alerts_mint ON alerts(mint);
CREATE INDEX IF NOT EXISTS idx_alerts_created_on ON alerts(created_on);
CREATE INDEX IF NOT EXISTS idx_enrichment_notification ON solana_tracker_enrichment(notification_id);
CREATE INDEX IF NOT EXISTS idx_trade_windows_notification ON alert_trade_windows(notification_id);
CREATE INDEX IF NOT EXISTS idx_trade_windows_mint ON alert_trade_windows(mint);
CREATE INDEX IF NOT EXISTS idx_trade_windows_strategy ON alert_trade_windows(strategy_name);
CREATE INDEX IF NOT EXISTS idx_milestones_mint ON milestone_events(mint);
CREATE INDEX IF NOT EXISTS idx_filter_metrics_passed ON alert_filter_metrics(filter_passed);
CREATE INDEX IF NOT EXISTS idx_strategy_evaluations_strategy ON strategy_evaluations(strategy_name);
CREATE INDEX IF NOT EXISTS idx_strategy_evaluations_notification ON strategy_evaluations(notification_id);
CREATE INDEX IF NOT EXISTS idx_strategy_evaluations_mint ON strategy_evaluations(mint);
CREATE INDEX IF NOT EXISTS idx_strategy_evaluations_passed ON strategy_evaluations(filter_passed);

-- research_v2_historical = frozen old baseline.
-- research_v2_live = current live version of the old Research V2 filter.
-- early_discovery / continuation_runner / premium_runner / confirmed_runner = experimental filters.
UPDATE strategy_evaluations
SET strategy_name = 'research_v2_historical',
    evaluation_id = REPLACE(evaluation_id, 'research_v2:', 'research_v2_historical:')
WHERE strategy_name = 'research_v2';

INSERT OR IGNORE INTO strategy_evaluations (
    evaluation_id,
    notification_id,
    mint,
    symbol,
    strategy_name,
    filter_version,
    filter_passed,
    rejection_reason,
    market_cap,
    liquidity,
    age_minutes,
    volume_usd,
    sol_volume,
    liq_to_mc,
    vol_to_mc,
    buys,
    holders,
    top10_holder_pct,
    bundle_pct,
    sniper_pct,
    buy_sell_volume_ratio,
    evaluated_at,
    raw_metrics_json
)
SELECT
    'research_v2_historical:' || notification_id,
    notification_id,
    mint,
    symbol,
    'research_v2_historical',
    COALESCE(filter_name, 'ERF-v1'),
    filter_passed,
    rejection_reason,
    market_cap,
    liquidity,
    age_minutes,
    volume_usd,
    buy_volume_sol,
    liq_to_mc,
    vol_to_mc,
    buys,
    holders,
    top10_holder_pct,
    bundle_pct,
    sniper_pct,
    buy_sell_volume_ratio,
    COALESCE(created_at, datetime('now')),
    json_object(
        'source', 'alert_filter_metrics',
        'filter_name', filter_name,
        'avg_buy_size_sol', avg_buy_size_sol,
        'unique_buyers', unique_buyers,
        'top_buyer_share', top_buyer_share
    )
FROM alert_filter_metrics
WHERE notification_id IS NOT NULL
  AND COALESCE(filter_name, '') != 'research_v2_live';

DROP VIEW IF EXISTS strategy_research_view;
CREATE VIEW strategy_research_view AS
SELECT
    se.strategy_name,
    se.filter_version,
    se.notification_id,
    se.mint,
    COALESCE(se.symbol, a.symbol) AS symbol,
    se.filter_passed,
    se.rejection_reason,
    se.market_cap,
    se.liquidity,
    se.age_minutes,
    se.volume_usd,
    se.sol_volume,
    se.liq_to_mc,
    se.vol_to_mc,
    se.buys,
    se.holders,
    se.top10_holder_pct,
    se.bundle_pct,
    se.sniper_pct,
    se.buy_sell_volume_ratio,
    se.evaluated_at,
    se.market_cap AS strategy_alert_market_cap,
    o.ath_mc,
    o.max_multiple AS token_max_multiple,
    CASE
        WHEN se.filter_passed = 1
         AND se.market_cap IS NOT NULL
         AND se.market_cap > 0
         AND o.ath_mc IS NOT NULL
        THEN o.ath_mc / se.market_cap
        ELSE NULL
    END AS strategy_max_multiple,
    o.max_multiple AS max_multiple,
    o.outcome_bucket,
    CASE
        WHEN se.filter_passed != 1
          OR se.market_cap IS NULL
          OR se.market_cap <= 0
          OR o.ath_mc IS NULL
        THEN NULL
        WHEN o.ath_mc / se.market_cap < 2 THEN '<2x'
        WHEN o.ath_mc / se.market_cap < 5 THEN '2x-5x'
        WHEN o.ath_mc / se.market_cap < 10 THEN '5x-10x'
        WHEN o.ath_mc / se.market_cap < 20 THEN '10x-20x'
        ELSE '20x+'
    END AS strategy_outcome_bucket,
    o.rugged
FROM strategy_evaluations se
LEFT JOIN alerts a ON a.notification_id = se.notification_id
LEFT JOIN outcomes o ON o.mint = se.mint
WHERE NOT (
    se.strategy_name = 'research_v2_historical'
    AND se.filter_version = 'research_v2_live'
);

DROP VIEW IF EXISTS strategy_performance_summary;
CREATE VIEW strategy_performance_summary AS
SELECT
    strategy_name,
    COUNT(DISTINCT mint) AS total_tokens,
    COUNT(DISTINCT CASE WHEN filter_passed = 1 THEN mint END) AS passed_tokens,
    COUNT(DISTINCT CASE WHEN COALESCE(filter_passed, 0) = 0 THEN mint END) AS rejected_tokens,
    ROUND(AVG(CASE WHEN filter_passed = 1 THEN CASE WHEN strategy_max_multiple >= 1.5 THEN 1.0 ELSE 0.0 END END), 3) AS hit_1_5x,
    ROUND(AVG(CASE WHEN filter_passed = 1 THEN CASE WHEN strategy_max_multiple >= 1.5 THEN 1.0 ELSE 0.0 END END) * 100, 1) AS hit_1_5x_pct,
    ROUND(AVG(CASE WHEN filter_passed = 1 THEN CASE WHEN strategy_max_multiple >= 2 THEN 1.0 ELSE 0.0 END END), 3) AS hit_2x,
    ROUND(AVG(CASE WHEN filter_passed = 1 THEN CASE WHEN strategy_max_multiple >= 2 THEN 1.0 ELSE 0.0 END END) * 100, 1) AS hit_2x_pct,
    ROUND(AVG(CASE WHEN filter_passed = 1 THEN CASE WHEN strategy_max_multiple >= 5 THEN 1.0 ELSE 0.0 END END), 3) AS hit_5x,
    ROUND(AVG(CASE WHEN filter_passed = 1 THEN CASE WHEN strategy_max_multiple >= 5 THEN 1.0 ELSE 0.0 END END) * 100, 1) AS hit_5x_pct,
    ROUND(AVG(CASE WHEN filter_passed = 1 THEN CASE WHEN strategy_max_multiple >= 3 AND strategy_max_multiple < 10 THEN 1.0 ELSE 0.0 END END), 3) AS hit_3x_to_10x,
    ROUND(AVG(CASE WHEN filter_passed = 1 THEN CASE WHEN strategy_max_multiple >= 10 THEN 1.0 ELSE 0.0 END END), 3) AS hit_10x_plus,
    ROUND(AVG(CASE WHEN filter_passed = 1 THEN CASE WHEN strategy_max_multiple >= 10 THEN 1.0 ELSE 0.0 END END) * 100, 1) AS hit_10x_pct,
    ROUND(AVG(CASE WHEN filter_passed = 1 THEN strategy_max_multiple END), 2) AS avg_multiple
FROM strategy_research_view
WHERE mint IS NOT NULL
GROUP BY strategy_name;

DROP VIEW IF EXISTS rejection_damage_summary;
CREATE VIEW rejection_damage_summary AS
SELECT
    rejection_reason,
    COUNT(DISTINCT mint) AS rejected_tokens,
    ROUND(AVG(CASE WHEN max_multiple >= 2 THEN 1.0 ELSE 0.0 END), 3) AS hit_2x,
    ROUND(AVG(CASE WHEN max_multiple >= 5 THEN 1.0 ELSE 0.0 END), 3) AS hit_5x,
    ROUND(AVG(CASE WHEN max_multiple >= 10 THEN 1.0 ELSE 0.0 END), 3) AS hit_10x,
    ROUND(AVG(max_multiple), 2) AS avg_multiple
FROM strategy_research_view
WHERE strategy_name = 'research_v2_historical'
  AND COALESCE(filter_passed, 0) = 0
  AND rejection_reason IS NOT NULL
GROUP BY rejection_reason
ORDER BY hit_10x DESC, avg_multiple DESC;

DROP VIEW IF EXISTS missed_winner_examples;
CREATE VIEW missed_winner_examples AS
SELECT
    symbol,
    mint,
    rejection_reason,
    market_cap,
    liquidity,
    liq_to_mc,
    volume_usd,
    buys,
    holders,
    max_multiple
FROM strategy_research_view
WHERE strategy_name = 'research_v2_historical'
  AND COALESCE(filter_passed, 0) = 0
  AND max_multiple >= 5
ORDER BY max_multiple DESC;

DROP VIEW IF EXISTS strategy_overlap_summary;
CREATE VIEW strategy_overlap_summary AS
SELECT
    mint,
    MAX(symbol) AS symbol,
    GROUP_CONCAT(DISTINCT strategy_name) AS passed_strategies,
    COUNT(DISTINCT strategy_name) AS strategy_count,
    MAX(max_multiple) AS max_multiple
FROM strategy_research_view
WHERE strategy_name IN ('early_discovery', 'continuation_runner', 'premium_runner', 'confirmed_runner')
  AND filter_passed = 1
GROUP BY mint
HAVING COUNT(DISTINCT strategy_name) > 1
ORDER BY strategy_count DESC, max_multiple DESC;

DROP VIEW IF EXISTS token_strategy_journey;
CREATE VIEW token_strategy_journey AS
WITH first_pass AS (
    SELECT
        strategy_name,
        mint,
        MIN(evaluated_at) AS first_pass_time
    FROM strategy_research_view
    WHERE filter_passed = 1
      AND strategy_name IN (
          'research_v2_live',
          'early_discovery',
          'continuation_runner',
          'premium_runner',
          'confirmed_runner'
      )
    GROUP BY strategy_name, mint
),
first_pass_rows AS (
    SELECT
        fp.strategy_name,
        fp.mint,
        fp.first_pass_time,
        MIN(srv.market_cap) AS first_pass_market_cap,
        COUNT(*) AS passed_count
    FROM first_pass fp
    JOIN strategy_research_view srv
      ON srv.strategy_name = fp.strategy_name
     AND srv.mint = fp.mint
     AND srv.evaluated_at = fp.first_pass_time
     AND srv.filter_passed = 1
    GROUP BY fp.strategy_name, fp.mint, fp.first_pass_time
),
passed_counts AS (
    SELECT
        strategy_name,
        mint,
        COUNT(*) AS passed_count
    FROM strategy_research_view
    WHERE filter_passed = 1
      AND strategy_name IN (
          'research_v2_live',
          'early_discovery',
          'continuation_runner',
          'premium_runner',
          'confirmed_runner'
      )
    GROUP BY strategy_name, mint
),
token_base AS (
    SELECT
        srv.mint,
        MAX(srv.symbol) AS symbol,
        MIN(a.created_on) AS first_seen_at,
        MAX(srv.ath_mc) AS ath_mc,
        MAX(srv.token_max_multiple) AS token_max_multiple,
        MAX(srv.outcome_bucket) AS outcome_bucket
    FROM strategy_research_view srv
    LEFT JOIN alerts a ON a.mint = srv.mint
    WHERE srv.mint IS NOT NULL
    GROUP BY srv.mint
),
strategy_first AS (
    SELECT
        mint,
        strategy_name AS first_strategy_to_pass,
        first_pass_time AS first_strategy_pass_time,
        first_pass_market_cap AS first_strategy_pass_market_cap
    FROM (
        SELECT
            fpr.*,
            ROW_NUMBER() OVER (
                PARTITION BY mint
                ORDER BY first_pass_time ASC, strategy_name ASC
            ) AS rn
        FROM first_pass_rows fpr
    )
    WHERE rn = 1
)
SELECT
    tb.mint,
    tb.symbol,
    tb.first_seen_at,
    tb.ath_mc,
    tb.token_max_multiple,
    tb.outcome_bucket,

    rv2.first_pass_time AS research_v2_live_first_pass_time,
    rv2.first_pass_market_cap AS research_v2_live_first_pass_market_cap,
    COALESCE(rv2c.passed_count, 0) AS research_v2_live_passed_count,
    CASE
        WHEN rv2.first_pass_market_cap IS NOT NULL
         AND rv2.first_pass_market_cap > 0
         AND tb.ath_mc IS NOT NULL
        THEN tb.ath_mc / rv2.first_pass_market_cap
        ELSE NULL
    END AS research_v2_live_return_from_first_pass,

    early.first_pass_time AS early_discovery_first_pass_time,
    early.first_pass_market_cap AS early_discovery_first_pass_market_cap,
    COALESCE(earlyc.passed_count, 0) AS early_discovery_passed_count,
    CASE
        WHEN early.first_pass_market_cap IS NOT NULL
         AND early.first_pass_market_cap > 0
         AND tb.ath_mc IS NOT NULL
        THEN tb.ath_mc / early.first_pass_market_cap
        ELSE NULL
    END AS early_discovery_return_from_first_pass,

    continuation.first_pass_time AS continuation_runner_first_pass_time,
    continuation.first_pass_market_cap AS continuation_runner_first_pass_market_cap,
    COALESCE(continuationc.passed_count, 0) AS continuation_runner_passed_count,
    CASE
        WHEN continuation.first_pass_market_cap IS NOT NULL
         AND continuation.first_pass_market_cap > 0
         AND tb.ath_mc IS NOT NULL
        THEN tb.ath_mc / continuation.first_pass_market_cap
        ELSE NULL
    END AS continuation_runner_return_from_first_pass,

    premium.first_pass_time AS premium_runner_first_pass_time,
    premium.first_pass_market_cap AS premium_runner_first_pass_market_cap,
    COALESCE(premiumc.passed_count, 0) AS premium_runner_passed_count,
    CASE
        WHEN premium.first_pass_market_cap IS NOT NULL
         AND premium.first_pass_market_cap > 0
         AND tb.ath_mc IS NOT NULL
        THEN tb.ath_mc / premium.first_pass_market_cap
        ELSE NULL
    END AS premium_runner_return_from_first_pass,

    confirmed.first_pass_time AS confirmed_runner_first_pass_time,
    confirmed.first_pass_market_cap AS confirmed_runner_first_pass_market_cap,
    COALESCE(confirmedc.passed_count, 0) AS confirmed_runner_passed_count,
    CASE
        WHEN confirmed.first_pass_market_cap IS NOT NULL
         AND confirmed.first_pass_market_cap > 0
         AND tb.ath_mc IS NOT NULL
        THEN tb.ath_mc / confirmed.first_pass_market_cap
        ELSE NULL
    END AS confirmed_runner_return_from_first_pass,

    sf.first_strategy_to_pass,
    sf.first_strategy_pass_time,
    sf.first_strategy_pass_market_cap,
    CASE
        WHEN early.first_pass_time IS NOT NULL
         AND confirmed.first_pass_time IS NOT NULL
         AND early.first_pass_time < confirmed.first_pass_time
        THEN 1
        ELSE 0
    END AS confirmed_after_early,
    CASE
        WHEN early.first_pass_market_cap IS NOT NULL
         AND early.first_pass_market_cap > 0
         AND confirmed.first_pass_market_cap IS NOT NULL
        THEN confirmed.first_pass_market_cap / early.first_pass_market_cap
        ELSE NULL
    END AS early_to_confirmed_mc_multiple,
    CASE
        WHEN early.first_pass_time IS NOT NULL
         AND continuation.first_pass_time IS NOT NULL
         AND early.first_pass_time < continuation.first_pass_time
        THEN 1
        ELSE 0
    END AS continuation_after_early,
    CASE
        WHEN early.first_pass_market_cap IS NOT NULL
         AND early.first_pass_market_cap > 0
         AND continuation.first_pass_market_cap IS NOT NULL
        THEN continuation.first_pass_market_cap / early.first_pass_market_cap
        ELSE NULL
    END AS early_to_continuation_mc_multiple
FROM token_base tb
LEFT JOIN first_pass_rows rv2
  ON rv2.mint = tb.mint AND rv2.strategy_name = 'research_v2_live'
LEFT JOIN passed_counts rv2c
  ON rv2c.mint = tb.mint AND rv2c.strategy_name = 'research_v2_live'
LEFT JOIN first_pass_rows early
  ON early.mint = tb.mint AND early.strategy_name = 'early_discovery'
LEFT JOIN passed_counts earlyc
  ON earlyc.mint = tb.mint AND earlyc.strategy_name = 'early_discovery'
LEFT JOIN first_pass_rows continuation
  ON continuation.mint = tb.mint AND continuation.strategy_name = 'continuation_runner'
LEFT JOIN passed_counts continuationc
  ON continuationc.mint = tb.mint AND continuationc.strategy_name = 'continuation_runner'
LEFT JOIN first_pass_rows premium
  ON premium.mint = tb.mint AND premium.strategy_name = 'premium_runner'
LEFT JOIN passed_counts premiumc
  ON premiumc.mint = tb.mint AND premiumc.strategy_name = 'premium_runner'
LEFT JOIN first_pass_rows confirmed
  ON confirmed.mint = tb.mint AND confirmed.strategy_name = 'confirmed_runner'
LEFT JOIN passed_counts confirmedc
  ON confirmedc.mint = tb.mint AND confirmedc.strategy_name = 'confirmed_runner'
LEFT JOIN strategy_first sf
  ON sf.mint = tb.mint;
"""


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    db_path = Path(path) if path else settings.database_path
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def insert_alert(conn: sqlite3.Connection, alert: dict[str, Any]) -> bool:
    columns = [
        "notification_id",
        "mint",
        "symbol",
        "name",
        "chain",
        "notification_type",
        "sent_at",
        "market_cap",
        "first_call_market_cap",
        "liquidity",
        "price_usd",
        "vol_1h",
        "vol_24h",
        "chg_1h",
        "chg_24h",
        "total_buy",
        "count_buy",
        "label",
        "sentence",
        "paragraph",
        "factory",
        "pre_factory",
        "total_fee",
        "created_at",
        "first_call_time",
        "created_on",
        "raw_json",
    ]
    values = [alert.get(column) for column in columns]
    placeholders = ", ".join("?" for _ in columns)
    sql = f"""
        INSERT OR IGNORE INTO alerts ({", ".join(columns)})
        VALUES ({placeholders})
    """
    cur = conn.execute(sql, values)
    conn.commit()
    return cur.rowcount == 1


def upsert_token_quality(conn: sqlite3.Connection, metrics: dict[str, Any]) -> None:
    if not metrics.get("mint"):
        return
    metrics = {**metrics, "updated_at": metrics.get("updated_at") or utc_now_iso()}
    columns = [
        "mint",
        "holder_count",
        "top10_percent",
        "dev_hold_percent",
        "sniper_hold_percent",
        "bundle_hold_percent",
        "phishing_hold_percent",
        "dex_paid",
        "dex_boost_score",
        "freezable",
        "mintable",
        "lp_burned_percent",
        "updated_at",
    ]
    assignments = ", ".join(f"{column}=excluded.{column}" for column in columns[1:])
    conn.execute(
        f"""
        INSERT INTO token_quality_metrics ({", ".join(columns)})
        VALUES ({", ".join("?" for _ in columns)})
        ON CONFLICT(mint) DO UPDATE SET {assignments}
        """,
        [metrics.get(column) for column in columns],
    )
    conn.commit()


def replace_top_holders(
    conn: sqlite3.Connection, mint: str, holders: Iterable[dict[str, Any]], snapshot_time: str
) -> None:
    conn.execute("DELETE FROM top_holders WHERE mint = ?", (mint,))
    for holder in holders:
        conn.execute(
            """
            INSERT INTO top_holders
            (mint, wallet, amount, percent, name, kol_name, kol_twitter, snapshot_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mint,
                holder.get("wallet"),
                holder.get("amount"),
                holder.get("percent"),
                holder.get("name"),
                holder.get("kol_name"),
                holder.get("kol_twitter"),
                snapshot_time,
            ),
        )
    conn.commit()


def insert_enrichment(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    columns = [
        "notification_id",
        "mint",
        "enriched_at",
        "buy_volume_1m_usd",
        "buy_volume_5m_usd",
        "buy_volume_10m_usd",
        "buy_volume_1m_sol",
        "buy_volume_5m_sol",
        "buy_volume_10m_sol",
        "buy_count_1m",
        "buy_count_5m",
        "buy_count_10m",
        "sell_count_1m",
        "sell_count_5m",
        "sell_count_10m",
        "unique_buyers_1m",
        "unique_buyers_5m",
        "unique_buyers_10m",
        "net_buy_volume_1m",
        "net_buy_volume_5m",
        "net_buy_volume_10m",
        "top_buyer_share_10m",
        "raw_json",
    ]
    conn.execute(
        f"""
        INSERT INTO solana_tracker_enrichment ({", ".join(columns)})
        VALUES ({", ".join("?" for _ in columns)})
        """,
        [row.get(column) for column in columns],
    )
    conn.commit()


def upsert_alert_trade_window(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    columns = [
        "notification_id",
        "mint",
        "strategy_name",
        "alert_time",
        "window_label",
        "buy_volume_usd",
        "sell_volume_usd",
        "net_volume_usd",
        "buy_count",
        "sell_count",
        "unique_buyers",
        "unique_sellers",
        "avg_buy_size_usd",
        "top_buyer_share",
        "created_at",
        "raw_json",
    ]
    assignments = ", ".join(f"{column}=excluded.{column}" for column in columns[3:])
    conn.execute(
        f"""
        INSERT INTO alert_trade_windows ({", ".join(columns)})
        VALUES ({", ".join("?" for _ in columns)})
        ON CONFLICT(notification_id, strategy_name, window_label)
        DO UPDATE SET {assignments}
        """,
        [row.get(column) for column in columns],
    )
    conn.commit()


def upsert_outcome(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    columns = [
        "mint",
        "call_mc",
        "call_at",
        "current_mc",
        "ath_mc",
        "ath_at",
        "max_multiple",
        "outcome_bucket",
        "rugged",
        "next_milestone",
        "updated_at",
        "raw_json",
    ]
    assignments = ", ".join(f"{column}=excluded.{column}" for column in columns[1:])
    conn.execute(
        f"""
        INSERT INTO outcomes ({", ".join(columns)})
        VALUES ({", ".join("?" for _ in columns)})
        ON CONFLICT(mint) DO UPDATE SET {assignments}
        """,
        [row.get(column) for column in columns],
    )
    conn.commit()


def insert_milestone_event(conn: sqlite3.Connection, row: dict[str, Any]) -> bool:
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO milestone_events
        (mint, milestone, multiple, mc, hit_at, telegram_sent, telegram_message_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row.get("mint"),
            row.get("milestone"),
            row.get("multiple"),
            row.get("mc"),
            row.get("hit_at"),
            int(bool(row.get("telegram_sent"))),
            row.get("telegram_message_id"),
        ),
    )
    conn.commit()
    return cur.rowcount == 1


def mark_milestone_sent(
    conn: sqlite3.Connection, mint: str, milestone: float, telegram_message_id: str | None
) -> None:
    conn.execute(
        """
        UPDATE milestone_events
        SET telegram_sent = ?, telegram_message_id = ?
        WHERE mint = ? AND milestone = ?
        """,
        (1 if telegram_message_id else 0, telegram_message_id, mint, milestone),
    )
    conn.commit()


def claim_milestone_send(conn: sqlite3.Connection, mint: str, milestone: float) -> bool:
    cur = conn.execute(
        """
        UPDATE milestone_events
        SET telegram_sent = 2
        WHERE mint = ?
          AND milestone = ?
          AND telegram_message_id IS NULL
          AND COALESCE(telegram_sent, 0) != 2
        """,
        (mint, milestone),
    )
    conn.commit()
    return cur.rowcount == 1


def reset_stale_milestone_claims(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        """
        UPDATE milestone_events
        SET telegram_sent = 0
        WHERE telegram_message_id IS NULL
          AND COALESCE(telegram_sent, 0) != 0
        """
    )
    conn.commit()
    return cur.rowcount


def log_telegram_message(
    conn: sqlite3.Connection,
    message_type: str,
    telegram_message_id: str | None,
    notification_id: str | None = None,
    mint: str | None = None,
    milestone: float | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO telegram_sent_messages
        (message_type, notification_id, mint, milestone, sent_at, telegram_message_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (message_type, notification_id, mint, milestone, utc_now_iso(), telegram_message_id),
    )
    conn.commit()


def upsert_alert_filter_metrics(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    columns = [
        "notification_id",
        "mint",
        "symbol",
        "filter_name",
        "filter_passed",
        "market_cap",
        "liquidity",
        "age_minutes",
        "volume_usd",
        "buy_volume_sol",
        "sell_volume_sol",
        "buy_sell_volume_ratio",
        "buys",
        "holders",
        "unique_buyers",
        "top_buyer_share",
        "bundle_hold_percent",
        "sniper_hold_percent",
        "dev_hold_percent",
        "top10_percent",
        "phishing_hold_percent",
        "dex_paid",
        "lp_burned_percent",
        "liq_to_mc",
        "vol_to_mc",
        "avg_buy_size_sol",
        "top10_holder_pct",
        "bundle_pct",
        "sniper_pct",
        "rejection_reason",
        "created_at",
    ]
    assignments = ", ".join(f"{column}=excluded.{column}" for column in columns[1:])
    conn.execute(
        f"""
        INSERT INTO alert_filter_metrics ({", ".join(columns)})
        VALUES ({", ".join("?" for _ in columns)})
        ON CONFLICT(notification_id) DO UPDATE SET {assignments}
        """,
        [row.get(column) for column in columns],
    )
    conn.commit()


def upsert_strategy_evaluation(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    columns = [
        "evaluation_id",
        "notification_id",
        "mint",
        "symbol",
        "strategy_name",
        "filter_version",
        "filter_passed",
        "rejection_reason",
        "market_cap",
        "liquidity",
        "age_minutes",
        "volume_usd",
        "sol_volume",
        "liq_to_mc",
        "vol_to_mc",
        "buys",
        "holders",
        "top10_holder_pct",
        "bundle_pct",
        "sniper_pct",
        "buy_sell_volume_ratio",
        "evaluated_at",
        "raw_metrics_json",
    ]
    assignments = ", ".join(f"{column}=excluded.{column}" for column in columns[6:])
    conn.execute(
        f"""
        INSERT INTO strategy_evaluations ({", ".join(columns)})
        VALUES ({", ".join("?" for _ in columns)})
        ON CONFLICT(notification_id, strategy_name, filter_version)
        DO UPDATE SET {assignments}
        """,
        [row.get(column) for column in columns],
    )
    conn.commit()


def upsert_explosive_runner_candidate(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    columns = [
        "notification_id",
        "mint",
        "symbol",
        "market_cap",
        "liquidity",
        "age_minutes",
        "volume_usd",
        "sol_volume",
        "buys",
        "holders",
        "liq_to_mc",
        "vol_to_mc",
        "avg_buy_size_sol",
        "top10_holder_pct",
        "bundle_pct",
        "sniper_pct",
        "created_at",
    ]
    assignments = ", ".join(f"{column}=excluded.{column}" for column in columns[1:])
    conn.execute(
        f"""
        INSERT INTO explosive_runner_candidates ({", ".join(columns)})
        VALUES ({", ".join("?" for _ in columns)})
        ON CONFLICT(notification_id) DO UPDATE SET {assignments}
        """,
        [row.get(column) for column in columns],
    )
    conn.commit()


def due_mints_for_outcome_tracking(conn: sqlite3.Connection, track_hours: int) -> list[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT a.mint
        FROM alerts a
        LEFT JOIN outcomes o ON o.mint = a.mint
        WHERE a.mint IS NOT NULL
          AND (
            o.mint IS NULL
            OR datetime(COALESCE(o.call_at, a.first_call_time, a.created_on)) >= datetime('now', ?)
          )
        ORDER BY COALESCE(o.updated_at, a.created_on) ASC
        """,
        (f"-{track_hours} hours",),
    ).fetchall()
    return [row["mint"] for row in rows]


def json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=True, separators=(",", ":"), default=str)


if __name__ == "__main__":
    from .logging_config import configure_logging

    configure_logging()
    with connect() as connection:
        init_db(connection)
    logger.info("Initialized database at %s", settings.database_path)
