from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aladdin_research_engine.normalizers import normalize_signal
from aladdin_research_engine.utils import number_or_none, pick
from migrate_vlak_long_run_schema import migrate

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "vlak_aladdin_research.sqlite"
OUT_DIR = ROOT / "research_outputs" / "research_metrics"


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def as_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def nested(raw: dict[str, Any], *keys: str) -> Any:
    cur: Any = raw
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def bool_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(bool(value))
    text = str(value).strip().lower()
    if text in {"true", "yes", "1", "paid"}:
        return 1
    if text in {"false", "no", "0", "none", "null"}:
        return 0
    return None


def num(*values: Any) -> float | None:
    for value in values:
        parsed = number_or_none(value)
        if parsed is not None:
            return parsed
    return None


def integer(value: Any) -> int | None:
    parsed = number_or_none(value)
    return int(parsed) if parsed is not None else None


def max_market_cap_from_outcome(raw: dict[str, Any]) -> float | None:
    candidates: list[float] = []
    for value in [raw.get("athMarketCap"), raw.get("ath_market_cap"), raw.get("maxMc"), raw.get("max_mc"), raw.get("currentMc"), raw.get("current_mc")]:
        parsed = num(value)
        if parsed is not None:
            candidates.append(parsed)
    outcome = raw.get("outcome") if isinstance(raw.get("outcome"), dict) else {}
    for key in ("max_mc_10m", "max_mc_30m", "max_mc_1h", "max_mc_24h"):
        parsed = num(outcome.get(key))
        if parsed is not None:
            candidates.append(parsed)
    milestones = raw.get("milestones") if isinstance(raw.get("milestones"), dict) else {}
    nested_milestones = milestones.get("milestones") if isinstance(milestones.get("milestones"), dict) else {}
    for item in list(nested_milestones.values()) + list(milestones.get("timeline", []) if isinstance(milestones.get("timeline"), list) else []):
        if isinstance(item, dict):
            parsed = num(item.get("mc"))
            if parsed is not None:
                candidates.append(parsed)
    return max(candidates) if candidates else None


def threshold_multiple(label: str) -> float | None:
    text = str(label).lower().replace("x", "").strip()
    if text == "alert":
        return 1.0
    return num(text)


def metric_record(source: str, endpoint: str | None, raw: dict[str, Any], *, observed_at: str | None = None, raw_payload_hash: str | None = None, notification_id: str | None = None, mint: str | None = None) -> dict[str, Any]:
    alert = normalize_signal(raw)
    holders = pick(raw, "holders", "holderStats", default={}) or {}
    trackers = pick(raw, "trackers", default={}) or {}
    audit = pick(raw, "audit", default={}) or {}
    social = pick(raw, "social", default={}) or {}
    pool = pick(raw, "pool", default={}) or {}
    if not isinstance(holders, dict):
        holders = {}
    if not isinstance(trackers, dict):
        trackers = {}
    if not isinstance(audit, dict):
        audit = {}
    if isinstance(pool, dict):
        pool_holding = pool.get("holding") if isinstance(pool.get("holding"), dict) else {}
        pool_audit = pool.get("audit") if isinstance(pool.get("audit"), dict) else {}
    else:
        pool_holding = {}
        pool_audit = {}
    if not isinstance(social, dict):
        social = {}
    if not isinstance(pool, dict):
        pool = {}

    buys = integer(pick(trackers, "countBuy", "count_buy", "buys") or alert.get("count_buy"))
    sells = integer(pick(trackers, "countSell", "count_sell", "sells") or alert.get("count_sell"))
    buy_volume_sol = num(pick(trackers, "totalBuy", "total_buy", "buyVolumeSol") or alert.get("total_buy"))
    sell_volume_sol = num(pick(trackers, "totalSell", "total_sell", "sellVolumeSol") or alert.get("total_sell"))
    first_call_mc = num(raw.get("callMc"), raw.get("firstCallMarketCap"), alert.get("first_call_market_cap"), alert.get("market_cap"))
    market_cap = num(raw.get("marketCap"), raw.get("market_cap"), alert.get("market_cap"), pool.get("marketCap"))
    current_mc = num(raw.get("currentMc"), raw.get("current_mc"), pool.get("marketCap"))
    ath_mc = max_market_cap_from_outcome(raw)
    explicit_multiple = num(raw.get("maxMultiple"), raw.get("max_multiple"))
    max_multiple = explicit_multiple or ((ath_mc / first_call_mc) if ath_mc is not None and first_call_mc else None)
    dev_hold = num(holders.get("devHoldPercent"), holders.get("dev_hold_percent"), pool_holding.get("devHoldPercent"), pool_holding.get("dev_hold_percent"))

    return {
        "source": source,
        "endpoint": endpoint,
        "mint": mint or alert.get("mint") or raw.get("mint"),
        "notification_id": notification_id or alert.get("notification_id") or raw.get("notificationId"),
        "observed_at": observed_at or utc_now_iso(),
        "payload_time": raw.get("updatedAt") or raw.get("callAt") or alert.get("first_call_time") or alert.get("sent_at"),
        "raw_payload_hash": raw_payload_hash or "",
        "token_name": alert.get("name") or raw.get("name"),
        "symbol": alert.get("symbol") or raw.get("symbol"),
        "image_url": raw.get("image") or raw.get("imageUrl"),
        "first_call_market_cap": first_call_mc,
        "market_cap": market_cap,
        "current_mc": current_mc,
        "ath_market_cap": ath_mc,
        "max_multiple": max_multiple,
        "price_usd": num(raw.get("priceUsd"), raw.get("price"), pool.get("priceUsd"), pool.get("price")),
        "liquidity_usd": num(alert.get("liquidity"), raw.get("liquidity"), pool.get("liquidity")),
        "volume_usd": num(alert.get("volume"), raw.get("volume"), raw.get("volumeUsd"), raw.get("vol1h"), raw.get("volume1h"), raw.get("volume_1h"), pool.get("volume")),
        "volume_1h_usd": num(raw.get("vol1h"), raw.get("volume1h"), raw.get("volume_1h")),
        "volume_24h_usd": num(raw.get("vol24h"), raw.get("volume24h"), raw.get("volume_24h")),
        "buy_volume_sol": buy_volume_sol,
        "sell_volume_sol": sell_volume_sol,
        "buys": buys,
        "sells": sells,
        "avg_buy_size_sol": (buy_volume_sol / buys) if buy_volume_sol is not None and buys else None,
        "holders_total": integer(pick(holders, "total", "holderCount", "holders") or pool_holding.get("total")),
        "sniper_percent": num(holders.get("sniperHoldPercent"), holders.get("sniper_pct"), pool_holding.get("sniperHoldPercent"), pool_holding.get("sniper_pct")),
        "bundler_percent": num(holders.get("bundleHoldPercent"), holders.get("bundle_pct"), pool_holding.get("bundleHoldPercent"), pool_holding.get("bundle_pct")),
        "top10_percent": num(holders.get("top10Percent"), holders.get("top10_percent"), pool_holding.get("top10Percent"), pool_holding.get("top10_percent")),
        "dev_hold_percent": dev_hold,
        "dev_sold": 1 if dev_hold is not None and dev_hold <= 0 else 0 if dev_hold is not None else None,
        "dex_paid": bool_int(audit.get("dexPaid") if audit.get("dexPaid") is not None else pool_audit.get("dexPaid")),
        "lp_burned_percent": num(audit.get("lpBurnedPercent"), pool_audit.get("lpBurnedPercent"), pool.get("lpBurnedPercent") if isinstance(pool, dict) else None),
        "mintable": bool_int(audit.get("mintable") if audit.get("mintable") is not None else pool_audit.get("mintable")),
        "freezable": bool_int(audit.get("freezable") if audit.get("freezable") is not None else pool_audit.get("freezable")),
        "dex_boost_score": num(audit.get("dexBoostScore"), pool_audit.get("dexBoostScore")),
        "website_url": social.get("website") if isinstance(social, dict) else None,
        "telegram_url": social.get("telegram") if isinstance(social, dict) else None,
        "twitter_url": social.get("twitter") if isinstance(social, dict) else None,
        "pair_address": raw.get("pairAddress") or pool.get("pairAddress"),
        "factory": raw.get("factory") or pool.get("factory"),
        "created_on": raw.get("createdOn") or pool.get("createdOn"),
        "stored_at": utc_now_iso(),
    }


def store_api_metric_snapshot(conn: sqlite3.Connection, source: str, endpoint: str | None, raw: dict[str, Any], *, observed_at: str | None = None, raw_payload_hash: str | None = None, notification_id: str | None = None, mint: str | None = None) -> None:
    record = metric_record(source, endpoint, raw, observed_at=observed_at, raw_payload_hash=raw_payload_hash, notification_id=notification_id, mint=mint)
    if not record["raw_payload_hash"]:
        return
    cols = list(record.keys())
    placeholders = ", ".join("?" for _ in cols)
    updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "raw_payload_hash")
    conn.execute(
        f"""
        INSERT INTO vlak_api_metric_snapshots ({', '.join(cols)})
        VALUES ({placeholders})
        ON CONFLICT(raw_payload_hash) DO UPDATE SET {updates}
        """,
        [record[c] for c in cols],
    )


def store_outcome_milestones(conn: sqlite3.Connection, mint: str, raw: dict[str, Any], *, snapshot_time: str | None = None, raw_payload_hash: str | None = None) -> None:
    now = utc_now_iso()
    milestones = raw.get("milestones") if isinstance(raw.get("milestones"), dict) else {}
    nested_milestones = milestones.get("milestones") if isinstance(milestones.get("milestones"), dict) else {}
    for label, item in nested_milestones.items():
        if not isinstance(item, dict):
            continue
        threshold = threshold_multiple(label)
        hit = bool_int(item.get("hit")) or 0
        hit_at = item.get("at")
        mc = num(item.get("mc"))
        existing = conn.execute(
            "SELECT created_at, first_seen_snapshot_time FROM vlak_outcome_milestones WHERE mint = ? AND threshold_label = ?",
            (mint, str(label)),
        ).fetchone()
        created_at = existing[0] if existing else now
        first_seen = existing[1] if existing and existing[1] else snapshot_time
        conn.execute(
            """
            INSERT INTO vlak_outcome_milestones
            (mint, threshold_label, threshold_multiple, hit, hit_at, milestone_market_cap, first_seen_snapshot_time, latest_snapshot_time, source_raw_payload_hash, source, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'vlak_outcome_endpoint', ?, ?)
            ON CONFLICT(mint, threshold_label) DO UPDATE SET
                threshold_multiple=excluded.threshold_multiple,
                hit=MAX(vlak_outcome_milestones.hit, excluded.hit),
                hit_at=COALESCE(vlak_outcome_milestones.hit_at, excluded.hit_at),
                milestone_market_cap=MAX(COALESCE(vlak_outcome_milestones.milestone_market_cap, 0), COALESCE(excluded.milestone_market_cap, 0)),
                first_seen_snapshot_time=COALESCE(vlak_outcome_milestones.first_seen_snapshot_time, excluded.first_seen_snapshot_time),
                latest_snapshot_time=excluded.latest_snapshot_time,
                source_raw_payload_hash=excluded.source_raw_payload_hash,
                updated_at=excluded.updated_at
            """,
            (mint, str(label), threshold, hit, hit_at, mc, first_seen, snapshot_time, raw_payload_hash, created_at, now),
        )


def backfill(db_path: Path = DB_PATH) -> dict[str, int]:
    migrate(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        signal_count = 0
        outcome_count = 0
        milestone_payloads = 0
        for row in conn.execute("SELECT * FROM vlak_alert_events WHERE raw_json IS NOT NULL"):
            raw = as_json(row["raw_json"])
            store_api_metric_snapshot(conn, row["source"] or "vlak_websocket", "websocket", raw, observed_at=row["inserted_at"], raw_payload_hash=row["raw_payload_hash"], notification_id=row["notification_id"], mint=row["mint"])
            signal_count += 1
        for row in conn.execute("SELECT * FROM vlak_outcome_snapshots WHERE raw_json IS NOT NULL"):
            raw = as_json(row["raw_json"])
            store_api_metric_snapshot(conn, row["source"] or "vlak_outcome_endpoint", f"/api/signal/{row['mint']}/outcome", raw, observed_at=row["snapshot_time"], raw_payload_hash=row["raw_payload_hash"], mint=row["mint"])
            store_outcome_milestones(conn, row["mint"], raw, snapshot_time=row["snapshot_time"], raw_payload_hash=row["raw_payload_hash"])
            outcome_count += 1
            if isinstance(raw.get("milestones"), dict):
                milestone_payloads += 1
        conn.commit()
        metric_rows = conn.execute("SELECT COUNT(*) FROM vlak_api_metric_snapshots").fetchone()[0]
        milestone_rows = conn.execute("SELECT COUNT(*) FROM vlak_outcome_milestones").fetchone()[0]
        duplicate_metrics = conn.execute("SELECT COUNT(*) FROM (SELECT raw_payload_hash FROM vlak_api_metric_snapshots GROUP BY raw_payload_hash HAVING COUNT(*) > 1)").fetchone()[0]
        duplicate_milestones = conn.execute("SELECT COUNT(*) FROM (SELECT mint, threshold_label FROM vlak_outcome_milestones GROUP BY mint, threshold_label HAVING COUNT(*) > 1)").fetchone()[0]
    return {
        "signals_processed": signal_count,
        "outcomes_processed": outcome_count,
        "outcome_payloads_with_milestones": milestone_payloads,
        "metric_snapshot_rows": metric_rows,
        "outcome_milestone_rows": milestone_rows,
        "duplicate_metric_hashes": duplicate_metrics,
        "duplicate_milestones": duplicate_milestones,
    }


def write_report(result: dict[str, int], db_path: Path = DB_PATH) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        milestone_summary = [dict(r) for r in conn.execute("""
            SELECT threshold_label, COUNT(*) AS rows, SUM(hit) AS hits,
                   MAX(milestone_market_cap) AS max_milestone_mc
            FROM vlak_outcome_milestones
            GROUP BY threshold_label
            ORDER BY COALESCE(threshold_multiple, 0)
        """)]
        coverage = [dict(r) for r in conn.execute("""
            SELECT
              COUNT(*) AS rows,
              SUM(CASE WHEN volume_usd IS NOT NULL THEN 1 ELSE 0 END) AS has_volume,
              SUM(CASE WHEN avg_buy_size_sol IS NOT NULL THEN 1 ELSE 0 END) AS has_avg_buy,
              SUM(CASE WHEN holders_total IS NOT NULL THEN 1 ELSE 0 END) AS has_holders,
              SUM(CASE WHEN sniper_percent IS NOT NULL THEN 1 ELSE 0 END) AS has_sniper,
              SUM(CASE WHEN bundler_percent IS NOT NULL THEN 1 ELSE 0 END) AS has_bundler,
              SUM(CASE WHEN dex_paid IS NOT NULL THEN 1 ELSE 0 END) AS has_dex_paid
            FROM vlak_api_metric_snapshots
        """)]
    import csv
    for name, rows in [("research_metric_backfill_summary.csv", [result]), ("outcome_milestone_summary.csv", milestone_summary), ("metric_snapshot_coverage.csv", coverage)]:
        with (OUT_DIR / name).open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["empty"])
            writer.writeheader()
            writer.writerows(rows)
    md = [
        "# Vlak Research Metrics Storage",
        "",
        "## What is stored",
        "- `vlak_api_metric_snapshots`: normalized research metrics from every observed Vlak websocket signal and outcome payload.",
        "- `vlak_outcome_milestones`: one row per mint and milestone label from the Vlak outcome payload, including hit time and milestone market cap when available.",
        "",
        "Telegram remains a delivery layer only. These tables are for research/model training.",
        "",
        "## Backfill",
    ]
    md += [f"- {k}: {v}" for k, v in result.items()]
    (OUT_DIR / "research_metrics_storage_report.md").write_text("\n".join(md), encoding="utf-8")


if __name__ == "__main__":
    result = backfill(DB_PATH)
    write_report(result, DB_PATH)
    print(result)
    print(OUT_DIR)


