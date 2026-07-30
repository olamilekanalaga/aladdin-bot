from __future__ import annotations

import csv
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "vlak_aladdin_research.sqlite"
OUT_DIR = ROOT / "research_outputs" / "alert_entry_matrix"

COLUMNS = [
    "mint", "token_name", "symbol", "alert_time", "alert_multiple", "alert_market_cap", "first_call_market_cap", "time_since_first_call_seconds",
    "holders_at_alert", "buys_at_alert", "liquidity_at_alert", "volume_1h_at_alert", "avg_buy_size_sol_at_alert",
    "buy_volume_sol_at_alert", "lp_burned_percent_at_alert", "factory_at_alert",
    "sniper_percent_at_alert", "bundler_percent_at_alert", "sniper_percent_missing", "bundler_percent_missing", "top10_percent_at_alert", "dev_hold_percent_at_alert", "dev_sold_at_alert", "dex_paid_at_alert",
    "max_multiple_after_alert", "ath_market_cap_after_alert", "time_to_ath_after_alert_seconds",
    "gained_25_percent_after_alert", "gained_50_percent_after_alert", "gained_100_percent_after_alert", "gained_200_percent_after_alert",
    "reached_3x_after_alert", "reached_5x_after_alert", "reached_10x_after_alert",
    "alert_feature_source", "selected_snapshot_id", "selected_snapshot_observed_at", "source_raw_payload_hash", "telegram_sent", "telegram_message_id", "shadow_only", "pre_live_qualified", "created_at", "updated_at",
]


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") if dt else None


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def div(n: Any, d: Any) -> float | None:
    n = safe_float(n)
    d = safe_float(d)
    if n is None or d in (None, 0):
        return None
    return n / d


def seconds_between(start: Any, end: Any) -> int | None:
    a = parse_time(start)
    b = parse_time(end)
    if not a or not b:
        return None
    return int((b - a).total_seconds())


def flag(value: bool) -> int:
    return 1 if value else 0


def create_table(conn: sqlite3.Connection, reset: bool = True) -> None:
    if reset:
        conn.execute("DROP TABLE IF EXISTS vlak_alert_entry_feature_matrix")
    create_clause = "CREATE TABLE vlak_alert_entry_feature_matrix" if reset else "CREATE TABLE IF NOT EXISTS vlak_alert_entry_feature_matrix"
    conn.execute(
        f"""
        {create_clause} (
            mint TEXT PRIMARY KEY,
            token_name TEXT,
            symbol TEXT,
            alert_time TEXT,
            alert_multiple REAL,
            alert_market_cap REAL,
            first_call_market_cap REAL,
            time_since_first_call_seconds INTEGER,
            holders_at_alert INTEGER,
            buys_at_alert INTEGER,
            liquidity_at_alert REAL,
            volume_1h_at_alert REAL,
            avg_buy_size_sol_at_alert REAL,
            buy_volume_sol_at_alert REAL,
            lp_burned_percent_at_alert REAL,
            factory_at_alert TEXT,
            sniper_percent_at_alert REAL,
            bundler_percent_at_alert REAL,
            sniper_percent_missing INTEGER,
            bundler_percent_missing INTEGER,
            top10_percent_at_alert REAL,
            dev_hold_percent_at_alert REAL,
            dev_sold_at_alert INTEGER,
            dex_paid_at_alert INTEGER,
            max_multiple_after_alert REAL,
            ath_market_cap_after_alert REAL,
            time_to_ath_after_alert_seconds INTEGER,
            gained_25_percent_after_alert INTEGER,
            gained_50_percent_after_alert INTEGER,
            gained_100_percent_after_alert INTEGER,
            gained_200_percent_after_alert INTEGER,
            reached_3x_after_alert INTEGER,
            reached_5x_after_alert INTEGER,
            reached_10x_after_alert INTEGER,
            alert_feature_source TEXT,
            selected_snapshot_id INTEGER,
            selected_snapshot_observed_at TEXT,
            source_raw_payload_hash TEXT,
            telegram_sent INTEGER,
            telegram_message_id INTEGER,
            shadow_only INTEGER,
            pre_live_qualified INTEGER,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(vlak_alert_entry_feature_matrix)").fetchall()}
    extra_columns = {
        "buy_volume_sol_at_alert": "REAL",
        "lp_burned_percent_at_alert": "REAL",
        "factory_at_alert": "TEXT",
    }
    for column, column_type in extra_columns.items():
        if column not in existing_columns:
            conn.execute(f"ALTER TABLE vlak_alert_entry_feature_matrix ADD COLUMN {column} {column_type}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_vlak_alert_entry_feature_matrix_time ON vlak_alert_entry_feature_matrix(alert_time)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_vlak_alert_entry_feature_matrix_labels ON vlak_alert_entry_feature_matrix(gained_25_percent_after_alert, gained_100_percent_after_alert, reached_5x_after_alert)")


def select_alert_feature_snapshot(conn: sqlite3.Connection, mint: str, alert_time: str | None) -> sqlite3.Row | None:
    target = parse_time(alert_time)
    snapshots = conn.execute("SELECT * FROM vlak_api_metric_snapshots WHERE mint = ? ORDER BY observed_at ASC, id ASC", (mint,)).fetchall()
    if not snapshots or not target:
        return None
    best = None
    for snap in snapshots:
        observed = parse_time(snap["observed_at"])
        if observed and observed <= target:
            best = snap
        elif observed and observed > target:
            break
    return best


def outcome_candidates_after_alert(conn: sqlite3.Connection, mint: str, alert_dt: datetime | None, alert_mc: float | None) -> list[tuple[datetime, float, str]]:
    candidates: list[tuple[datetime, float, str]] = []
    if alert_dt and alert_mc is not None:
        candidates.append((alert_dt, alert_mc, "alert_entry"))
    if not alert_dt:
        return candidates
    for row in conn.execute("SELECT observed_at, market_cap, current_mc FROM vlak_api_metric_snapshots WHERE mint = ?", (mint,)):
        observed = parse_time(row["observed_at"])
        if not observed or observed < alert_dt:
            continue
        mc = safe_float(row["market_cap"] or row["current_mc"])
        if mc is not None:
            candidates.append((observed, mc, "metric_snapshot"))
    for row in conn.execute("SELECT hit_at, milestone_market_cap FROM vlak_outcome_milestones WHERE mint = ? AND hit = 1", (mint,)):
        hit_at = parse_time(row["hit_at"])
        if not hit_at or hit_at < alert_dt:
            continue
        mc = safe_float(row["milestone_market_cap"])
        if mc is not None:
            candidates.append((hit_at, mc, "outcome_milestone"))
    return candidates


def max_after_alert(conn: sqlite3.Connection, mint: str, alert_time: str | None, alert_mc: float | None) -> tuple[float | None, float | None, int | None]:
    alert_dt = parse_time(alert_time)
    candidates = outcome_candidates_after_alert(conn, mint, alert_dt, alert_mc)
    if not candidates or alert_mc in (None, 0):
        return None, None, None
    best_dt, best_mc, _ = max(candidates, key=lambda item: item[1])
    return best_mc / alert_mc, best_mc, int((best_dt - alert_dt).total_seconds()) if alert_dt else None


def build_row(conn: sqlite3.Connection, survivor: sqlite3.Row) -> dict[str, Any]:
    mint = survivor["mint"]
    thread = conn.execute("SELECT * FROM telegram_survivor_threads WHERE mint = ?", (mint,)).fetchone()
    alert_time = thread["first_alerted_at"] if thread else survivor["survivor_crossed_at"]
    snap = select_alert_feature_snapshot(conn, mint, alert_time)
    feature_source = "latest_snapshot_at_or_before_alert" if snap else "survivor_signal_table_only"
    first_mc = safe_float(survivor["first_spotted_mc"] or (snap["first_call_market_cap"] if snap else None))
    alert_mc = safe_float((snap["market_cap"] if snap else None) or survivor["survivor_mc"])
    alert_multiple = div(alert_mc, first_mc) or safe_float(thread["first_alert_multiple"] if thread else survivor["root_multiple"])
    max_after, ath_after, time_to_ath = max_after_alert(conn, mint, alert_time, alert_mc)
    abs_multiple_after = div(ath_after, first_mc)
    now = utc_now_iso()
    return {
        "mint": mint,
        "token_name": survivor["token_name"] or (snap["token_name"] if snap else None),
        "symbol": survivor["symbol"] or (snap["symbol"] if snap else None),
        "alert_time": alert_time,
        "alert_multiple": alert_multiple,
        "alert_market_cap": alert_mc,
        "first_call_market_cap": first_mc,
        "time_since_first_call_seconds": seconds_between(survivor["first_spotted_at"], alert_time),
        "holders_at_alert": safe_int((snap["holders_total"] if snap else None) or survivor["holders_at_survivor"]),
        "buys_at_alert": safe_int((snap["buys"] if snap else None) or survivor["buys_at_survivor"]),
        "liquidity_at_alert": safe_float((snap["liquidity_usd"] if snap else None) or survivor["liquidity_at_survivor"]),
        "volume_1h_at_alert": safe_float((snap["volume_1h_usd"] if snap else None) or survivor["volume_at_survivor"]),
        "avg_buy_size_sol_at_alert": safe_float((snap["avg_buy_size_sol"] if snap else None) or survivor["avg_buy_size_sol_at_survivor"]),
        "buy_volume_sol_at_alert": safe_float(snap["buy_volume_sol"] if snap and snap["buy_volume_sol"] is not None else survivor["buy_volume_sol_at_survivor"]),
        "lp_burned_percent_at_alert": safe_float(snap["lp_burned_percent"] if snap and snap["lp_burned_percent"] is not None else survivor["lp_burned_percent"]),
        "factory_at_alert": (snap["factory"] if snap and snap["factory"] is not None else survivor["factory"]),
        "sniper_percent_at_alert": safe_float((snap["sniper_percent"] if snap else None) if snap and snap["sniper_percent"] is not None else survivor["sniper_percent"]),
        "bundler_percent_at_alert": safe_float((snap["bundler_percent"] if snap else None) if snap and snap["bundler_percent"] is not None else survivor["bundler_percent"]),
        "top10_percent_at_alert": safe_float((snap["top10_percent"] if snap else None) if snap and snap["top10_percent"] is not None else survivor["top10_percent"]),
        "sniper_percent_missing": 1 if ((snap["sniper_percent"] if snap else None) if snap and snap["sniper_percent"] is not None else survivor["sniper_percent"]) is None else 0,
        "bundler_percent_missing": 1 if ((snap["bundler_percent"] if snap else None) if snap and snap["bundler_percent"] is not None else survivor["bundler_percent"]) is None else 0,
        "dev_hold_percent_at_alert": safe_float((snap["dev_hold_percent"] if snap else None) if snap and snap["dev_hold_percent"] is not None else survivor["dev_hold_percent"]),
        "dev_sold_at_alert": safe_int((snap["dev_sold"] if snap else None) if snap and snap["dev_sold"] is not None else survivor["dev_sold"]),
        "dex_paid_at_alert": safe_int((snap["dex_paid"] if snap else None) if snap and snap["dex_paid"] is not None else survivor["dex_paid"]),
        "max_multiple_after_alert": max_after,
        "ath_market_cap_after_alert": ath_after,
        "time_to_ath_after_alert_seconds": time_to_ath,
        "gained_25_percent_after_alert": flag(max_after is not None and max_after >= 1.25),
        "gained_50_percent_after_alert": flag(max_after is not None and max_after >= 1.50),
        "gained_100_percent_after_alert": flag(max_after is not None and max_after >= 2.00),
        "gained_200_percent_after_alert": flag(max_after is not None and max_after >= 3.00),
        "reached_3x_after_alert": flag(abs_multiple_after is not None and abs_multiple_after >= 3 and (alert_multiple or 0) < 3),
        "reached_5x_after_alert": flag(abs_multiple_after is not None and abs_multiple_after >= 5 and (alert_multiple or 0) < 5),
        "reached_10x_after_alert": flag(abs_multiple_after is not None and abs_multiple_after >= 10 and (alert_multiple or 0) < 10),
        "alert_feature_source": feature_source,
        "selected_snapshot_id": snap["id"] if snap else None,
        "selected_snapshot_observed_at": snap["observed_at"] if snap else None,
        "source_raw_payload_hash": snap["raw_payload_hash"] if snap else None,
        "telegram_sent": survivor["telegram_sent"],
        "telegram_message_id": survivor["telegram_message_id"],
        "shadow_only": survivor["shadow_only"],
        "pre_live_qualified": survivor["pre_live_qualified"],
        "created_at": now,
        "updated_at": now,
    }


def rebuild(db_path: Path = DB_PATH) -> dict[str, int]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        create_table(conn, reset=True)
        survivors = conn.execute("SELECT * FROM vlak_survivor_signals ORDER BY survivor_crossed_at, mint").fetchall()
        rows = [build_row(conn, row) for row in survivors]
        placeholders = ", ".join("?" for _ in COLUMNS)
        conn.executemany(
            f"INSERT INTO vlak_alert_entry_feature_matrix ({', '.join(COLUMNS)}) VALUES ({placeholders})",
            [[row.get(c) for c in COLUMNS] for row in rows],
        )
        conn.commit()
        total = conn.execute("SELECT COUNT(*) FROM vlak_alert_entry_feature_matrix").fetchone()[0]
        dup = conn.execute("SELECT COUNT(*) FROM (SELECT mint FROM vlak_alert_entry_feature_matrix GROUP BY mint HAVING COUNT(*) > 1)").fetchone()[0]
        return {"source_survivor_rows": len(survivors), "alert_entry_rows": total, "duplicate_mints": dup}



def upsert_alert_entry_row(db_path: Path | str = DB_PATH, mint: str | None = None) -> bool:
    if not mint:
        return False
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        create_table(conn, reset=False)
        survivor = conn.execute("SELECT * FROM vlak_survivor_signals WHERE mint = ?", (mint,)).fetchone()
        if survivor is None:
            return False
        row = build_row(conn, survivor)
        placeholders = ", ".join("?" for _ in COLUMNS)
        updates = ", ".join(f"{c}=excluded.{c}" for c in COLUMNS if c != "mint")
        conn.execute(
            f"""
            INSERT INTO vlak_alert_entry_feature_matrix ({', '.join(COLUMNS)})
            VALUES ({placeholders})
            ON CONFLICT(mint) DO UPDATE SET {updates}
            """,
            [row.get(c) for c in COLUMNS],
        )
        conn.commit()
        return True
def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else ["empty"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def avg(values: list[Any]) -> float | None:
    vals = [safe_float(v) for v in values]
    clean = [v for v in vals if v is not None]
    return sum(clean) / len(clean) if clean else None


def med(values: list[Any]) -> float | None:
    vals = [safe_float(v) for v in values]
    clean = [v for v in vals if v is not None]
    return float(median(clean)) if clean else None


def write_reports(build: dict[str, int], db_path: Path = DB_PATH) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM vlak_alert_entry_feature_matrix").fetchall()
        quality = [
            {"metric": "total_alert_entry_rows", "value": len(rows)},
            {"metric": "duplicate_mints", "value": build["duplicate_mints"]},
            {"metric": "median_alert_multiple", "value": med([r["alert_multiple"] for r in rows])},
            {"metric": "count_alerts_below_1_5x", "value": sum(1 for r in rows if (safe_float(r["alert_multiple"]) or 0) < 1.5)},
            {"metric": "count_alerts_between_1_5x_and_2x", "value": sum(1 for r in rows if 1.5 <= (safe_float(r["alert_multiple"]) or 0) < 2)},
            {"metric": "count_alerts_already_above_2x", "value": sum(1 for r in rows if (safe_float(r["alert_multiple"]) or 0) >= 2)},
            {"metric": "pct_with_25pct_upside_after_alert", "value": avg([r["gained_25_percent_after_alert"] for r in rows])},
            {"metric": "pct_with_50pct_upside_after_alert", "value": avg([r["gained_50_percent_after_alert"] for r in rows])},
            {"metric": "pct_with_100pct_upside_after_alert", "value": avg([r["gained_100_percent_after_alert"] for r in rows])},
            {"metric": "pct_with_200pct_upside_after_alert", "value": avg([r["gained_200_percent_after_alert"] for r in rows])},
            {"metric": "pct_reaching_3x_after_alert", "value": avg([r["reached_3x_after_alert"] for r in rows])},
            {"metric": "pct_reaching_5x_after_alert", "value": avg([r["reached_5x_after_alert"] for r in rows])},
            {"metric": "pct_reaching_10x_after_alert", "value": avg([r["reached_10x_after_alert"] for r in rows])},
            {"metric": "missing_alert_market_cap", "value": sum(1 for r in rows if r["alert_market_cap"] is None)},
            {"metric": "missing_holders_at_alert", "value": sum(1 for r in rows if r["holders_at_alert"] is None)},
            {"metric": "missing_volume_1h_at_alert", "value": sum(1 for r in rows if r["volume_1h_at_alert"] is None)},
            {"metric": "missing_liquidity_at_alert", "value": sum(1 for r in rows if r["liquidity_at_alert"] is None)},
        ]
        sample = [dict(r) for r in conn.execute("SELECT * FROM vlak_alert_entry_feature_matrix ORDER BY COALESCE(max_multiple_after_alert, 0) DESC LIMIT 20")]
        write_csv(OUT_DIR / "vlak_alert_entry_feature_matrix_quality_summary.csv", quality, ["metric", "value"])
        write_csv(OUT_DIR / "vlak_alert_entry_feature_matrix_sample_rows.csv", sample, COLUMNS)
    md = [
        "# Vlak Alert Entry Feature Matrix",
        "",
        "## Purpose",
        "One row per survivor alert entry event. This measures whether tradable upside remained from the exact Telegram/root alert point.",
        "",
        "## Feature Rule",
        "Alert-time features use the latest normalized metric snapshot at or before `alert_time`. If none exists, the row falls back to `vlak_survivor_signals` fields and marks `alert_feature_source = survivor_signal_table_only`.",
        "",
        "## Outcome Rule",
        "Relative outcome labels use only observed market caps and milestone hits at or after `alert_time`. Pre-alert milestones are not counted as post-alert upside.",
        "",
        "## Absolute Milestone Rule",
        "`reached_3x_after_alert`, `reached_5x_after_alert`, and `reached_10x_after_alert` only count if that absolute multiple was crossed after alert entry, not if it had already happened before entry.",
        "",
        "## Build Summary",
    ]
    md += [f"- {k}: {v}" for k, v in build.items()]
    (OUT_DIR / "vlak_alert_entry_feature_matrix_schema_report.md").write_text("\n".join(md), encoding="utf-8")


def main() -> None:
    build = rebuild(DB_PATH)
    write_reports(build, DB_PATH)
    print(build)
    print(OUT_DIR)


if __name__ == "__main__":
    main()





