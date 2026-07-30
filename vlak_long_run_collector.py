from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import random
import signal
import socket
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

try:
    import websockets
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency: websockets. Run: .venv\\Scripts\\python.exe -m pip install -r requirements.txt"
    ) from exc

from aladdin_research_engine.normalizers import extract_signal_list, normalize_signal
from aladdin_research_engine.utils import number_or_none, pick
from migrate_vlak_long_run_schema import migrate
from vlak_alert_entry_feature_matrix import upsert_alert_entry_row
from vlak_research_metrics_store import store_api_metric_snapshot, store_outcome_milestones
from vlak_survivor_research import upsert_survivor_signal
from vlak_survivor_telegram import SurvivorTelegramAlerts

ROOT = Path(__file__).resolve().parent
DEFAULT_DB_PATH = ROOT / "vlak_aladdin_research.sqlite"
DEFAULT_BASE_URL = "https://api.somehowissomewhere.uk"
DEFAULT_WS_URL = "wss://api.somehowissomewhere.uk/ws"
TRACKING_CHECKPOINTS = [1, 3, 5, 10, 15, 30, 60, 120, 1440]
PRE_SURVIVOR_POLL_SECONDS = 15
PRE_SURVIVOR_LABEL_PREFIX = "pre_survivor"
POST_TELEGRAM_PROGRESSIVE_POLL_MINUTES = [2]
POST_TELEGRAM_INACTIVE_AFTER_MINUTES = 30
POST_TELEGRAM_LONG_TAIL_POLL_HOURS = 12
POST_TELEGRAM_LONG_TAIL_SEED_LIMIT_PER_LOOP = 20
POST_TELEGRAM_LONG_TAIL_SEED_SPACING_SECONDS = 10
ACTIVE_POLL_LIMIT_PER_LOOP = 10
SCHEDULE_POLL_LIMIT_PER_LOOP = 15
LOG_DIR = ROOT / "logs"
REPORT_DIR = ROOT / "research_outputs" / "vlak_long_run_collector"
TOP_GAINS_TIMEZONE = ZoneInfo("Europe/London")
TOP_GAINS_SEND_HOUR = 23
TOP_GAINS_SEND_MINUTE = 59


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_now_iso() -> str:
    return utc_now().isoformat(timespec="seconds")


def json_dumps(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def payload_hash(payload: Any) -> str:
    return hashlib.sha256(json_dumps(payload).encode("utf-8")).hexdigest()


def redact(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "[REDACTED]"
    return f"{value[:4]}...[REDACTED]...{value[-4:]}"


def env_value(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value:
        return value
    env_path = ROOT / ".env"
    if not env_path.exists():
        return default
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        if key.strip() == name:
            return raw_value.strip().strip('"').strip("'")
    return default


def parse_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    number = number_or_none(value)
    if number is not None:
        if number > 10_000_000_000:
            number /= 1000
        try:
            return datetime.fromtimestamp(number, UTC)
        except (OverflowError, OSError, ValueError):
            return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def to_iso(value: Any) -> str | None:
    parsed = parse_time(value)
    return parsed.isoformat(timespec="seconds") if parsed else (str(value) if value else None)


def missing_fields(row: dict[str, Any], fields: list[str]) -> str:
    return ";".join(field for field in fields if row.get(field) in (None, ""))


def extract_holders(raw: dict[str, Any]) -> dict[str, Any]:
    holders = pick(raw, "holders", "holderStats", default={}) or {}
    return holders if isinstance(holders, dict) else {}


def extract_trackers(raw: dict[str, Any]) -> dict[str, Any]:
    trackers = pick(raw, "trackers", default={}) or {}
    return trackers if isinstance(trackers, dict) else {}


def normalized_alert_metrics(raw: dict[str, Any]) -> dict[str, Any]:
    alert = normalize_signal(raw)
    holders = extract_holders(raw)
    trackers = extract_trackers(raw)
    alert_time = to_iso(alert.get("first_call_time") or alert.get("sent_at") or alert.get("created_at"))
    alert_dt = parse_time(alert_time)
    capture_lag = (utc_now() - alert_dt).total_seconds() if alert_dt else None
    market_cap = number_or_none(alert.get("market_cap"))
    first_call_mc = number_or_none(alert.get("first_call_market_cap"))
    liquidity = number_or_none(alert.get("liquidity"))
    volume = number_or_none(alert.get("vol_1h"))
    buys = int(number_or_none(alert.get("count_buy")) or 0)
    buy_volume_sol = number_or_none(pick(trackers, "totalBuy", "total_buy", "buyVolumeSol") or alert.get("total_buy"))
    sell_volume_sol = number_or_none(pick(trackers, "totalSell", "total_sell", "sellVolumeSol"))
    return {
        "notification_id": alert.get("notification_id"),
        "mint": alert.get("mint"),
        "symbol": alert.get("symbol"),
        "name": alert.get("name"),
        "alert_time": alert_time,
        "first_call_market_cap": first_call_mc,
        "market_cap": market_cap,
        "liquidity": liquidity,
        "price": number_or_none(alert.get("price_usd")),
        "volume": volume,
        "buy_volume_sol": buy_volume_sol,
        "sell_volume_sol": sell_volume_sol,
        "buys": buys,
        "holders": int(number_or_none(pick(holders, "total", "holderCount", "holders")) or 0) or None,
        "bundle_percent": number_or_none(pick(holders, "bundleHoldPercent", "bundle_pct")),
        "sniper_percent": number_or_none(pick(holders, "sniperHoldPercent", "sniper_pct")),
        "top10_percent": number_or_none(pick(holders, "top10Percent", "top10_percent")),
        "liq_to_mc": liquidity / market_cap if liquidity and market_cap else None,
        "vol_to_mc": volume / market_cap if volume and market_cap else None,
        "avg_buy_size_sol": buy_volume_sol / buys if buy_volume_sol is not None and buys else None,
        "capture_lag_seconds": capture_lag,
        "raw_json": json_dumps(raw),
        "raw_payload_hash": payload_hash(raw),
    }


def nested_number(payload: dict[str, Any], *paths: tuple[str, ...]) -> float | None:
    for path in paths:
        current: Any = payload
        for part in path:
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(part)
        value = number_or_none(current)
        if value is not None:
            return value
    return None


def outcome_max_market_cap(payload: dict[str, Any]) -> float | None:
    candidates: list[float] = []
    for value in [
        nested_number(payload, ("currentMc",), ("current_mc",)),
        nested_number(payload, ("marketCap",), ("market_cap",), ("pool", "marketCap")),
        nested_number(payload, ("athMarketCap",), ("ath_mc",), ("athMc",)),
    ]:
        if value is not None:
            candidates.append(value)
    outcome = payload.get("outcome") if isinstance(payload.get("outcome"), dict) else {}
    for key in ("max_mc_10m", "max_mc_30m", "max_mc_1h", "max_mc_24h"):
        value = number_or_none(outcome.get(key))
        if value is not None:
            candidates.append(value)
    milestones = payload.get("milestones") if isinstance(payload.get("milestones"), dict) else {}
    nested = milestones.get("milestones") if isinstance(milestones.get("milestones"), dict) else {}
    for item in list(nested.values()) + list(milestones.get("timeline", []) if isinstance(milestones.get("timeline"), list) else []):
        if isinstance(item, dict):
            value = number_or_none(item.get("mc"))
            if value is not None:
                candidates.append(value)
    return max(candidates) if candidates else None


def normalized_outcome_metrics(mint: str, payload: dict[str, Any]) -> dict[str, Any]:
    pool = payload.get("pool") if isinstance(payload.get("pool"), dict) else {}
    current_mc = nested_number(payload, ("currentMc",), ("current_mc",), ("pool", "marketCap"))
    call_mc = nested_number(payload, ("firstCallMarketCap",), ("first_call_market_cap",), ("callMc",))
    ath_mc = outcome_max_market_cap(payload)
    explicit_multiple = nested_number(payload, ("maxMultiple",), ("max_multiple",))
    computed_multiple = (ath_mc / call_mc) if ath_mc is not None and call_mc else None
    return {
        "mint": mint,
        "snapshot_time": utc_now_iso(),
        "current_mc": current_mc,
        "first_call_market_cap": call_mc,
        "ath_market_cap": ath_mc,
        "max_multiple": explicit_multiple if explicit_multiple is not None else computed_multiple,
        "liquidity": nested_number(payload, ("liquidity",), ("pool", "liquidUsd")),
        "price": nested_number(payload, ("price",), ("priceUsd",), ("pool", "priceUsd")),
        "market_cap": nested_number(payload, ("marketCap",), ("market_cap",), ("pool", "marketCap")),
        "updated_at": str(payload.get("updatedAt") or payload.get("updated_at") or pool.get("updatedAt") or "") or None,
        "raw_json": json_dumps(payload),
        "raw_payload_hash": payload_hash(payload),
    }


def extract_outcome_buy_count(payload: dict[str, Any]) -> int | None:
    """Return the most stable buy-count signal available from an outcome payload.

    Vlak outcome payloads commonly include rolling poolReports. For active
    polling we use the largest observed buyCount across report windows so a
    shorter rolling interval cannot falsely reset activity lower than a longer
    interval. Missing/unparseable values return None and never mark inactive.
    """
    candidates: list[int] = []
    pool = payload.get("pool") if isinstance(payload.get("pool"), dict) else {}
    reports = pool.get("poolReports") if isinstance(pool.get("poolReports"), list) else []
    for report in reports:
        if not isinstance(report, dict):
            continue
        value = number_or_none(pick(report, "buyCount", "buy_count", "buys"))
        if value is not None:
            candidates.append(int(value))
    for path in [
        ("buyCount",),
        ("buy_count",),
        ("buys",),
        ("pool", "buyCount"),
        ("pool", "buy_count"),
        ("pool", "txns", "buys"),
        ("pool", "txns", "buyCount"),
    ]:
        value = nested_number(payload, path)
        if value is not None:
            candidates.append(int(value))
    return max(candidates) if candidates else None

@dataclass(frozen=True)
class CollectorConfig:
    api_key: str
    db_path: Path
    base_url: str = DEFAULT_BASE_URL
    websocket_url: str = DEFAULT_WS_URL
    signal_ingest_mode: str = "polling"
    signal_poll_seconds: float = 10.0
    rest_min_interval_seconds: float = 1.5
    websocket_reconnect_min_seconds: float = 2.0
    websocket_reconnect_max_seconds: float = 60.0
    outcome_retry_limit: int = 3

    @classmethod
    def from_env(cls) -> "CollectorConfig":
        load_dotenv(ROOT / ".env")
        api_key = env_value("VLAK_API_KEY").strip()
        if not api_key:
            raise RuntimeError("Missing VLAK_API_KEY in environment or .env")
        return cls(
            api_key=api_key,
            db_path=Path(env_value("DATABASE_PATH", str(DEFAULT_DB_PATH))),
            base_url=env_value("VLAK_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
            websocket_url=env_value("VLAK_WS_URL", DEFAULT_WS_URL).rstrip("?"),
            signal_ingest_mode=env_value("VLAK_SIGNAL_INGEST_MODE", "polling").strip().lower(),
            signal_poll_seconds=float(env_value("SIGNAL_POLL_SECONDS", "10") or 10),
        )


class VlakLongRunCollector:
    def __init__(self, config: CollectorConfig) -> None:
        self.config = config
        self.stop_event = asyncio.Event()
        self.last_websocket_message_at: str | None = None
        self.last_signal_poll_at: str | None = None
        self.last_outcome_refresh_at: str | None = None
        self.http = httpx.AsyncClient(timeout=30)
        self.survivor_alerts = SurvivorTelegramAlerts(self.config.db_path)
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
            handlers=[
                logging.FileHandler(LOG_DIR / "vlak_long_run_collector.log", encoding="utf-8"),
                logging.StreamHandler(),
            ],
        )
        self.logger = logging.getLogger("vlak_long_run_collector")
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.config.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def ws_url_with_key(self) -> str:
        sep = "&" if "?" in self.config.websocket_url else "?"
        return f"{self.config.websocket_url}{sep}apikey={self.config.api_key}"

    def audit_payload(
        self,
        conn: sqlite3.Connection,
        source: str,
        endpoint: str,
        method: str,
        payload: Any,
        *,
        mint: str | None = None,
        notification_id: str | None = None,
        status_code: int | None = None,
        success: bool = True,
        api_error: str | None = None,
    ) -> None:
        keys = sorted(str(key) for key in payload.keys()) if isinstance(payload, dict) else []
        raw = json_dumps(payload)
        conn.execute(
            """
            INSERT INTO vlak_api_payload_audit
            (received_at, source, endpoint, method, mint, notification_id, status_code, success, api_error, raw_payload_hash, payload_bytes, top_level_keys)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (utc_now_iso(), source, endpoint, method, mint, notification_id, status_code, int(success), api_error, payload_hash(payload), len(raw.encode("utf-8")), ";".join(keys)),
        )

    def log_error(
        self,
        conn: sqlite3.Connection,
        source: str,
        message: str,
        *,
        endpoint: str | None = None,
        mint: str | None = None,
        notification_id: str | None = None,
        error_type: str = "error",
        retry_count: int = 0,
        payload: Any | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO vlak_ingestion_errors
            (occurred_at, source, endpoint, mint, notification_id, error_type, error_message, retry_count, raw_payload_hash, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (utc_now_iso(), source, endpoint, mint, notification_id, error_type, message[:1000], retry_count, payload_hash(payload) if payload is not None else None, json_dumps(payload) if payload is not None else None),
        )

    def save_metric_snapshot(self, conn: sqlite3.Connection, metrics: dict[str, Any], snapshot_kind: str, source: str, is_clean: int, missing: str | None) -> None:
        conn.execute(
            """
            INSERT INTO vlak_metric_snapshots
            (notification_id, mint, snapshot_time, snapshot_kind, first_call_market_cap, market_cap, liquidity, price, volume, buy_volume_sol, sell_volume_sol, buys, sells, holders, bundle_percent, sniper_percent, top10_percent, liq_to_mc, vol_to_mc, avg_buy_size_sol, max_multiple, source, capture_lag_seconds, is_clean_snapshot, missing_fields, api_error, raw_payload_hash, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, NULL, ?, ?)
            """,
            (metrics.get("notification_id"), metrics.get("mint"), utc_now_iso(), snapshot_kind, metrics.get("first_call_market_cap"), metrics.get("market_cap"), metrics.get("liquidity"), metrics.get("price"), metrics.get("volume"), metrics.get("buy_volume_sol"), metrics.get("sell_volume_sol"), metrics.get("buys"), metrics.get("holders"), metrics.get("bundle_percent"), metrics.get("sniper_percent"), metrics.get("top10_percent"), metrics.get("liq_to_mc"), metrics.get("vol_to_mc"), metrics.get("avg_buy_size_sol"), source, metrics.get("capture_lag_seconds"), is_clean, missing, metrics.get("raw_payload_hash"), metrics.get("raw_json")),
        )


    def survivor_state_exists(self, conn: sqlite3.Connection, mint: str) -> bool:
        return bool(
            conn.execute("SELECT 1 FROM telegram_survivor_threads WHERE mint = ?", (mint,)).fetchone()
            or conn.execute("SELECT 1 FROM telegram_survivor_shadow_exclusions WHERE mint = ?", (mint,)).fetchone()
        )

    def complete_pending_pre_survivor_checks(self, conn: sqlite3.Connection, mint: str) -> None:
        conn.execute(
            """
            UPDATE vlak_tracking_schedule
            SET completed_at = COALESCE(completed_at, ?), last_error = NULL
            WHERE mint = ?
              AND completed_at IS NULL
              AND checkpoint_label LIKE ?
            """,
            (utc_now_iso(), mint, f"{PRE_SURVIVOR_LABEL_PREFIX}_%"),
        )


    def schedule_next_pre_survivor_check(
        self,
        conn: sqlite3.Connection,
        mint: str,
        first_alert_time: str | None,
        *,
        from_dt: datetime | None = None,
    ) -> None:
        if self.survivor_state_exists(conn, mint):
            self.complete_pending_pre_survivor_checks(conn, mint)
            return
        outcome = conn.execute("SELECT completed_24h FROM vlak_token_outcomes WHERE mint = ?", (mint,)).fetchone()
        if outcome and outcome["completed_24h"] == 1:
            self.complete_pending_pre_survivor_checks(conn, mint)
            return
        now_dt = from_dt or utc_now()
        now = utc_now_iso()
        conn.execute(
            """
            UPDATE vlak_tracking_schedule
            SET completed_at = COALESCE(completed_at, ?), last_error = NULL
            WHERE mint = ?
              AND completed_at IS NULL
              AND checkpoint_label LIKE ?
            """,
            (now, mint, f"{PRE_SURVIVOR_LABEL_PREFIX}_%"),
        )
        due_at = (now_dt + timedelta(seconds=PRE_SURVIVOR_POLL_SECONDS)).isoformat(timespec="seconds")
        label = f"{PRE_SURVIVOR_LABEL_PREFIX}_{int(now_dt.timestamp())}"
        conn.execute(
            """
            INSERT OR IGNORE INTO vlak_tracking_schedule
            (mint, first_alert_time, checkpoint_label, checkpoint_minutes, due_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                mint,
                (parse_time(first_alert_time) or now_dt).isoformat(timespec="seconds"),
                label,
                PRE_SURVIVOR_POLL_SECONDS / 60,
                due_at,
                now,
            ),
        )
    def telegram_thread_exists(self, conn: sqlite3.Connection, mint: str) -> bool:
        return bool(conn.execute("SELECT 1 FROM telegram_survivor_threads WHERE mint = ?", (mint,)).fetchone())

    def post_telegram_progressive_due_at(self, now_dt: datetime, checks_count: int | None) -> str:
        cycle_index = int(checks_count or 0) % len(POST_TELEGRAM_PROGRESSIVE_POLL_MINUTES)
        minutes = POST_TELEGRAM_PROGRESSIVE_POLL_MINUTES[cycle_index]
        return (now_dt + timedelta(minutes=minutes)).isoformat(timespec="seconds")

    def post_telegram_long_tail_due_at(self, now_dt: datetime) -> str:
        return (now_dt + timedelta(hours=POST_TELEGRAM_LONG_TAIL_POLL_HOURS)).isoformat(timespec="seconds")

    def seed_sleeping_survivor_long_tail_checks(self, conn: sqlite3.Connection) -> None:
        now_dt = utc_now()
        rows = conn.execute(
            """
            SELECT mint
            FROM telegram_survivor_active_polling
            WHERE status IN ('inactive', 'missing_buy_count')
              AND next_due_at IS NULL
            ORDER BY datetime(COALESCE(inactive_at, updated_at, created_at)) ASC
            LIMIT ?
            """,
            (POST_TELEGRAM_LONG_TAIL_SEED_LIMIT_PER_LOOP,),
        ).fetchall()
        for index, row in enumerate(rows):
            due_at = (now_dt + timedelta(seconds=index * POST_TELEGRAM_LONG_TAIL_SEED_SPACING_SECONDS)).isoformat(timespec="seconds")
            conn.execute(
                """
                UPDATE telegram_survivor_active_polling
                SET next_due_at = ?, updated_at = ?
                WHERE mint = ? AND next_due_at IS NULL
                """,
                (due_at, utc_now_iso(), row["mint"]),
            )

    def ensure_post_telegram_active_polling(self, conn: sqlite3.Connection, mint: str) -> None:
        thread = conn.execute(
            "SELECT first_alerted_at FROM telegram_survivor_threads WHERE mint = ?",
            (mint,),
        ).fetchone()
        if not thread:
            return
        now = utc_now_iso()
        outcome = conn.execute("SELECT completed_24h FROM vlak_token_outcomes WHERE mint = ?", (mint,)).fetchone()
        is_completed = bool(outcome and outcome["completed_24h"] == 1)
        conn.execute(
            """
            INSERT OR IGNORE INTO telegram_survivor_active_polling
            (mint, status, first_alerted_at, next_due_at, inactive_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (mint, "inactive" if is_completed else "active", thread["first_alerted_at"], self.post_telegram_long_tail_due_at(utc_now()) if is_completed else now, now if is_completed else None, now, now),
        )

    def update_post_telegram_active_polling(
        self,
        conn: sqlite3.Connection,
        mint: str,
        payload: dict[str, Any] | None,
        *,
        fetched_at: str | None = None,
    ) -> None:
        if not self.telegram_thread_exists(conn, mint):
            return
        outcome = conn.execute("SELECT completed_24h FROM vlak_token_outcomes WHERE mint = ?", (mint,)).fetchone()
        if outcome and outcome["completed_24h"] == 1:
            now = (parse_time(fetched_at) or utc_now()).isoformat(timespec="seconds")
            self.ensure_post_telegram_active_polling(conn, mint)
            conn.execute(
                """
                UPDATE telegram_survivor_active_polling
                SET status = 'inactive', next_due_at = ?, inactive_at = COALESCE(inactive_at, ?), last_checked_at = ?, updated_at = ?
                WHERE mint = ?
                """,
                (self.post_telegram_long_tail_due_at(parse_time(now) or utc_now()), now, now, now, mint),
            )
            return
        self.ensure_post_telegram_active_polling(conn, mint)
        state = conn.execute(
            "SELECT * FROM telegram_survivor_active_polling WHERE mint = ?",
            (mint,),
        ).fetchone()
        if not state:
            return
        now_dt = parse_time(fetched_at) or utc_now()
        now = now_dt.isoformat(timespec="seconds")
        buy_count = extract_outcome_buy_count(payload or {})
        if buy_count is None:
            conn.execute(
                """
                UPDATE telegram_survivor_active_polling
                SET status = 'missing_buy_count',
                    last_checked_at = ?,
                    next_due_at = ?,
                    missing_buy_count_count = missing_buy_count_count + 1,
                    checks_count = checks_count + 1,
                    updated_at = ?
                WHERE mint = ?
                """,
                (now, self.post_telegram_long_tail_due_at(now_dt), now, mint),
            )
            return
        last_buy_count = state["last_buy_count"]
        no_increase_since = parse_time(state["no_buy_increase_since"])
        if last_buy_count is None or buy_count > int(last_buy_count):
            next_due = self.post_telegram_progressive_due_at(now_dt, state["checks_count"])
            conn.execute(
                """
                UPDATE telegram_survivor_active_polling
                SET status = 'active',
                    last_buy_count = ?,
                    last_buy_count_at = ?,
                    last_checked_at = ?,
                    no_buy_increase_since = NULL,
                    inactive_at = NULL,
                    next_due_at = ?,
                    checks_count = checks_count + 1,
                    updated_at = ?
                WHERE mint = ?
                """,
                (buy_count, now, now, next_due, now, mint),
            )
            return
        if no_increase_since is None:
            no_increase_since = now_dt
        inactive_at = None
        status = "active"
        next_due = self.post_telegram_progressive_due_at(now_dt, state["checks_count"])
        if now_dt >= no_increase_since + timedelta(minutes=POST_TELEGRAM_INACTIVE_AFTER_MINUTES):
            status = "inactive"
            inactive_at = now
            next_due = self.post_telegram_long_tail_due_at(now_dt)
        conn.execute(
            """
            UPDATE telegram_survivor_active_polling
            SET status = ?,
                last_buy_count = ?,
                last_checked_at = ?,
                no_buy_increase_since = ?,
                inactive_at = COALESCE(inactive_at, ?),
                next_due_at = ?,
                checks_count = checks_count + 1,
                updated_at = ?
            WHERE mint = ?
            """,
            (status, buy_count, now, no_increase_since.isoformat(timespec="seconds"), inactive_at, next_due, now, mint),
        )

    async def process_outcome_for_mint(
        self,
        mint: str,
        *,
        schedule_id: int | None = None,
        attempts: int = 0,
        checkpoint_label: str | None = None,
        active_poll: bool = False,
    ) -> None:
        payload, error, status_code = await self.fetch_outcome(mint)
        with self.connect() as conn:
            if schedule_id is not None:
                conn.execute("UPDATE vlak_tracking_schedule SET attempts = attempts + 1 WHERE id = ?", (schedule_id,))
            if payload is None:
                if schedule_id is not None:
                    conn.execute("UPDATE vlak_tracking_schedule SET last_error = ? WHERE id = ?", (error, schedule_id))
                self.log_error(conn, "vlak_outcome_endpoint", error or "unknown outcome error", endpoint=f"/api/signal/{mint}/outcome", mint=mint, retry_count=int(attempts or 0) + 1)
                self.audit_payload(conn, "vlak_outcome_endpoint", f"/api/signal/{mint}/outcome", "GET", {"error": error}, mint=mint, status_code=status_code, success=False, api_error=error)
            elif schedule_id is not None:
                conn.execute("UPDATE vlak_tracking_schedule SET completed_at = ?, last_error = NULL WHERE id = ?", (utc_now_iso(), schedule_id))
            conn.commit()
        if payload is None:
            return
        self.save_outcome(mint, payload, status_code=status_code)
        try:
            upsert_survivor_signal(self.config.db_path, mint)
        except Exception as exc:
            self.logger.warning("Survivor research upsert failed mint=%s error=%s", mint, exc)
        await self.survivor_alerts.process_mint(mint)
        with self.connect() as conn:
            if self.telegram_thread_exists(conn, mint):
                self.ensure_post_telegram_active_polling(conn, mint)
                self.update_post_telegram_active_polling(conn, mint, payload)
            if self.survivor_state_exists(conn, mint):
                self.complete_pending_pre_survivor_checks(conn, mint)
            elif checkpoint_label and str(checkpoint_label).startswith(f"{PRE_SURVIVOR_LABEL_PREFIX}_"):
                first_alert_time = conn.execute(
                    "SELECT first_alert_time FROM vlak_tracking_schedule WHERE id = ?",
                    (schedule_id,),
                ).fetchone() if schedule_id is not None else None
                self.schedule_next_pre_survivor_check(
                    conn,
                    mint,
                    first_alert_time["first_alert_time"] if first_alert_time else None,
                )
            conn.commit()
        try:
            upsert_alert_entry_row(self.config.db_path, mint)
        except Exception as exc:
            self.logger.warning("Alert-entry matrix upsert failed mint=%s error=%s", mint, exc)

    def create_tracking_schedule(self, conn: sqlite3.Connection, mint: str, alert_time: str) -> None:
        alert_dt = parse_time(alert_time) or utc_now()
        now = utc_now_iso()
        for minutes in TRACKING_CHECKPOINTS:
            due_at = (alert_dt + timedelta(minutes=minutes)).isoformat(timespec="seconds")
            label = f"{int(minutes)}m" if minutes < 1440 else "24h"
            conn.execute(
                """
                INSERT OR IGNORE INTO vlak_tracking_schedule
                (mint, first_alert_time, checkpoint_label, checkpoint_minutes, due_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (mint, alert_dt.isoformat(timespec="seconds"), label, minutes, due_at, now),
            )
        self.schedule_next_pre_survivor_check(conn, mint, alert_dt.isoformat(timespec="seconds"), from_dt=alert_dt)

    def save_alert(self, raw: dict[str, Any], source: str = "vlak_websocket") -> str | None:
        metrics = normalized_alert_metrics(raw)
        mint = metrics.get("mint")
        if not mint:
            with self.connect() as conn:
                self.log_error(conn, "vlak_websocket", "Missing mint in websocket signal", payload=raw)
                self.audit_payload(conn, "vlak_websocket", "websocket", "MESSAGE", raw, success=False, api_error="missing_mint")
                conn.commit()
            return None
        with self.connect() as conn:
            existing_for_mint = conn.execute("SELECT COUNT(1) FROM vlak_alert_events WHERE mint = ?", (mint,)).fetchone()[0]
            duplicate_count = conn.execute("SELECT COUNT(1) FROM vlak_alert_events WHERE notification_id = ?", (metrics.get("notification_id"),)).fetchone()[0] if metrics.get("notification_id") else 0
            is_first = existing_for_mint == 0
            capture_lag = metrics.get("capture_lag_seconds")
            is_clean = bool(is_first and capture_lag is not None and capture_lag <= 300)
            missing = missing_fields(metrics, ["mint", "alert_time", "first_call_market_cap", "market_cap", "liquidity", "volume", "buys"])
            conn.execute(
                """
                INSERT OR IGNORE INTO vlak_alert_events
                (notification_id, mint, symbol, name, alert_time, first_call_market_cap, market_cap, liquidity, volume, buys, holders, bundle_percent, sniper_percent, top10_percent, source, inserted_at, capture_lag_seconds, is_first_alert_per_mint, is_clean_first_snapshot, missing_fields, api_error, duplicate_alert_count, raw_payload_hash, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
                """,
                (metrics.get("notification_id"), mint, metrics.get("symbol"), metrics.get("name"), metrics.get("alert_time"), metrics.get("first_call_market_cap"), metrics.get("market_cap"), metrics.get("liquidity"), metrics.get("volume"), metrics.get("buys"), metrics.get("holders"), metrics.get("bundle_percent"), metrics.get("sniper_percent"), metrics.get("top10_percent"), source, utc_now_iso(), capture_lag, int(is_first), int(is_clean), missing, duplicate_count, metrics.get("raw_payload_hash"), metrics.get("raw_json")),
            )
            inserted = conn.execute("SELECT changes()").fetchone()[0]
            self.save_metric_snapshot(conn, metrics, "alert", source, int(is_clean), missing)
            self.audit_payload(conn, source, source, "MESSAGE", raw, mint=mint, notification_id=metrics.get("notification_id"))
            store_api_metric_snapshot(conn, source, source, raw, observed_at=utc_now_iso(), raw_payload_hash=metrics.get("raw_payload_hash"), notification_id=metrics.get("notification_id"), mint=mint)
            if inserted:
                self.create_tracking_schedule(conn, mint, metrics.get("alert_time") or utc_now_iso())
            conn.commit()
        return mint


    def signal_key(self, raw: dict[str, Any]) -> str:
        alert = normalize_signal(raw)
        notification_id = alert.get("notification_id")
        if notification_id:
            return f"notification:{notification_id}"
        mint = alert.get("mint") or "missing_mint"
        alert_time = alert.get("alert_time") or alert.get("created_at") or "missing_time"
        return f"mint_time:{mint}:{alert_time}"

    async def fetch_signals(self) -> tuple[Any | None, str | None, int | None]:
        url = f"{self.config.base_url}/api/signals"
        try:
            response = await self.http.get(url, params={"apikey": self.config.api_key})
            if response.status_code == 429:
                return None, "rate_limited", response.status_code
            response.raise_for_status()
            return response.json(), None, response.status_code
        except httpx.HTTPStatusError as exc:
            return None, exc.response.text[:500], exc.response.status_code
        except Exception as exc:
            return None, str(exc), None

    async def polling_loop(self) -> None:
        seen_signal_keys: set[str] = set()
        baseline_loaded = False
        while not self.stop_event.is_set():
            payload, error, status_code = await self.fetch_signals()
            self.last_signal_poll_at = utc_now_iso()
            if payload is None:
                self.logger.warning("Vlak polling fetch failed status=%s error=%s", status_code, error)
                with self.connect() as conn:
                    error_message = error or "unknown polling error"
                    if status_code is not None:
                        error_message = f"HTTP {status_code}: {error_message}"
                    self.log_error(conn, "vlak_polling", error_message, endpoint="/api/signals")
                    self.audit_payload(conn, "vlak_polling", "/api/signals", "GET", {"error": error}, status_code=status_code, success=False, api_error=error)
                    conn.commit()
                await asyncio.sleep(self.config.signal_poll_seconds)
                continue
            signals = extract_signal_list(payload)
            if not baseline_loaded:
                for raw in signals:
                    seen_signal_keys.add(self.signal_key(raw))
                    mint = self.save_alert(raw, source="vlak_polling")
                    if mint:
                        self.logger.info("Captured Vlak polling baseline signal mint=%s", mint)
                baseline_loaded = True
                self.logger.info("Vlak polling baseline loaded signals=%s", len(signals))
                await asyncio.sleep(self.config.signal_poll_seconds)
                continue
            new_count = 0
            for raw in signals:
                key = self.signal_key(raw)
                if key in seen_signal_keys:
                    continue
                seen_signal_keys.add(key)
                mint = self.save_alert(raw, source="vlak_polling")
                if mint:
                    new_count += 1
                    self.logger.info("Captured Vlak polling signal mint=%s", mint)
            if new_count:
                self.logger.info("Vlak polling captured new_signals=%s fetched=%s", new_count, len(signals))
            await asyncio.sleep(self.config.signal_poll_seconds)

    async def websocket_loop(self) -> None:
        delay = self.config.websocket_reconnect_min_seconds
        safe_url = self.ws_url_with_key().replace(self.config.api_key, "[REDACTED]")
        while not self.stop_event.is_set():
            try:
                self.logger.info("Connecting Vlak websocket %s", safe_url)
                async with websockets.connect(self.ws_url_with_key(), ping_interval=20, ping_timeout=20, close_timeout=10) as ws:
                    delay = self.config.websocket_reconnect_min_seconds
                    async for message in ws:
                        self.last_websocket_message_at = utc_now_iso()
                        try:
                            payload = json.loads(message) if isinstance(message, str) else json.loads(message.decode("utf-8"))
                        except Exception as exc:
                            with self.connect() as conn:
                                self.log_error(conn, "vlak_websocket", f"Invalid JSON websocket payload: {exc}", payload={"message": str(message)[:1000]})
                                conn.commit()
                            continue
                        for raw in extract_signal_list(payload):
                            mint = self.save_alert(raw, source="vlak_websocket")
                            if mint:
                                self.logger.info("Captured Vlak websocket signal mint=%s", mint)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.logger.warning("Websocket disconnected/error: %s", exc)
                with self.connect() as conn:
                    self.log_error(conn, "vlak_websocket", str(exc), endpoint="websocket", error_type=type(exc).__name__)
                    conn.commit()
                await asyncio.sleep(delay + random.random())
                delay = min(delay * 2, self.config.websocket_reconnect_max_seconds)

    async def fetch_outcome(self, mint: str) -> tuple[dict[str, Any] | None, str | None, int | None]:
        url = f"{self.config.base_url}/api/signal/{mint}/outcome"
        for attempt in range(1, self.config.outcome_retry_limit + 1):
            try:
                response = await self.http.get(url, params={"apikey": self.config.api_key})
                if response.status_code == 429:
                    await asyncio.sleep(min(30, 2 * attempt))
                    continue
                response.raise_for_status()
                payload = response.json()
                return (payload if isinstance(payload, dict) else {"data": payload}, None, response.status_code)
            except Exception as exc:
                if attempt >= self.config.outcome_retry_limit:
                    return None, str(exc), getattr(getattr(exc, "response", None), "status_code", None)
                await asyncio.sleep(min(30, 2**attempt))
        return None, "retry_exhausted", None

    def save_outcome(self, mint: str, payload: dict[str, Any], status_code: int | None = None) -> None:
        metrics = normalized_outcome_metrics(mint, payload)
        missing = missing_fields(metrics, ["current_mc", "first_call_market_cap", "ath_market_cap", "max_multiple"])
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO vlak_outcome_snapshots
                (mint, snapshot_time, current_mc, first_call_market_cap, ath_market_cap, max_multiple, liquidity, price, market_cap, updated_at, source, api_error, missing_fields, raw_payload_hash, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'vlak_outcome_endpoint', NULL, ?, ?, ?)
                """,
                (mint, metrics.get("snapshot_time"), metrics.get("current_mc"), metrics.get("first_call_market_cap"), metrics.get("ath_market_cap"), metrics.get("max_multiple"), metrics.get("liquidity"), metrics.get("price"), metrics.get("market_cap"), metrics.get("updated_at"), missing, metrics.get("raw_payload_hash"), metrics.get("raw_json")),
            )
            self.audit_payload(conn, "vlak_outcome_endpoint", f"/api/signal/{mint}/outcome", "GET", payload, mint=mint, status_code=status_code)
            store_api_metric_snapshot(conn, "vlak_outcome_endpoint", f"/api/signal/{mint}/outcome", payload, observed_at=metrics.get("snapshot_time"), raw_payload_hash=metrics.get("raw_payload_hash"), mint=mint)
            store_outcome_milestones(conn, mint, payload, snapshot_time=metrics.get("snapshot_time"), raw_payload_hash=metrics.get("raw_payload_hash"))
            self.upsert_latest_outcome(conn, metrics)
            conn.commit()
        self.last_outcome_refresh_at = utc_now_iso()

    def upsert_latest_outcome(self, conn: sqlite3.Connection, metrics: dict[str, Any]) -> None:
        mint = metrics["mint"]
        first = conn.execute("SELECT alert_time, first_call_market_cap FROM vlak_alert_events WHERE mint = ? ORDER BY alert_time ASC, id ASC LIMIT 1", (mint,)).fetchone()
        first_alert_time = first["alert_time"] if first else None
        first_call_mc = metrics.get("first_call_market_cap") or (first["first_call_market_cap"] if first else None)
        max_multiple = metrics.get("max_multiple")
        completed_24h = 0
        if first_alert_time:
            first_dt = parse_time(first_alert_time)
            completed_24h = int(bool(first_dt and utc_now() >= first_dt + timedelta(hours=24)))
        conn.execute(
            """
            INSERT INTO vlak_token_outcomes
            (mint, first_alert_time, first_call_market_cap, latest_snapshot_time, current_mc, ath_market_cap, max_multiple, hit_2x, hit_5x, hit_10x, rugged, completed_24h, updated_at, raw_payload_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
            ON CONFLICT(mint) DO UPDATE SET
                first_alert_time=excluded.first_alert_time,
                first_call_market_cap=excluded.first_call_market_cap,
                latest_snapshot_time=excluded.latest_snapshot_time,
                current_mc=excluded.current_mc,
                ath_market_cap=MAX(COALESCE(vlak_token_outcomes.ath_market_cap, 0), COALESCE(excluded.ath_market_cap, 0)),
                max_multiple=MAX(COALESCE(vlak_token_outcomes.max_multiple, 0), COALESCE(excluded.max_multiple, 0)),
                hit_2x=MAX(vlak_token_outcomes.hit_2x, excluded.hit_2x),
                hit_5x=MAX(vlak_token_outcomes.hit_5x, excluded.hit_5x),
                hit_10x=MAX(vlak_token_outcomes.hit_10x, excluded.hit_10x),
                completed_24h=excluded.completed_24h,
                updated_at=excluded.updated_at,
                raw_payload_hash=excluded.raw_payload_hash
            """,
            (mint, first_alert_time, first_call_mc, metrics.get("snapshot_time"), metrics.get("current_mc"), metrics.get("ath_market_cap"), max_multiple, int(bool(max_multiple is not None and max_multiple >= 2)), int(bool(max_multiple is not None and max_multiple >= 5)), int(bool(max_multiple is not None and max_multiple >= 10)), completed_24h, utc_now_iso(), metrics.get("raw_payload_hash")),
        )

    async def outcome_loop(self) -> None:
        while not self.stop_event.is_set():
            with self.connect() as conn:
                self.seed_sleeping_survivor_long_tail_checks(conn)
                conn.commit()
                active_due = conn.execute(
                    """
                    SELECT p.mint
                    FROM telegram_survivor_active_polling p
                    WHERE p.status IN ('active', 'inactive', 'missing_buy_count')
                      AND p.next_due_at IS NOT NULL
                      AND datetime(p.next_due_at) <= datetime('now')
                    ORDER BY
                        CASE p.status
                            WHEN 'active' THEN 0
                            WHEN 'missing_buy_count' THEN 1
                            ELSE 2
                        END ASC,
                        datetime(p.next_due_at) ASC
                    LIMIT ?
                    """,
                    (ACTIVE_POLL_LIMIT_PER_LOOP,),
                ).fetchall()
                due = conn.execute(
                    """
                    SELECT id, mint, checkpoint_label, attempts
                    FROM vlak_tracking_schedule
                    WHERE completed_at IS NULL AND datetime(due_at) <= datetime('now')
                    ORDER BY
                        CASE
                            WHEN datetime(first_alert_time) >= datetime('now', '-2 hours') THEN 0
                            ELSE 1
                        END ASC,
                        datetime(first_alert_time) DESC,
                        CASE
                            WHEN checkpoint_label LIKE ? THEN 0
                            WHEN checkpoint_minutes <= 15 THEN 1
                            ELSE 2
                        END ASC,
                        checkpoint_minutes ASC,
                        datetime(due_at) ASC
                    LIMIT ?
                    """,
                    (f"{PRE_SURVIVOR_LABEL_PREFIX}_%", SCHEDULE_POLL_LIMIT_PER_LOOP),
                ).fetchall()
            if not active_due and not due:
                await asyncio.sleep(10)
                continue
            pre_due = [
                row for row in due
                if str(row["checkpoint_label"] or "").startswith(f"{PRE_SURVIVOR_LABEL_PREFIX}_")
            ]
            other_due = [
                row for row in due
                if not str(row["checkpoint_label"] or "").startswith(f"{PRE_SURVIVOR_LABEL_PREFIX}_")
            ]
            for row in pre_due:
                if self.stop_event.is_set():
                    break
                mint = row["mint"]
                checkpoint_label = row["checkpoint_label"]
                with self.connect() as conn:
                    if self.survivor_state_exists(conn, mint):
                        self.complete_pending_pre_survivor_checks(conn, mint)
                        conn.commit()
                        continue
                await self.process_outcome_for_mint(
                    mint,
                    schedule_id=row["id"],
                    attempts=int(row["attempts"] or 0),
                    checkpoint_label=checkpoint_label,
                )
                await asyncio.sleep(self.config.rest_min_interval_seconds)
            for row in active_due:
                if self.stop_event.is_set():
                    break
                await self.process_outcome_for_mint(row["mint"], active_poll=True)
                await asyncio.sleep(self.config.rest_min_interval_seconds)
            for row in other_due:
                if self.stop_event.is_set():
                    break
                mint = row["mint"]
                checkpoint_label = row["checkpoint_label"]
                await self.process_outcome_for_mint(
                    mint,
                    schedule_id=row["id"],
                    attempts=int(row["attempts"] or 0),
                    checkpoint_label=checkpoint_label,
                )
                await asyncio.sleep(self.config.rest_min_interval_seconds)


    def ensure_daily_top_gains_table(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS telegram_daily_top_gains_summaries (
                report_date TEXT PRIMARY KEY,
                sent_at TEXT NOT NULL,
                telegram_message_id INTEGER,
                token_count INTEGER NOT NULL DEFAULT 0,
                top_multiple REAL,
                report_text TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'vlak'
            )
            """
        )

    def daily_top_gains_rows(self, conn: sqlite3.Connection, local_day: str) -> list[sqlite3.Row]:
        local_start = datetime.fromisoformat(local_day).replace(tzinfo=TOP_GAINS_TIMEZONE)
        local_end = local_start + timedelta(days=1)
        start_utc = local_start.astimezone(UTC).isoformat(timespec="seconds")
        end_utc = local_end.astimezone(UTC).isoformat(timespec="seconds")
        return conn.execute(
            """
            WITH first_events AS (
                SELECT
                    mint,
                    COALESCE(NULLIF(symbol, ''), 'UNKNOWN') AS symbol,
                    COALESCE(NULLIF(name, ''), NULLIF(symbol, ''), 'Unknown') AS name,
                    alert_time,
                    inserted_at,
                    ROW_NUMBER() OVER (PARTITION BY mint ORDER BY datetime(alert_time), id) AS rn
                FROM vlak_alert_events
                WHERE COALESCE(alert_time, inserted_at) >= ?
                  AND COALESCE(alert_time, inserted_at) < ?
            )
            SELECT
                e.mint,
                e.symbol,
                e.name,
                o.max_multiple
            FROM first_events e
            JOIN vlak_token_outcomes o ON o.mint = e.mint
            WHERE e.rn = 1
              AND o.max_multiple >= 5
            ORDER BY o.max_multiple DESC, e.alert_time ASC
            LIMIT 5
            """,
            (start_utc, end_utc),
        ).fetchall()

    def daily_scanned_token_count(self, conn: sqlite3.Connection, local_day: str) -> int:
        local_start = datetime.fromisoformat(local_day).replace(tzinfo=TOP_GAINS_TIMEZONE)
        local_end = local_start + timedelta(days=1)
        start_utc = local_start.astimezone(UTC).isoformat(timespec="seconds")
        end_utc = local_end.astimezone(UTC).isoformat(timespec="seconds")
        row = conn.execute(
            """
            SELECT COUNT(DISTINCT mint)
            FROM vlak_alert_events
            WHERE COALESCE(alert_time, inserted_at) >= ?
              AND COALESCE(alert_time, inserted_at) < ?
            """,
            (start_utc, end_utc),
        ).fetchone()
        return int(row[0] or 0)

    def render_daily_top_gains_message(self, rows: list[sqlite3.Row], scanned_count: int) -> str:
        medals = ["🥇", "🥈", "🥉", "4⃣", "5⃣"]
        lines = [
            "🏆 24h Top Aladdin Gains",
            "",
            f"Total amount of tokens scanned today: {scanned_count}",
            "",
        ]
        if not rows:
            lines.append("No qualifying top gains today.")
        else:
            for index, row in enumerate(rows):
                multiple = int(round(float(row["max_multiple"] or 0)))
                name = str(row["name"] or row["symbol"] or "Unknown")
                symbol = str(row["symbol"] or "UNKNOWN").lstrip("$")
                prefix = medals[index] if index < len(medals) else f"{index + 1}."
                lines.append(f"{prefix} {name} | ${symbol} • {multiple}X")
        lines.extend([
            "",
            "Credit : Aladdin Bot",
        ])
        return "\n".join(lines)

    async def maybe_send_daily_top_gains(self) -> None:
        local_now = datetime.now(TOP_GAINS_TIMEZONE)
        if (local_now.hour, local_now.minute) < (TOP_GAINS_SEND_HOUR, TOP_GAINS_SEND_MINUTE):
            return
        local_day = local_now.date().isoformat()
        with self.connect() as conn:
            self.ensure_daily_top_gains_table(conn)
            already = conn.execute(
                "SELECT 1 FROM telegram_daily_top_gains_summaries WHERE report_date = ?",
                (local_day,),
            ).fetchone()
            if already:
                conn.commit()
                return
            rows = self.daily_top_gains_rows(conn, local_day)
            scanned_count = self.daily_scanned_token_count(conn, local_day)
            text = self.render_daily_top_gains_message(rows, scanned_count)
            conn.execute(
                """
                INSERT INTO telegram_daily_top_gains_summaries
                (report_date, sent_at, telegram_message_id, token_count, top_multiple, report_text)
                VALUES (?, ?, NULL, ?, ?, ?)
                """,
                (
                    local_day,
                    utc_now_iso(),
                    scanned_count,
                    float(rows[0]["max_multiple"]) if rows else None,
                    text,
                ),
            )
            conn.commit()
        message_id = await self.survivor_alerts.send_message(text)
        with self.connect() as conn:
            conn.execute(
                "UPDATE telegram_daily_top_gains_summaries SET telegram_message_id = ? WHERE report_date = ?",
                (message_id, local_day),
            )
            conn.commit()
        self.logger.info("Daily top gains summary sent date=%s message_id=%s rows=%s", local_day, message_id, len(rows))

    async def daily_top_gains_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                await self.maybe_send_daily_top_gains()
            except Exception:
                self.logger.exception("Daily top gains summary failed")
            await asyncio.sleep(30)

    async def heartbeat_loop(self) -> None:
        while not self.stop_event.is_set():
            self.logger.info(
                "heartbeat db=%s last_ws=%s last_outcome=%s api_key=%s",
                self.config.db_path,
                self.last_websocket_message_at,
                self.last_outcome_refresh_at,
                redact(self.config.api_key),
            )
            await self.write_daily_report()
            await asyncio.sleep(3600)

    async def write_daily_report(self) -> None:
        today = utc_now().date().isoformat()
        day_start = f"{today}T00:00:00+00:00"
        with self.connect() as conn:
            values = self.daily_summary_values(conn, day_start)
            report = self.render_daily_report(today, values)
            conn.execute(
                """
                INSERT INTO vlak_daily_summaries
                (report_date, generated_at, new_alerts_collected, unique_mints_collected, outcome_snapshots_collected, completed_24h_outcomes, rate_2x, rate_5x, rate_10x, missing_field_rates_json, ingestion_errors, db_size_bytes, last_websocket_message_at, last_outcome_refresh_at, report_markdown)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(report_date) DO UPDATE SET
                    generated_at=excluded.generated_at,
                    new_alerts_collected=excluded.new_alerts_collected,
                    unique_mints_collected=excluded.unique_mints_collected,
                    outcome_snapshots_collected=excluded.outcome_snapshots_collected,
                    completed_24h_outcomes=excluded.completed_24h_outcomes,
                    rate_2x=excluded.rate_2x,
                    rate_5x=excluded.rate_5x,
                    rate_10x=excluded.rate_10x,
                    missing_field_rates_json=excluded.missing_field_rates_json,
                    ingestion_errors=excluded.ingestion_errors,
                    db_size_bytes=excluded.db_size_bytes,
                    last_websocket_message_at=excluded.last_websocket_message_at,
                    last_outcome_refresh_at=excluded.last_outcome_refresh_at,
                    report_markdown=excluded.report_markdown
                """,
                (today, utc_now_iso(), values["new_alerts"], values["unique_mints"], values["outcome_snapshots"], values["completed_24h"], values["rate_2x"], values["rate_5x"], values["rate_10x"], json_dumps(values["missing_rates"]), values["errors"], values["db_size"], self.last_websocket_message_at, self.last_outcome_refresh_at, report),
            )
            conn.commit()
        (REPORT_DIR / f"vlak_daily_summary_{today}.md").write_text(report, encoding="utf-8")

    def daily_summary_values(self, conn: sqlite3.Connection, day_start: str) -> dict[str, Any]:
        new_alerts = conn.execute("SELECT COUNT(1) FROM vlak_alert_events WHERE inserted_at >= ?", (day_start,)).fetchone()[0]
        unique_mints = conn.execute("SELECT COUNT(DISTINCT mint) FROM vlak_alert_events WHERE inserted_at >= ?", (day_start,)).fetchone()[0]
        outcome_snapshots = conn.execute("SELECT COUNT(1) FROM vlak_outcome_snapshots WHERE snapshot_time >= ?", (day_start,)).fetchone()[0]
        completed_24h = conn.execute("SELECT COUNT(1) FROM vlak_token_outcomes WHERE completed_24h = 1").fetchone()[0]
        row = conn.execute("SELECT AVG(hit_2x), AVG(hit_5x), AVG(hit_10x) FROM vlak_token_outcomes WHERE max_multiple IS NOT NULL").fetchone()
        errors = conn.execute("SELECT COUNT(1) FROM vlak_ingestion_errors WHERE occurred_at >= ?", (day_start,)).fetchone()[0]
        missing_rates: dict[str, float] = {}
        if new_alerts:
            for field in ["first_call_market_cap", "market_cap", "liquidity", "volume", "buys", "holders", "bundle_percent", "sniper_percent", "top10_percent"]:
                count = conn.execute(f"SELECT COUNT(1) FROM vlak_alert_events WHERE inserted_at >= ? AND {field} IS NULL", (day_start,)).fetchone()[0]
                missing_rates[field] = count / new_alerts
        return {
            "new_alerts": new_alerts,
            "unique_mints": unique_mints,
            "outcome_snapshots": outcome_snapshots,
            "completed_24h": completed_24h,
            "rate_2x": row[0] if row else None,
            "rate_5x": row[1] if row else None,
            "rate_10x": row[2] if row else None,
            "missing_rates": missing_rates,
            "errors": errors,
            "db_size": self.config.db_path.stat().st_size if self.config.db_path.exists() else 0,
        }

    def render_daily_report(self, today: str, values: dict[str, Any]) -> str:
        def pct(value: Any) -> str:
            return "n/a" if value is None else f"{float(value) * 100:.2f}%"

        missing_lines = "\n".join(f"- {key}: {pct(value)}" for key, value in sorted(values["missing_rates"].items())) or "- n/a"
        return f"""# Vlak Long-Run Daily Summary - {today}

- New alerts collected: {values['new_alerts']}
- Unique mints collected: {values['unique_mints']}
- Outcome snapshots collected: {values['outcome_snapshots']}
- Completed 24h outcomes: {values['completed_24h']}
- 2x rate: {pct(values['rate_2x'])}
- 5x rate: {pct(values['rate_5x'])}
- 10x rate: {pct(values['rate_10x'])}
- Ingestion errors today: {values['errors']}
- DB size bytes: {values['db_size']}
- Last successful WebSocket message time: {self.last_websocket_message_at or 'n/a'}
- Last successful polling time: {self.last_signal_poll_at or 'n/a'}
- Last successful outcome refresh time: {self.last_outcome_refresh_at or 'n/a'}

## Missing Field Rates Today

{missing_lines}
"""

    async def run(self) -> None:
        migrate(self.config.db_path)
        self.logger.info(
            "Starting Vlak long-run collector db=%s base_url=%s ws=%s signal_mode=%s poll_seconds=%s api_key=%s",
            self.config.db_path,
            self.config.base_url,
            self.config.websocket_url,
            self.config.signal_ingest_mode,
            self.config.signal_poll_seconds,
            redact(self.config.api_key),
        )
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, self.stop_event.set)
        async def supervise(name: str, loop_factory: Any) -> None:
            while not self.stop_event.is_set():
                try:
                    await loop_factory()
                    if not self.stop_event.is_set():
                        self.logger.error("%s task exited unexpectedly; restarting", name)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self.logger.exception("%s task crashed; restarting", name)
                if not self.stop_event.is_set():
                    await asyncio.sleep(max(1.0, self.config.signal_poll_seconds))

        signal_tasks = []
        if self.config.signal_ingest_mode in {"polling", "both"}:
            signal_tasks.append(asyncio.create_task(supervise("Vlak polling", self.polling_loop)))
        if self.config.signal_ingest_mode in {"websocket", "both"}:
            signal_tasks.append(asyncio.create_task(supervise("Vlak websocket", self.websocket_loop)))
        if not signal_tasks:
            raise RuntimeError(f"Unsupported VLAK_SIGNAL_INGEST_MODE={self.config.signal_ingest_mode!r}")
        tasks = [
            *signal_tasks,
            asyncio.create_task(self.outcome_loop()),
            asyncio.create_task(self.heartbeat_loop()),
            asyncio.create_task(self.daily_top_gains_loop()),
        ]
        await self.stop_event.wait()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self.http.aclose()
        await self.survivor_alerts.close()
        await self.write_daily_report()
        self.logger.info("Stopped Vlak long-run collector")


async def main() -> None:
    lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock_socket.bind(("127.0.0.1", 49322))
        lock_socket.listen(1)
    except OSError:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger("vlak_long_run_collector").error("Vlak long-run collector is already running; exiting duplicate process")
        lock_socket.close()
        return
    try:
        collector = VlakLongRunCollector(CollectorConfig.from_env())
        await collector.run()
    finally:
        lock_socket.close()


if __name__ == "__main__":
    asyncio.run(main())
















