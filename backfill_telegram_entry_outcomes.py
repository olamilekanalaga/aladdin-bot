from __future__ import annotations

import sqlite3
import os
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = Path(os.getenv("DATABASE_PATH", str(ROOT / "vlak_aladdin_research.sqlite")))
OUT = ROOT / "research_outputs" / "telegram_entry_outcomes"
OUT.mkdir(parents=True, exist_ok=True)


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def main() -> None:
    now = utc_now_iso()
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute(
        """
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
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS telegram_entry_outcome_milestones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mint TEXT NOT NULL,
            threshold REAL NOT NULL,
            multiple_at_send REAL,
            overall_multiple_at_send REAL,
            telegram_message_id INTEGER,
            sent_at TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'telegram_entry',
            UNIQUE(mint, threshold)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_telegram_entry_outcome_milestones_mint ON telegram_entry_outcome_milestones(mint)"
    )

    rows = conn.execute(
        """
        WITH first_event AS (
            SELECT * FROM (
                SELECT e.*, row_number() over(partition by e.mint order by datetime(e.alert_time), e.id) rn
                FROM vlak_alert_events e
            ) WHERE rn = 1
        ),
        metric_best AS (
            SELECT mint, MAX(market_cap) AS max_metric_market_cap, MAX(snapshot_time) AS latest_metric_snapshot_time
            FROM vlak_metric_snapshots
            GROUP BY mint
        ),
        milestone_best AS (
            SELECT mint, MAX(threshold) AS max_milestone_threshold
            FROM telegram_survivor_milestones
            GROUP BY mint
        )
        SELECT
            t.mint,
            t.first_alerted_at,
            t.first_alert_multiple,
            COALESCE(o.first_call_market_cap, e.first_call_market_cap) AS first_call_market_cap,
            COALESCE(mb.latest_metric_snapshot_time, o.latest_snapshot_time) AS latest_snapshot_time,
            CASE
                WHEN mb.max_metric_market_cap IS NOT NULL AND (o.current_mc IS NULL OR mb.max_metric_market_cap > o.current_mc)
                THEN mb.max_metric_market_cap
                ELSE o.current_mc
            END AS current_mc,
            MAX(
                COALESCE(o.ath_market_cap, 0),
                COALESCE(mb.max_metric_market_cap, 0),
                CASE
                    WHEN COALESCE(o.first_call_market_cap, e.first_call_market_cap) > 0 AND ms.max_milestone_threshold IS NOT NULL
                    THEN COALESCE(o.first_call_market_cap, e.first_call_market_cap) * ms.max_milestone_threshold
                    ELSE 0
                END
            ) AS ath_market_cap,
            MAX(
                COALESCE(o.max_multiple, 0),
                COALESCE(ms.max_milestone_threshold, 0),
                CASE
                    WHEN COALESCE(o.first_call_market_cap, e.first_call_market_cap) > 0 AND mb.max_metric_market_cap IS NOT NULL
                    THEN mb.max_metric_market_cap / COALESCE(o.first_call_market_cap, e.first_call_market_cap)
                    ELSE 0
                END,
                COALESCE(t.first_alert_multiple, 0)
            ) AS max_multiple_from_first_spotted
        FROM telegram_survivor_threads t
        LEFT JOIN vlak_token_outcomes o ON o.mint = t.mint
        LEFT JOIN first_event e ON e.mint = t.mint
        LEFT JOIN metric_best mb ON mb.mint = t.mint
        LEFT JOIN milestone_best ms ON ms.mint = t.mint
        """
    ).fetchall()

    updated = 0
    skipped = 0
    for r in rows:
        try:
            entry_multiple = float(r["first_alert_multiple"] or 0)
            overall = float(r["max_multiple_from_first_spotted"] or 0)
            first_mc = float(r["first_call_market_cap"] or 0)
        except (TypeError, ValueError):
            skipped += 1
            continue
        if entry_multiple <= 0 or overall <= 0 or first_mc <= 0:
            skipped += 1
            continue
        telegram_entry_market_cap = first_mc * entry_multiple
        max_from_entry = overall / entry_multiple
        conn.execute(
            """
            INSERT INTO telegram_entry_outcomes (
                mint, telegram_alerted_at, telegram_entry_multiple, telegram_entry_market_cap,
                latest_snapshot_time, current_mc, ath_market_cap, max_multiple_from_first_spotted,
                max_multiple_from_telegram_entry, hit_20pct_after_telegram, hit_50pct_after_telegram,
                hit_2x_after_telegram, hit_3x_after_telegram, hit_5x_after_telegram,
                hit_10x_after_telegram, outcome_source, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'historical_backfill_from_existing_outcomes', ?)
            ON CONFLICT(mint) DO UPDATE SET
                telegram_alerted_at=excluded.telegram_alerted_at,
                telegram_entry_multiple=excluded.telegram_entry_multiple,
                telegram_entry_market_cap=excluded.telegram_entry_market_cap,
                latest_snapshot_time=excluded.latest_snapshot_time,
                current_mc=excluded.current_mc,
                ath_market_cap=excluded.ath_market_cap,
                max_multiple_from_first_spotted=excluded.max_multiple_from_first_spotted,
                max_multiple_from_telegram_entry=excluded.max_multiple_from_telegram_entry,
                hit_20pct_after_telegram=excluded.hit_20pct_after_telegram,
                hit_50pct_after_telegram=excluded.hit_50pct_after_telegram,
                hit_2x_after_telegram=excluded.hit_2x_after_telegram,
                hit_3x_after_telegram=excluded.hit_3x_after_telegram,
                hit_5x_after_telegram=excluded.hit_5x_after_telegram,
                hit_10x_after_telegram=excluded.hit_10x_after_telegram,
                outcome_source=excluded.outcome_source,
                updated_at=excluded.updated_at
            """,
            (
                r["mint"],
                r["first_alerted_at"],
                entry_multiple,
                telegram_entry_market_cap,
                r["latest_snapshot_time"],
                r["current_mc"],
                r["ath_market_cap"],
                overall,
                max_from_entry,
                int(max_from_entry >= 1.2),
                int(max_from_entry >= 1.5),
                int(max_from_entry >= 2),
                int(max_from_entry >= 3),
                int(max_from_entry >= 5),
                int(max_from_entry >= 10),
                now,
            ),
        )
        updated += 1
    conn.commit()

    summary = conn.execute(
        """
        SELECT
            COUNT(*) AS rows,
            SUM(hit_20pct_after_telegram) AS hit_20pct,
            SUM(hit_50pct_after_telegram) AS hit_50pct,
            SUM(hit_2x_after_telegram) AS hit_2x,
            SUM(hit_3x_after_telegram) AS hit_3x,
            SUM(hit_5x_after_telegram) AS hit_5x,
            ROUND(AVG(max_multiple_from_telegram_entry), 4) AS avg_entry_outcome,
            ROUND(AVG(CASE WHEN max_multiple_from_telegram_entry IS NOT NULL THEN max_multiple_from_telegram_entry END), 4) AS avg_entry_outcome_nonnull
        FROM telegram_entry_outcomes
        """
    ).fetchone()
    report = OUT / "telegram_entry_outcome_backfill_report.md"
    report.write_text(
        "\n".join(
            [
                "# Telegram Entry Outcome Backfill Report",
                "",
                f"DB: `{DB}`",
                f"Run at UTC: `{now}`",
                "",
                "## Result",
                f"- Telegram thread rows scanned: {len(rows)}",
                f"- Telegram-entry outcome rows upserted: {updated}",
                f"- Rows skipped for missing/invalid entry multiple, first MC or max multiple: {skipped}",
                "",
                "## Current Table Summary",
                f"- telegram_entry_outcomes rows: {summary['rows']}",
                f"- +20% after Telegram: {summary['hit_20pct']}",
                f"- +50% after Telegram: {summary['hit_50pct']}",
                f"- 2x after Telegram: {summary['hit_2x']}",
                f"- 3x after Telegram: {summary['hit_3x']}",
                f"- 5x after Telegram: {summary['hit_5x']}",
                f"- Average max multiple from Telegram entry: {summary['avg_entry_outcome']}",
                "",
                "## Safety",
                "- Existing first-spotted outcome columns/tables were not deleted.",
                "- Existing telegram_survivor_milestones rows were not changed.",
                "- Future Telegram milestone replies now use telegram_entry_outcome_milestones.",
            ]
        ),
        encoding="utf-8",
    )
    print(f"scanned={len(rows)} updated={updated} skipped={skipped} report={report}")
    print(dict(summary))
    conn.close()


if __name__ == "__main__":
    main()
