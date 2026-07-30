from __future__ import annotations

import csv
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from migrate_vlak_long_run_schema import migrate

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "vlak_aladdin_research.sqlite"
OUT_DIR = ROOT / "research_outputs" / "survivor_signals"
SURVIVOR_THRESHOLD = 1.4


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def seconds_between(start: Any, end: Any) -> int | None:
    a = parse_time(start)
    b = parse_time(end)
    if not a or not b:
        return None
    return max(0, int((b - a).total_seconds()))


def as_json(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def nested(data: dict[str, Any], *keys: str) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def bool_int(value: Any) -> int | None:
    if value is None:
        return None
    return 1 if bool(value) else 0


def num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con


def first_event(con: sqlite3.Connection, mint: str) -> sqlite3.Row | None:
    return con.execute(
        """
        SELECT * FROM vlak_alert_events
        WHERE mint = ? AND is_first_alert_per_mint = 1
        ORDER BY alert_time ASC, id ASC
        LIMIT 1
        """,
        (mint,),
    ).fetchone()


def nearest_metric(con: sqlite3.Connection, mint: str, at_time: str | None) -> sqlite3.Row | None:
    if at_time:
        row = con.execute(
            """
            SELECT * FROM vlak_metric_snapshots
            WHERE mint = ? AND snapshot_time <= ?
            ORDER BY snapshot_time DESC, id DESC
            LIMIT 1
            """,
            (mint, at_time),
        ).fetchone()
        if row:
            return row
    return con.execute(
        "SELECT * FROM vlak_metric_snapshots WHERE mint = ? ORDER BY snapshot_time ASC, id ASC LIMIT 1",
        (mint,),
    ).fetchone()


def crossing_candidates(con: sqlite3.Connection, mint: str, first_mc: float, threshold: float) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in con.execute(
        "SELECT * FROM vlak_alert_events WHERE mint = ? AND market_cap IS NOT NULL ORDER BY alert_time ASC, id ASC",
        (mint,),
    ):
        market_cap = num(row["market_cap"])
        if market_cap and first_mc and market_cap / first_mc >= threshold:
            candidates.append({"time": row["alert_time"], "mc": market_cap, "multiple": market_cap / first_mc, "source": "vlak_alert_events", "row": row})
            break
    for row in con.execute(
        "SELECT * FROM vlak_metric_snapshots WHERE mint = ? AND market_cap IS NOT NULL ORDER BY snapshot_time ASC, id ASC",
        (mint,),
    ):
        market_cap = num(row["market_cap"])
        if market_cap and first_mc and market_cap / first_mc >= threshold:
            candidates.append({"time": row["snapshot_time"], "mc": market_cap, "multiple": market_cap / first_mc, "source": "vlak_metric_snapshots", "row": row})
            break
    for row in con.execute(
        "SELECT * FROM vlak_outcome_snapshots WHERE mint = ? AND max_multiple IS NOT NULL ORDER BY snapshot_time ASC, id ASC",
        (mint,),
    ):
        max_multiple = num(row["max_multiple"])
        if max_multiple is not None and max_multiple >= threshold:
            mc = num(row["ath_market_cap"]) or num(row["market_cap"]) or num(row["current_mc"])
            candidates.append({"time": row["snapshot_time"], "mc": mc, "multiple": max_multiple, "source": "vlak_outcome_snapshots", "row": row})
            break
    return [c for c in candidates if c.get("time")]


def survivor_crossing(con: sqlite3.Connection, mint: str, first_mc: float, threshold: float = SURVIVOR_THRESHOLD) -> dict[str, Any] | None:
    candidates = crossing_candidates(con, mint, first_mc, threshold)
    if not candidates:
        return None
    return sorted(candidates, key=lambda c: parse_time(c["time"]) or datetime.max.replace(tzinfo=UTC))[0]


def best_outcome(con: sqlite3.Connection, mint: str, first_mc: float) -> tuple[float | None, float | None, str | None]:
    outcome = con.execute("SELECT * FROM vlak_token_outcomes WHERE mint = ?", (mint,)).fetchone()
    max_multiple = num(outcome["max_multiple"]) if outcome else None
    ath_mc = num(outcome["ath_market_cap"]) if outcome else None
    latest = outcome["latest_snapshot_time"] if outcome else None
    metric = con.execute("SELECT MAX(market_cap) AS max_metric_mc, MAX(snapshot_time) AS latest_metric_time FROM vlak_metric_snapshots WHERE mint = ?", (mint,)).fetchone()
    metric_mc = num(metric["max_metric_mc"]) if metric else None
    if metric_mc and first_mc:
        metric_multiple = metric_mc / first_mc
        if max_multiple is None or metric_multiple > max_multiple:
            max_multiple = metric_multiple
            ath_mc = metric_mc
            latest = metric["latest_metric_time"] or latest
    return max_multiple, ath_mc, latest


def time_to_threshold(con: sqlite3.Connection, mint: str, first_mc: float, first_time: str | None, threshold: float) -> int | None:
    candidates = crossing_candidates(con, mint, first_mc, threshold)
    if not candidates:
        return None
    crossing = sorted(candidates, key=lambda c: parse_time(c["time"]) or datetime.max.replace(tzinfo=UTC))[0]
    return seconds_between(first_time, crossing["time"])


def build_survivor_record(con: sqlite3.Connection, mint: str) -> dict[str, Any] | None:
    event = first_event(con, mint)
    if not event:
        return None
    first_mc = num(event["first_call_market_cap"])
    if not first_mc:
        return None
    crossing = survivor_crossing(con, mint, first_mc)
    if not crossing:
        return None
    metric = nearest_metric(con, mint, crossing["time"])
    raw = as_json(event["raw_json"])
    holders = nested(raw, "holders") or {}
    audit = nested(raw, "audit") or {}
    social = nested(raw, "social") or {}
    thread = con.execute("SELECT * FROM telegram_survivor_threads WHERE mint = ?", (mint,)).fetchone()
    shadow = con.execute("SELECT * FROM telegram_survivor_shadow_exclusions WHERE mint = ?", (mint,)).fetchone()
    max_multiple, ath_mc, latest = best_outcome(con, mint, first_mc)
    survivor_mc = num(crossing["mc"])
    root_multiple = num(crossing["multiple"])
    dev_hold = num(holders.get("devHoldPercent")) if isinstance(holders, dict) else None
    dex_paid = audit.get("dexPaid") if isinstance(audit, dict) else None
    now = utc_now_iso()
    return {
        "mint": mint,
        "token_name": event["name"],
        "symbol": event["symbol"],
        "first_spotted_at": event["alert_time"],
        "survivor_crossed_at": crossing["time"],
        "survivor_threshold": SURVIVOR_THRESHOLD,
        "root_multiple": root_multiple,
        "first_spotted_mc": first_mc,
        "survivor_mc": survivor_mc,
        "mc_gain_to_root": (survivor_mc / first_mc) if survivor_mc and first_mc else root_multiple,
        "time_since_first_spotted_seconds": seconds_between(event["alert_time"], crossing["time"]),
        "buys_at_survivor": metric["buys"] if metric else event["buys"],
        "sells_at_survivor": metric["sells"] if metric else None,
        "holders_at_survivor": metric["holders"] if metric else event["holders"],
        "liquidity_at_survivor": metric["liquidity"] if metric else event["liquidity"],
        "volume_at_survivor": metric["volume"] if metric else event["volume"],
        "price_at_survivor": metric["price"] if metric else num(raw.get("priceUsd")),
        "buy_volume_sol_at_survivor": metric["buy_volume_sol"] if metric else None,
        "avg_buy_size_sol_at_survivor": metric["avg_buy_size_sol"] if metric else None,
        "liq_to_mc_at_survivor": metric["liq_to_mc"] if metric else None,
        "vol_to_mc_at_survivor": metric["vol_to_mc"] if metric else None,
        "sniper_percent": metric["sniper_percent"] if metric and metric["sniper_percent"] is not None else (holders.get("sniperHoldPercent") if isinstance(holders, dict) else None),
        "bundler_percent": metric["bundle_percent"] if metric and metric["bundle_percent"] is not None else (holders.get("bundleHoldPercent") if isinstance(holders, dict) else None),
        "top10_percent": metric["top10_percent"] if metric and metric["top10_percent"] is not None else (holders.get("top10Percent") if isinstance(holders, dict) else None),
        "dev_sold": 1 if dev_hold is not None and dev_hold <= 0 else 0 if dev_hold is not None else None,
        "dev_hold_percent": dev_hold,
        "dex_paid": bool_int(dex_paid),
        "lp_burned_percent": num(audit.get("lpBurnedPercent")) if isinstance(audit, dict) else None,
        "mintable": bool_int(audit.get("mintable")) if isinstance(audit, dict) else None,
        "freezable": bool_int(audit.get("freezable")) if isinstance(audit, dict) else None,
        "dex_boost_score": num(audit.get("dexBoostScore")) if isinstance(audit, dict) else None,
        "image_url": raw.get("image"),
        "website_url": social.get("website") if isinstance(social, dict) else None,
        "telegram_url": social.get("telegram") if isinstance(social, dict) else None,
        "twitter_url": social.get("twitter") if isinstance(social, dict) else None,
        "pair_address": raw.get("pairAddress"),
        "factory": raw.get("factory"),
        "created_on": raw.get("createdOn"),
        "raw_api_source": crossing["source"],
        "telegram_sent": 1 if thread and thread["root_message_id"] is not None else 0,
        "telegram_message_id": thread["root_message_id"] if thread else None,
        "shadow_only": 1 if shadow else 0,
        "pre_live_qualified": 1 if shadow and shadow["reason"] == "pre_live_qualified" else 0,
        "created_at": now,
        "updated_at": now,
        "ath_multiple": max_multiple,
        "ath_market_cap": ath_mc,
        "hit_2x": 1 if max_multiple is not None and max_multiple >= 2 else 0,
        "hit_3x": 1 if max_multiple is not None and max_multiple >= 3 else 0,
        "hit_5x": 1 if max_multiple is not None and max_multiple >= 5 else 0,
        "hit_10x": 1 if max_multiple is not None and max_multiple >= 10 else 0,
        "time_to_2x_seconds": time_to_threshold(con, mint, first_mc, event["alert_time"], 2),
        "time_to_3x_seconds": time_to_threshold(con, mint, first_mc, event["alert_time"], 3),
        "time_to_5x_seconds": time_to_threshold(con, mint, first_mc, event["alert_time"], 5),
        "time_to_10x_seconds": time_to_threshold(con, mint, first_mc, event["alert_time"], 10),
        "latest_outcome_updated_at": latest,
    }


SURVIVOR_COLUMNS = [
    "mint", "token_name", "symbol", "first_spotted_at", "survivor_crossed_at", "survivor_threshold", "root_multiple", "first_spotted_mc", "survivor_mc", "mc_gain_to_root", "time_since_first_spotted_seconds", "buys_at_survivor", "sells_at_survivor", "holders_at_survivor", "liquidity_at_survivor", "volume_at_survivor", "price_at_survivor", "buy_volume_sol_at_survivor", "avg_buy_size_sol_at_survivor", "liq_to_mc_at_survivor", "vol_to_mc_at_survivor", "sniper_percent", "bundler_percent", "top10_percent", "dev_sold", "dev_hold_percent", "dex_paid", "lp_burned_percent", "mintable", "freezable", "dex_boost_score", "image_url", "website_url", "telegram_url", "twitter_url", "pair_address", "factory", "created_on", "raw_api_source", "telegram_sent", "telegram_message_id", "shadow_only", "pre_live_qualified", "created_at", "updated_at", "ath_multiple", "ath_market_cap", "hit_2x", "hit_3x", "hit_5x", "hit_10x", "time_to_2x_seconds", "time_to_3x_seconds", "time_to_5x_seconds", "time_to_10x_seconds", "latest_outcome_updated_at"
]


def upsert_record(con: sqlite3.Connection, record: dict[str, Any]) -> None:
    existing = con.execute("SELECT created_at FROM vlak_survivor_signals WHERE mint = ?", (record["mint"],)).fetchone()
    if existing:
        record["created_at"] = existing["created_at"]
    cols = SURVIVOR_COLUMNS
    placeholders = ", ".join("?" for _ in cols)
    updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "mint")
    con.execute(
        f"""
        INSERT INTO vlak_survivor_signals ({', '.join(cols)})
        VALUES ({placeholders})
        ON CONFLICT(mint) DO UPDATE SET {updates}
        """,
        [record.get(c) for c in cols],
    )


def upsert_survivor_signal(db_path: Path | str, mint: str) -> bool:
    db_path = Path(db_path)
    migrate(db_path)
    with connect(db_path) as con:
        record = build_survivor_record(con, mint)
        if not record:
            return False
        upsert_record(con, record)
        con.commit()
        return True


def survivor_mints(con: sqlite3.Connection) -> list[str]:
    mints: set[str] = set()
    for row in con.execute("SELECT DISTINCT mint FROM vlak_token_outcomes"):
        record = build_survivor_record(con, row["mint"])
        if record:
            mints.add(row["mint"])
    return sorted(mints)


def backfill_survivor_signals(db_path: Path = DB_PATH) -> dict[str, Any]:
    migrate(db_path)
    inserted = 0
    updated = 0
    with connect(db_path) as con:
        for mint in survivor_mints(con):
            exists = con.execute("SELECT 1 FROM vlak_survivor_signals WHERE mint = ?", (mint,)).fetchone()
            record = build_survivor_record(con, mint)
            if not record:
                continue
            upsert_record(con, record)
            if exists:
                updated += 1
            else:
                inserted += 1
        con.commit()
        total = con.execute("SELECT COUNT(*) FROM vlak_survivor_signals").fetchone()[0]
        duplicates = con.execute("SELECT COUNT(*) FROM (SELECT mint FROM vlak_survivor_signals GROUP BY mint HAVING COUNT(*) > 1)").fetchone()[0]
    return {"inserted": inserted, "updated": updated, "total": total, "duplicates": duplicates}


def flatten_json(data: Any, prefix: str = "") -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    if isinstance(data, dict):
        for key, value in data.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            out.extend(flatten_json(value, name))
    elif isinstance(data, list):
        out.append((prefix, data[:1] if data else []))
        if data and isinstance(data[0], dict):
            out.extend(flatten_json(data[0], f"{prefix}[]"))
    else:
        out.append((prefix, data))
    return out


def observed_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


FIELD_STORAGE = {
    "mint": ("vlak_survivor_signals", "mint"),
    "name": ("vlak_survivor_signals", "token_name"),
    "symbol": ("vlak_survivor_signals", "symbol"),
    "image": ("vlak_survivor_signals", "image_url"),
    "firstCallTime": ("vlak_survivor_signals", "first_spotted_at"),
    "sentAt": ("vlak_survivor_signals", "first_spotted_at"),
    "firstCallMarketCap": ("vlak_survivor_signals", "first_spotted_mc"),
    "marketCap": ("vlak_survivor_signals", "survivor_mc/current_mc"),
    "liquidity": ("vlak_survivor_signals", "liquidity_at_survivor"),
    "priceUsd": ("vlak_survivor_signals", "price_at_survivor"),
    "vol1h": ("not_stored", ""),
    "vol24h": ("not_stored", ""),
    "holders.total": ("vlak_survivor_signals", "holders_at_survivor"),
    "holders.sniperHoldPercent": ("vlak_survivor_signals", "sniper_percent"),
    "holders.bundleHoldPercent": ("vlak_survivor_signals", "bundler_percent"),
    "holders.devHoldPercent": ("vlak_survivor_signals", "dev_hold_percent/dev_sold"),
    "holders.top10Percent": ("vlak_survivor_signals", "top10_percent"),
    "holders.top10": ("not_stored", ""),
    "trackers.countBuy": ("vlak_survivor_signals", "buys_at_survivor"),
    "trackers.totalBuy": ("not_stored", ""),
    "audit.dexPaid": ("vlak_survivor_signals", "dex_paid"),
    "audit.lpBurnedPercent": ("vlak_survivor_signals", "lp_burned_percent"),
    "audit.mintable": ("vlak_survivor_signals", "mintable"),
    "audit.freezable": ("vlak_survivor_signals", "freezable"),
    "audit.dexBoostScore": ("vlak_survivor_signals", "dex_boost_score"),
    "social.website": ("vlak_survivor_signals", "website_url"),
    "social.telegram": ("vlak_survivor_signals", "telegram_url"),
    "social.twitter": ("vlak_survivor_signals", "twitter_url"),
    "pairAddress": ("vlak_survivor_signals", "pair_address"),
    "factory": ("vlak_survivor_signals", "factory"),
    "createdOn": ("vlak_survivor_signals", "created_on"),
    "currentMc": ("vlak_survivor_signals", "ath_market_cap/current_mc"),
    "maxMultiple": ("vlak_survivor_signals", "ath_multiple"),
    "outcome.max_mc_10m": ("vlak_survivor_signals", "ath_market_cap"),
    "outcome.max_mc_30m": ("vlak_survivor_signals", "ath_market_cap"),
    "outcome.max_mc_1h": ("vlak_survivor_signals", "ath_market_cap"),
    "outcome.max_mc_24h": ("vlak_survivor_signals", "ath_market_cap"),
}


def endpoint_rows(con: sqlite3.Connection) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for row in con.execute("SELECT raw_json FROM vlak_alert_events WHERE raw_json IS NOT NULL LIMIT 500"):
        rows.append(("websocket", "vlak_alert_events.raw_json", row["raw_json"]))
    for row in con.execute("SELECT raw_json FROM vlak_outcome_snapshots WHERE raw_json IS NOT NULL LIMIT 500"):
        rows.append(("/api/signal/{mint}/outcome", "vlak_outcome_snapshots.raw_json", row["raw_json"]))
    return rows


def populate_api_field_catalog(db_path: Path = DB_PATH) -> list[dict[str, Any]]:
    migrate(db_path)
    now = utc_now_iso()
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    with connect(db_path) as con:
        for endpoint, source, raw in endpoint_rows(con):
            data = as_json(raw)
            for field_name, value in flatten_json(data):
                if not field_name:
                    continue
                key = (endpoint, field_name)
                stored = FIELD_STORAGE.get(field_name, ("not_stored", ""))
                notes = "observed in payload"
                if stored[0] == "not_stored":
                    notes = "observed but not stored as dedicated survivor signal column"
                rec = seen.setdefault(
                    key,
                    {
                        "endpoint": endpoint,
                        "field_name": field_name,
                        "example_value": json.dumps(value, ensure_ascii=False)[:500],
                        "observed_type": observed_type(value),
                        "stored_in_table": stored[0],
                        "stored_column": stored[1],
                        "notes": notes,
                        "first_seen_at": now,
                        "last_seen_at": now,
                    },
                )
                rec["last_seen_at"] = now
        for rec in seen.values():
            con.execute(
                """
                INSERT INTO vlak_api_field_catalog
                (endpoint, field_name, example_value, observed_type, stored_in_table, stored_column, notes, first_seen_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(endpoint, field_name) DO UPDATE SET
                    example_value=excluded.example_value,
                    observed_type=excluded.observed_type,
                    stored_in_table=excluded.stored_in_table,
                    stored_column=excluded.stored_column,
                    notes=excluded.notes,
                    last_seen_at=excluded.last_seen_at
                """,
                [rec[k] for k in ["endpoint", "field_name", "example_value", "observed_type", "stored_in_table", "stored_column", "notes", "first_seen_at", "last_seen_at"]],
            )
        con.commit()
        return list(seen.values())


def median(values: list[Any]) -> float | None:
    xs = sorted(float(v) for v in values if v is not None)
    if not xs:
        return None
    n = len(xs)
    mid = n // 2
    return xs[mid] if n % 2 else (xs[mid - 1] + xs[mid]) / 2


def quality_summary(con: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = con.execute("SELECT * FROM vlak_survivor_signals").fetchall()
    total = len(rows)
    def rate(col: str) -> float | None:
        return None if not total else sum(1 for r in rows if r[col]) / total
    stopped = [r for r in rows if not r["hit_2x"]]
    hit2 = [r for r in rows if r["hit_2x"]]
    summary = [
        {"metric": "total_survivor_signals", "value": total},
        {"metric": "hit_2x_rate", "value": rate("hit_2x")},
        {"metric": "hit_3x_rate", "value": rate("hit_3x")},
        {"metric": "hit_5x_rate", "value": rate("hit_5x")},
        {"metric": "hit_10x_rate", "value": rate("hit_10x")},
        {"metric": "median_root_multiple", "value": median([r["root_multiple"] for r in rows])},
        {"metric": "median_survivor_mc", "value": median([r["survivor_mc"] for r in rows])},
        {"metric": "median_holders", "value": median([r["holders_at_survivor"] for r in rows])},
        {"metric": "median_buys", "value": median([r["buys_at_survivor"] for r in rows])},
        {"metric": "median_liquidity", "value": median([r["liquidity_at_survivor"] for r in rows])},
        {"metric": "median_volume", "value": median([r["volume_at_survivor"] for r in rows])},
        {"metric": "stopped_below_2x_count", "value": len(stopped)},
        {"metric": "hit_2x_count", "value": len(hit2)},
        {"metric": "stopped_median_root_multiple", "value": median([r["root_multiple"] for r in stopped])},
        {"metric": "hit2_median_root_multiple", "value": median([r["root_multiple"] for r in hit2])},
        {"metric": "stopped_median_survivor_mc", "value": median([r["survivor_mc"] for r in stopped])},
        {"metric": "hit2_median_survivor_mc", "value": median([r["survivor_mc"] for r in hit2])},
        {"metric": "stopped_median_holders", "value": median([r["holders_at_survivor"] for r in stopped])},
        {"metric": "hit2_median_holders", "value": median([r["holders_at_survivor"] for r in hit2])},
        {"metric": "stopped_median_buys", "value": median([r["buys_at_survivor"] for r in stopped])},
        {"metric": "hit2_median_buys", "value": median([r["buys_at_survivor"] for r in hit2])},
    ]
    return summary


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_reports(db_path: Path = DB_PATH, backfill_result: dict[str, Any] | None = None) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as con:
        catalog = [dict(r) for r in con.execute("SELECT * FROM vlak_api_field_catalog ORDER BY endpoint, field_name")]
        write_csv(OUT_DIR / "vlak_api_field_catalog.csv", catalog)
        summary = quality_summary(con)
        write_csv(OUT_DIR / "vlak_survivor_signal_quality_summary.csv", summary, ["metric", "value"])
        if backfill_result is None:
            backfill_result = {"inserted": 0, "updated": 0, "total": con.execute("SELECT COUNT(*) FROM vlak_survivor_signals").fetchone()[0], "duplicates": 0}
        write_csv(OUT_DIR / "vlak_survivor_signals_backfill_summary.csv", [backfill_result], ["inserted", "updated", "total", "duplicates"])
    md = [
        "# Vlak Survivor Signals Research Layer",
        "",
        "## Purpose",
        "Telegram delivery stays minimal. `vlak_survivor_signals` is the research truth table for every token that crosses the survivor threshold, including live, dry-run, shadow-only, and pre-live qualified tokens.",
        "",
        "## Integration",
        "- Raw Vlak ingestion is unchanged and remains silent.",
        "- Outcome refresh calls the survivor research upsert after `save_outcome()`.",
        "- Telegram survivor formatting, triggers, milestone threading, and existing deduplication are not changed by this layer.",
        "",
        "## Primary Tables",
        "- `vlak_survivor_signals`: one row per mint, primary key `mint`.",
        "- `vlak_api_field_catalog`: observed Vlak API/raw payload fields and storage mapping.",
        "",
        "## Metric Sources",
        "- First spotted values: `vlak_alert_events` first alert per mint.",
        "- Survivor crossing values: earliest `vlak_alert_events`, `vlak_metric_snapshots`, or `vlak_outcome_snapshots` crossing `1.4x`.",
        "- Outcome values: best of Vlak outcome endpoint and Vlak metric snapshot market-cap history.",
        "- Telegram delivery values: `telegram_survivor_threads` and `telegram_survivor_milestones`.",
        "- Shadow/pre-live values: `telegram_survivor_shadow_exclusions`.",
        "",
        "## Missing/Weak Fields",
        "- Sells and sell volume columns exist in metric snapshots but currently have no usable populated values.",
        "- Creator/dev wallet is not observed as a dedicated field in sampled payloads; dev holding percent is observed.",
        "- Top-holder wallet list is observed in raw JSON but not exploded into this compact survivor table; top10 percent is stored.",
    ]
    (OUT_DIR / "vlak_survivor_signals_schema_report.md").write_text("\n".join(md), encoding="utf-8")


def main() -> None:
    migrate(DB_PATH)
    backfill = backfill_survivor_signals(DB_PATH)
    populate_api_field_catalog(DB_PATH)
    write_reports(DB_PATH, backfill)
    print("backfill", backfill)
    print(OUT_DIR / "vlak_survivor_signals_schema_report.md")
    print(OUT_DIR / "vlak_api_field_catalog.csv")
    print(OUT_DIR / "vlak_survivor_signals_backfill_summary.csv")
    print(OUT_DIR / "vlak_survivor_signal_quality_summary.csv")


if __name__ == "__main__":
    main()
