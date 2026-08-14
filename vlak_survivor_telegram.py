from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
ARMING_THRESHOLD = 1.4
FIRST_ALERT_MIN_MULTIPLE = 1.4
FIRST_ALERT_MAX_MULTIPLE = 2.5
ROOT_THRESHOLD = FIRST_ALERT_MIN_MULTIPLE
ROOT_ALERT_MAX_MULTIPLE = FIRST_ALERT_MAX_MULTIPLE
SURVIVOR_THRESHOLDS = [1.5, 2, 3, 4, 5, 10]
REPLY_THRESHOLDS = [2, 3, 4, 5, 10]
ATH_UPDATE_STEP_MULTIPLE = 0.5
MILESTONE_ROOT_ALERT_CUTOFF_AT = "2026-07-10T00:00:00+00:00"

logger = logging.getLogger(__name__)


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


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


def bool_env(name: str, default: bool) -> bool:
    raw = env_value(name, "")
    if raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def int_env(name: str, default: int) -> int:
    raw = env_value(name, "")
    if raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def elapsed_text(start: Any, end: Any | None = None) -> str:
    start_dt = parse_time(start)
    end_dt = parse_time(end) if end else datetime.now(UTC)
    if not start_dt or not end_dt:
        return "n/a"
    seconds = max(0, int((end_dt - start_dt).total_seconds()))
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minutes"
    hours = minutes // 60
    remain = minutes % 60
    if hours < 48:
        return f"{hours}h {remain}m"
    days = hours // 24
    return f"{days}d {hours % 24}h"


def fmt_money(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:.0f}"


def fmt_multiple(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.2f}x"
    except (TypeError, ValueError):
        return "n/a"


def gmgn_link(mint: str) -> str:
    return f"https://gmgn.ai/sol/token/{mint}"


def dexscreener_link(mint: str) -> str:
    return f"https://dexscreener.com/solana/{mint}"


def trojan_link(mint: str | None = None) -> str:
    base = "https://t.me/hector_trojanbot?start=r-ola_crrypt"
    return f"{base}-{mint}" if mint else base


MARKDOWN_V2_SPECIALS = "\\_*[]()~`>#+-=|{}.!"




def html_escape(value: Any) -> str:
    return html.escape("n/a" if value is None else str(value), quote=True)


def fmt_shadow_number(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "n/a"


def fmt_shadow_money(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "n/a"
    return f"${numeric:,.0f}"


def mdv2_escape(value: Any) -> str:
    text = "n/a" if value is None else str(value)
    return "".join(f"\\{char}" if char in MARKDOWN_V2_SPECIALS else char for char in text)


def mdv2_url(value: str) -> str:
    return value.replace("\\", "\\\\").replace(")", "\\)")


def mdv2_bold(value: Any) -> str:
    return f"*{mdv2_escape(value)}*"


def fmt_pct(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return "n/a"


def raw_json_dict(row: sqlite3.Row) -> dict[str, Any]:
    raw = row["first_alert_raw_json"] if "first_alert_raw_json" in row.keys() else None
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def nested_get(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def first_spotted_avg_buy_sol(raw: dict[str, Any]) -> float | None:
    trackers = raw.get("trackers") if isinstance(raw.get("trackers"), dict) else {}
    buy_volume = (
        trackers.get("totalBuy")
        or trackers.get("total_buy")
        or trackers.get("buyVolumeSol")
        or raw.get("totalBuy")
        or raw.get("total_buy")
    )
    buys = (
        trackers.get("countBuy")
        or trackers.get("buyCount")
        or trackers.get("count_buy")
        or raw.get("countBuy")
        or raw.get("buyCount")
    )
    try:
        buy_volume_value = float(buy_volume)
        buys_value = float(buys)
    except (TypeError, ValueError):
        return None
    return buy_volume_value / buys_value if buys_value > 0 else None


def shadow_buy_button_markup(mint: str | None = None) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "🛒 Buy on Trojan",
                    "url": trojan_link(mint),
                }
            ]
        ]
    }


def buy_button_markup(mint: str | None = None) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "Buy Token",
                    "url": trojan_link(mint),
                }
            ]
        ]
    }


def yes_no_icon(value: Any) -> str:
    return "\u2705" if bool(value) else "\u274c"


def token_image_url(row: sqlite3.Row) -> str | None:
    raw = raw_json_dict(row)
    image = raw.get("image")
    return str(image) if image else None


def dev_sold_icon_text(dev_hold_percent: Any) -> str:
    if dev_hold_percent is None:
        return "\u274c (n/a hold)"
    try:
        pct = float(dev_hold_percent)
    except (TypeError, ValueError):
        return "\u274c (n/a hold)"
    icon = "\u2705" if pct <= 0 else "\u274c"
    return f"{icon} ({pct:.2f}% hold)"


def yes_no(value: Any) -> str:
    if value is None:
        return "n/a"
    return "Yes" if bool(value) else "No"


def dev_sold_text(dev_hold_percent: Any) -> str:
    if dev_hold_percent is None:
        return "n/a"
    try:
        pct = float(dev_hold_percent)
    except (TypeError, ValueError):
        return "n/a"
    if pct <= 0:
        return "Yes (0% dev hold)"
    return f"No ({pct:.2f}% dev hold)"


def thresholds_reached(max_multiple: float) -> list[float]:
    return [threshold for threshold in SURVIVOR_THRESHOLDS if max_multiple >= threshold]


def thresholds_waiting(max_multiple: float) -> list[float]:
    return [threshold for threshold in REPLY_THRESHOLDS if max_multiple < threshold]


def ath_update_marker(max_multiple: float) -> float:
    return max(ROOT_THRESHOLD, int(max_multiple / ATH_UPDATE_STEP_MULTIPLE) * ATH_UPDATE_STEP_MULTIPLE)


def telegram_entry_outcome_multiple(overall_multiple: Any, entry_multiple: Any) -> float | None:
    try:
        overall = float(overall_multiple)
        entry = float(entry_multiple)
    except (TypeError, ValueError):
        return None
    if overall <= 0 or entry <= 0:
        return None
    return overall / entry


def telegram_entry_update_marker(entry_outcome_multiple: float) -> float:
    return max(1.0, int(entry_outcome_multiple / ATH_UPDATE_STEP_MULTIPLE) * ATH_UPDATE_STEP_MULTIPLE)


def threshold_list_text(thresholds: list[float], prefix: str = "") -> str:
    if not thresholds:
        return "None"
    return "\n".join(f"{prefix}{threshold:g}x" for threshold in thresholds)


class SurvivorTelegramAlerts:
    def __init__(self, db_path: Path) -> None:
        load_dotenv(ROOT / ".env")
        self.db_path = db_path
        self.bot_token = env_value("TELEGRAM_BOT_TOKEN")
        self.chat_id = env_value("TELEGRAM_CHAT_ID")
        self.shadow_dm_chat_id = (
            env_value("TELEGRAM_SHADOW_DM_CHAT_ID")
            or env_value("TELEGRAM_DM_CHAT_ID")
            or env_value("TELEGRAM_USER_ID")
        )
        self.shadow_enabled = bool_env("TELEGRAM_SHADOW_STRONG_WATCH_ENABLED", True)
        self.enabled = bool_env("TELEGRAM_SURVIVOR_ALERTS_ENABLED", False)
        self.dry_run = bool_env("TELEGRAM_SURVIVOR_DRY_RUN", True)
        self.test_limit = int_env("TELEGRAM_SURVIVOR_TEST_LIMIT", 3)
        self.live_start_at_config = env_value("TELEGRAM_SURVIVOR_LIVE_START_AT", "")
        self.client = httpx.AsyncClient(timeout=20)

    async def close(self) -> None:
        await self.client.aclose()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        self.ensure_shadow_alerts_table(conn)
        return conn

    def ensure_shadow_alerts_table(self, conn: sqlite3.Connection) -> None:
        self.ensure_telegram_entry_outcome_tables(conn)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vlak_shadow_tracking_sessions (
                session_id TEXT PRIMARY KEY,
                session_name TEXT,
                started_at TEXT,
                ended_at TEXT,
                status TEXT,
                notes TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vlak_bot_config (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vlak_shadow_alerts (
                mint TEXT PRIMARY KEY,
                symbol TEXT,
                raw_vlak_detected_at TEXT,
                survivor_1_4x_time TEXT,
                shadow_alert_sent_at TEXT,
                shadow_session_id TEXT,
                shadow_row_source TEXT,
                passed_simple_rule INTEGER DEFAULT 0,
                passed_vlak_score_strong_watch INTEGER DEFAULT 0,
                net_buy_volume_sol_10m REAL,
                sell_pressure_10m REAL,
                buy_pressure_5m REAL,
                ohlcv_close_1m REAL,
                ohlcv_close_position_in_range_10m REAL,
                ohlcv_pre_detection_pullback_1m REAL,
                top_buyer_volume_sol_5m REAL,
                first_100_initial_buy_volume_sol REAL,
                fuel_score INTEGER,
                death_score INTEGER,
                vlak_score INTEGER,
                telegram_channel_alert_sent INTEGER DEFAULT 0,
                dm_shadow_alert_sent INTEGER DEFAULT 0,
                hit_2x INTEGER DEFAULT 0,
                hit_3x INTEGER DEFAULT 0,
                hit_5x INTEGER DEFAULT 0,
                hit_10x INTEGER DEFAULT 0,
                max_multiple_from_snapshot_a REAL,
                outcome_updated_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        existing = {row[1] for row in conn.execute("PRAGMA table_info(vlak_shadow_alerts)").fetchall()}
        required = {
            "symbol": "TEXT",
            "raw_vlak_detected_at": "TEXT",
            "survivor_1_4x_time": "TEXT",
            "shadow_alert_sent_at": "TEXT",
            "shadow_session_id": "TEXT",
            "shadow_row_source": "TEXT",
            "passed_simple_rule": "INTEGER DEFAULT 0",
            "passed_vlak_score_strong_watch": "INTEGER DEFAULT 0",
            "net_buy_volume_sol_10m": "REAL",
            "sell_pressure_10m": "REAL",
            "buy_pressure_5m": "REAL",
            "ohlcv_close_1m": "REAL",
            "ohlcv_close_position_in_range_10m": "REAL",
            "ohlcv_pre_detection_pullback_1m": "REAL",
            "top_buyer_volume_sol_5m": "REAL",
            "first_100_initial_buy_volume_sol": "REAL",
            "fuel_score": "INTEGER",
            "death_score": "INTEGER",
            "vlak_score": "INTEGER",
            "telegram_channel_alert_sent": "INTEGER DEFAULT 0",
            "dm_shadow_alert_sent": "INTEGER DEFAULT 0",
            "hit_2x": "INTEGER DEFAULT 0",
            "hit_3x": "INTEGER DEFAULT 0",
            "hit_5x": "INTEGER DEFAULT 0",
            "hit_10x": "INTEGER DEFAULT 0",
            "max_multiple_from_snapshot_a": "REAL",
            "outcome_updated_at": "TEXT",
            "created_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
        }
        for column, definition in required.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE vlak_shadow_alerts ADD COLUMN {column} {definition}")
        conn.commit()

    def ensure_telegram_entry_outcome_tables(self, conn: sqlite3.Connection) -> None:
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
            """
            CREATE INDEX IF NOT EXISTS idx_telegram_entry_outcome_milestones_mint
            ON telegram_entry_outcome_milestones(mint)
            """
        )
        conn.commit()

    def upsert_telegram_entry_outcome(self, conn: sqlite3.Connection, row: sqlite3.Row, thread: sqlite3.Row, now: str) -> float | None:
        entry_multiple = telegram_entry_outcome_multiple(row["max_multiple"], thread["first_alert_multiple"])
        if entry_multiple is None:
            return None
        first_mc = row["first_call_market_cap"] or row["first_alert_market_cap"]
        try:
            entry_mc = float(first_mc) * float(thread["first_alert_multiple"]) if first_mc and thread["first_alert_multiple"] else None
        except (TypeError, ValueError):
            entry_mc = None
        conn.execute(
            """
            INSERT INTO telegram_entry_outcomes (
                mint, telegram_alerted_at, telegram_entry_multiple, telegram_entry_market_cap,
                latest_snapshot_time, current_mc, ath_market_cap, max_multiple_from_first_spotted,
                max_multiple_from_telegram_entry, hit_20pct_after_telegram, hit_50pct_after_telegram,
                hit_2x_after_telegram, hit_3x_after_telegram, hit_5x_after_telegram,
                hit_10x_after_telegram, outcome_source, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'derived_from_existing_outcomes', ?)
            ON CONFLICT(mint) DO UPDATE SET
                telegram_alerted_at=excluded.telegram_alerted_at,
                telegram_entry_multiple=excluded.telegram_entry_multiple,
                telegram_entry_market_cap=excluded.telegram_entry_market_cap,
                latest_snapshot_time=excluded.latest_snapshot_time,
                current_mc=excluded.current_mc,
                ath_market_cap=MAX(COALESCE(telegram_entry_outcomes.ath_market_cap, 0), COALESCE(excluded.ath_market_cap, 0)),
                max_multiple_from_first_spotted=MAX(COALESCE(telegram_entry_outcomes.max_multiple_from_first_spotted, 0), COALESCE(excluded.max_multiple_from_first_spotted, 0)),
                max_multiple_from_telegram_entry=MAX(COALESCE(telegram_entry_outcomes.max_multiple_from_telegram_entry, 0), COALESCE(excluded.max_multiple_from_telegram_entry, 0)),
                hit_20pct_after_telegram=MAX(COALESCE(telegram_entry_outcomes.hit_20pct_after_telegram, 0), excluded.hit_20pct_after_telegram),
                hit_50pct_after_telegram=MAX(COALESCE(telegram_entry_outcomes.hit_50pct_after_telegram, 0), excluded.hit_50pct_after_telegram),
                hit_2x_after_telegram=MAX(COALESCE(telegram_entry_outcomes.hit_2x_after_telegram, 0), excluded.hit_2x_after_telegram),
                hit_3x_after_telegram=MAX(COALESCE(telegram_entry_outcomes.hit_3x_after_telegram, 0), excluded.hit_3x_after_telegram),
                hit_5x_after_telegram=MAX(COALESCE(telegram_entry_outcomes.hit_5x_after_telegram, 0), excluded.hit_5x_after_telegram),
                hit_10x_after_telegram=MAX(COALESCE(telegram_entry_outcomes.hit_10x_after_telegram, 0), excluded.hit_10x_after_telegram),
                outcome_source=excluded.outcome_source,
                updated_at=excluded.updated_at
            """,
            (
                row["mint"],
                thread["first_alerted_at"],
                thread["first_alert_multiple"],
                entry_mc,
                row["latest_snapshot_time"],
                row["current_mc"],
                row["ath_market_cap"],
                row["max_multiple"],
                entry_multiple,
                int(entry_multiple >= 1.2),
                int(entry_multiple >= 1.5),
                int(entry_multiple >= 2),
                int(entry_multiple >= 3),
                int(entry_multiple >= 5),
                int(entry_multiple >= 10),
                now,
            ),
        )
        return entry_multiple

    def active_shadow_session_id(self, conn: sqlite3.Connection) -> str | None:
        row = conn.execute(
            "SELECT value FROM vlak_bot_config WHERE key = 'active_shadow_session_id'"
        ).fetchone()
        return row["value"] if row and row["value"] else None

    def telegram_ready(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    async def send_shadow_dm(self, text: str, mint: str | None = None) -> int | None:
        if not self.shadow_enabled or not self.enabled or self.dry_run:
            logger.info("Shadow Strong Watch dry/disabled: would DM text=%s", text[:180])
            return None
        if not self.bot_token or not self.shadow_dm_chat_id:
            logger.warning("Shadow Strong Watch DM enabled but TELEGRAM_SHADOW_DM_CHAT_ID/TELEGRAM_DM_CHAT_ID/TELEGRAM_USER_ID missing")
            return None
        payload: dict[str, Any] = {
            "chat_id": self.shadow_dm_chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "reply_markup": shadow_buy_button_markup(mint),
        }
        response = await self.client.post(f"https://api.telegram.org/bot{self.bot_token}/sendMessage", json=payload)
        response.raise_for_status()
        message_id = response.json().get("result", {}).get("message_id")
        return int(message_id) if message_id is not None else None

    async def send_message(self, text: str, reply_to_message_id: int | None = None, parse_mode: str | None = None) -> int | None:
        if not self.enabled or self.dry_run:
            logger.info("Survivor Telegram dry/disabled: would send reply_to=%s text=%s", reply_to_message_id, text[:180])
            return None
        if not self.telegram_ready():
            logger.warning("Survivor Telegram enabled but TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID missing")
            return None
        payload: dict[str, Any] = {
            "chat_id": self.chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_to_message_id is not None:
            payload["reply_to_message_id"] = int(reply_to_message_id)
            payload["allow_sending_without_reply"] = False
        response = await self.client.post(f"https://api.telegram.org/bot{self.bot_token}/sendMessage", json=payload)
        response.raise_for_status()
        message_id = response.json().get("result", {}).get("message_id")
        return int(message_id) if message_id is not None else None

    async def send_photo_message(self, photo_url: str, caption: str, reply_markup: dict[str, Any] | None = None, parse_mode: str | None = None) -> int | None:
        if not self.enabled or self.dry_run:
            logger.info("Survivor Telegram dry/disabled: would send photo=%s caption=%s", bool(photo_url), caption[:180])
            return None
        if not self.telegram_ready():
            logger.warning("Survivor Telegram enabled but TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID missing")
            return None
        payload: dict[str, Any] = {
            "chat_id": self.chat_id,
            "photo": photo_url,
            "caption": caption,
            "reply_markup": reply_markup or buy_button_markup(),
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        response = await self.client.post(f"https://api.telegram.org/bot{self.bot_token}/sendPhoto", json=payload)
        response.raise_for_status()
        message_id = response.json().get("result", {}).get("message_id")
        return int(message_id) if message_id is not None else None

    async def send_root_text_fallback(self, caption: str, reply_markup: dict[str, Any] | None = None, parse_mode: str | None = None) -> int | None:
        if not self.enabled or self.dry_run:
            logger.info("Survivor Telegram dry/disabled: would send root text fallback caption=%s", caption[:180])
            return None
        if not self.telegram_ready():
            logger.warning("Survivor Telegram enabled but TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID missing")
            return None
        payload: dict[str, Any] = {
            "chat_id": self.chat_id,
            "text": caption,
            "disable_web_page_preview": True,
            "reply_markup": reply_markup or buy_button_markup(),
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        response = await self.client.post(f"https://api.telegram.org/bot{self.bot_token}/sendMessage", json=payload)
        response.raise_for_status()
        message_id = response.json().get("result", {}).get("message_id")
        return int(message_id) if message_id is not None else None

    def load_token(self, conn: sqlite3.Connection, mint: str) -> sqlite3.Row | None:
        return conn.execute(
            """
            WITH first_event AS (
                SELECT *
                FROM vlak_alert_events
                WHERE mint = ? AND is_first_alert_per_mint = 1
                ORDER BY alert_time ASC, id ASC
                LIMIT 1
            ),
            metric_best AS (
                SELECT
                    mint,
                    MAX(market_cap) AS max_metric_market_cap,
                    MAX(snapshot_time) AS latest_metric_snapshot_time
                FROM vlak_metric_snapshots
                WHERE mint = ?
            )
            SELECT
                o.mint,
                e.symbol,
                e.name,
                e.alert_time,
                o.first_alert_time,
                t.first_alerted_at AS telegram_alerted_at,
                t.first_alert_multiple AS telegram_entry_multiple,
                COALESCE(o.first_call_market_cap, e.first_call_market_cap) AS first_call_market_cap,
                e.market_cap AS first_alert_market_cap,
                e.liquidity AS first_alert_liquidity,
                e.raw_json AS first_alert_raw_json,
                CASE
                    WHEN mb.max_metric_market_cap IS NOT NULL
                     AND (o.current_mc IS NULL OR mb.max_metric_market_cap > o.current_mc)
                    THEN mb.max_metric_market_cap
                    ELSE o.current_mc
                END AS current_mc,
                MAX(COALESCE(o.ath_market_cap, 0), COALESCE(mb.max_metric_market_cap, 0)) AS ath_market_cap,
                MAX(
                    COALESCE(o.max_multiple, 0),
                    CASE
                        WHEN COALESCE(o.first_call_market_cap, e.first_call_market_cap) > 0
                         AND mb.max_metric_market_cap IS NOT NULL
                        THEN mb.max_metric_market_cap / COALESCE(o.first_call_market_cap, e.first_call_market_cap)
                        ELSE 0
                    END
                ) AS max_multiple,
                CASE
                    WHEN t.first_alert_multiple > 0 THEN
                        MAX(
                            COALESCE(o.max_multiple, 0),
                            CASE
                                WHEN COALESCE(o.first_call_market_cap, e.first_call_market_cap) > 0
                                 AND mb.max_metric_market_cap IS NOT NULL
                                THEN mb.max_metric_market_cap / COALESCE(o.first_call_market_cap, e.first_call_market_cap)
                                ELSE 0
                            END
                        ) / t.first_alert_multiple
                    ELSE NULL
                END AS telegram_entry_outcome_multiple,
                CASE
                    WHEN t.first_alert_multiple > 0 AND COALESCE(o.first_call_market_cap, e.first_call_market_cap) > 0
                    THEN COALESCE(o.first_call_market_cap, e.first_call_market_cap) * t.first_alert_multiple
                    ELSE NULL
                END AS telegram_entry_market_cap,
                COALESCE(mb.latest_metric_snapshot_time, o.latest_snapshot_time) AS latest_snapshot_time
            FROM vlak_token_outcomes o
            LEFT JOIN first_event e ON e.mint = o.mint
            LEFT JOIN metric_best mb ON mb.mint = o.mint
            LEFT JOIN telegram_survivor_threads t ON t.mint = o.mint
            WHERE o.mint = ?
            """,
            (mint, mint, mint),
        ).fetchone()

    def mark_armed(self, conn: sqlite3.Connection, row: sqlite3.Row, now: str) -> bool:
        max_multiple = float(row["max_multiple"] or 0)
        if max_multiple < ARMING_THRESHOLD:
            return False
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO telegram_survivor_armed
            (mint, armed_threshold, armed_multiple, armed_at, source)
            VALUES (?, ?, ?, ?, 'vlak')
            """,
            (row["mint"], ARMING_THRESHOLD, max_multiple, now),
        )
        conn.commit()
        return bool(cur.rowcount)

    def configured_live_start_at(self) -> str | None:
        if not self.live_start_at_config:
            return None
        parsed = parse_time(self.live_start_at_config)
        return parsed.isoformat(timespec="seconds") if parsed else None

    def current_live_start_at(self, conn: sqlite3.Connection) -> str | None:
        configured = self.configured_live_start_at()
        if configured:
            return configured
        row = conn.execute(
            "SELECT survivor_alerts_live_start_at FROM telegram_survivor_live_state WHERE source = 'vlak'"
        ).fetchone()
        return row["survivor_alerts_live_start_at"] if row and row["survivor_alerts_live_start_at"] else None

    def get_or_create_telegram_entry_outcome_live_start_at(self, conn: sqlite3.Connection, now: str) -> str:
        configured = self.configured_live_start_at()
        if configured:
            conn.execute(
                """
                INSERT INTO vlak_bot_config (key, value, updated_at)
                VALUES ('telegram_entry_outcome_live_start_at', ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (configured, now),
            )
            conn.commit()
            return configured
        row = conn.execute(
            "SELECT value FROM vlak_bot_config WHERE key = 'telegram_entry_outcome_live_start_at'"
        ).fetchone()
        if row and row["value"]:
            return row["value"]
        conn.execute(
            """
            INSERT INTO vlak_bot_config (key, value, updated_at)
            VALUES ('telegram_entry_outcome_live_start_at', ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (now, now),
        )
        conn.commit()
        logger.warning("Created Telegram-entry outcome live-start cutoff at %s", now)
        return now

    def get_or_create_live_start_at(self, conn: sqlite3.Connection, now: str) -> str | None:
        configured = self.configured_live_start_at()
        if configured:
            conn.execute(
                """
                INSERT INTO telegram_survivor_live_state
                (source, survivor_alerts_live_start_at, created_at, updated_at)
                VALUES ('vlak', ?, ?, ?)
                ON CONFLICT(source) DO UPDATE SET
                    survivor_alerts_live_start_at = excluded.survivor_alerts_live_start_at,
                    updated_at = excluded.updated_at
                """,
                (configured, now, now),
            )
            conn.commit()
            return configured
        row = conn.execute(
            "SELECT survivor_alerts_live_start_at FROM telegram_survivor_live_state WHERE source = 'vlak'"
        ).fetchone()
        if row and row["survivor_alerts_live_start_at"]:
            return row["survivor_alerts_live_start_at"]
        if self.enabled and not self.dry_run:
            conn.execute(
                """
                INSERT INTO telegram_survivor_live_state
                (source, survivor_alerts_live_start_at, created_at, updated_at)
                VALUES ('vlak', ?, ?, ?)
                ON CONFLICT(source) DO UPDATE SET
                    survivor_alerts_live_start_at = excluded.survivor_alerts_live_start_at,
                    updated_at = excluded.updated_at
                """,
                (now, now, now),
            )
            conn.commit()
            logger.warning("TELEGRAM_SURVIVOR_LIVE_START_AT missing; created live start timestamp at %s", now)
            return now
        return None

    def first_root_crossing_at(self, conn: sqlite3.Connection, row: sqlite3.Row) -> str | None:
        crossing = conn.execute(
            """
            SELECT MIN(snapshot_time)
            FROM vlak_outcome_snapshots
            WHERE mint = ? AND max_multiple >= ?
            """,
            (row["mint"], ROOT_THRESHOLD),
        ).fetchone()[0]
        if crossing:
            return crossing
        if row["max_multiple"] is not None and float(row["max_multiple"] or 0) >= ROOT_THRESHOLD:
            return row["latest_snapshot_time"] or row["first_alert_time"] or row["alert_time"]
        return None

    def is_shadow_excluded(self, conn: sqlite3.Connection, mint: str) -> bool:
        return bool(conn.execute("SELECT 1 FROM telegram_survivor_shadow_exclusions WHERE mint = ?", (mint,)).fetchone())

    def mark_shadow_if_pre_live(self, conn: sqlite3.Connection, row: sqlite3.Row, live_start_at: str, now: str) -> bool:
        crossing_at = self.first_root_crossing_at(conn, row)
        crossing_dt = parse_time(crossing_at)
        live_dt = parse_time(live_start_at)
        if not crossing_dt or not live_dt:
            return True
        if crossing_dt <= live_dt:
            conn.execute(
                """
                INSERT OR IGNORE INTO telegram_survivor_shadow_exclusions
                (mint, reason, first_qualified_at, max_multiple_at_mark, survivor_alerts_live_start_at, marked_at, source)
                VALUES (?, 'pre_live_qualified', ?, ?, ?, ?, 'vlak')
                """,
                (row["mint"], crossing_at, row["max_multiple"], live_start_at, now),
            )
            conn.commit()
            logger.info(
                "Vlak survivor shadow_only mint=%s first_qualified_at=%s live_start_at=%s",
                row["mint"],
                crossing_at,
                live_start_at,
            )
            return True
        return False

    def mark_late_root_if_above_cap(self, conn: sqlite3.Connection, row: sqlite3.Row, live_start_at: str, now: str) -> bool:
        max_multiple = float(row["max_multiple"] or 0)
        if max_multiple <= ROOT_ALERT_MAX_MULTIPLE:
            return False
        crossing_at = self.first_root_crossing_at(conn, row) or row["latest_snapshot_time"] or now
        conn.execute(
            """
            INSERT OR IGNORE INTO telegram_survivor_shadow_exclusions
            (mint, reason, first_qualified_at, max_multiple_at_mark, survivor_alerts_live_start_at, marked_at, source)
            VALUES (?, 'FIRST_ALERT_TOO_LATE_ABOVE_3X', ?, ?, ?, ?, 'vlak')
            """,
            (row["mint"], crossing_at, max_multiple, live_start_at, now),
        )
        conn.commit()
        logger.info(
            "Vlak survivor root suppressed as late entry mint=%s multiple=%s cap=%s",
            row["mint"],
            fmt_multiple(max_multiple),
            fmt_multiple(ROOT_ALERT_MAX_MULTIPLE),
        )
        return True
    def snapshot_a_db_path(self) -> Path:
        return ROOT / "vlak_snapshot_a_research.sqlite"

    def load_snapshot_a_features(self, mint: str) -> dict[str, Any] | None:
        db_path = self.snapshot_a_db_path()
        if not db_path.exists():
            logger.warning("Snapshot A DB missing for shadow strong watch: %s", db_path)
            return None
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT
                    r.mint,
                    r.symbol,
                    r.token_name,
                    r.first_vlak_detected_at,
                    r.first_call_market_cap,
                    r.market_cap_at_detection,
                    r.liquidity_at_detection,
                    tf.enrichment_status,
                    oh.ohlcv_status,
                    tf.net_buy_volume_sol_10m,
                    tf.sell_pressure_10m,
                    tf.buy_pressure_5m,
                    tf.top_buyer_volume_sol_5m,
                    oh.ohlcv_close_1m,
                    oh.ohlcv_close_position_in_range_10m,
                    oh.ohlcv_pre_detection_pullback_1m,
                    fb.first_100_initial_buy_volume_sol,
                    o.ath_market_cap,
                    o.max_multiple_from_snapshot_a,
                    o.outcome_bucket,
                    o.hit_1_4x,
                    o.hit_2x,
                    o.hit_3x,
                    o.hit_5x,
                    o.hit_10x
                FROM raw_vlak_detections r
                LEFT JOIN snapshot_a_outcomes o ON o.mint = r.mint
                LEFT JOIN snapshot_a_trade_features tf ON tf.mint = r.mint
                LEFT JOIN snapshot_a_ohlcv_features oh ON oh.mint = r.mint
                LEFT JOIN snapshot_a_first_buyer_features fb ON fb.mint = r.mint
                WHERE r.mint = ?
                  AND tf.enrichment_status = 'done'
                  AND oh.ohlcv_status = 'done'
                LIMIT 1
                """,
                (mint,),
            ).fetchone()
            conn.close()
        except Exception as exc:
            logger.warning("Snapshot A feature read failed mint=%s error=%s", mint, exc)
            return None
        return dict(row) if row else None

    def get_or_create_snapshot_shadow_live_start_at(self, conn: sqlite3.Connection, now: str) -> str:
        row = conn.execute("SELECT value FROM vlak_bot_config WHERE key = 'snapshot_a_shadow_live_start_at'").fetchone()
        if row and row["value"]:
            return row["value"]
        conn.execute(
            """
            INSERT INTO vlak_bot_config(key, value, updated_at)
            VALUES ('snapshot_a_shadow_live_start_at', ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (now, now),
        )
        conn.commit()
        return now

    def load_shadow_candidate_row(self, conn: sqlite3.Connection, mint: str, features: dict[str, Any]) -> sqlite3.Row | None:
        return conn.execute(
            """
            WITH first_event AS (
                SELECT *
                FROM vlak_alert_events
                WHERE mint = ? AND is_first_alert_per_mint = 1
                ORDER BY alert_time ASC, id ASC
                LIMIT 1
            )
            SELECT
                e.mint,
                COALESCE(e.symbol, ?) AS symbol,
                COALESCE(e.name, ?) AS name,
                COALESCE(e.alert_time, ?) AS alert_time,
                COALESCE(o.first_alert_time, ?) AS first_alert_time,
                COALESCE(o.first_call_market_cap, e.first_call_market_cap, ?) AS first_call_market_cap,
                COALESCE(e.market_cap, ?) AS first_alert_market_cap,
                COALESCE(e.liquidity, ?) AS first_alert_liquidity,
                e.raw_json AS first_alert_raw_json,
                COALESCE(o.current_mc, e.market_cap, ?) AS current_mc,
                COALESCE(o.ath_market_cap, ?) AS ath_market_cap,
                COALESCE(o.max_multiple, ?, 1.0) AS max_multiple,
                COALESCE(o.latest_snapshot_time, ?) AS latest_snapshot_time
            FROM first_event e
            LEFT JOIN vlak_token_outcomes o ON o.mint = e.mint
            """,
            (
                mint,
                features.get("symbol"),
                features.get("token_name") or features.get("symbol"),
                features.get("first_vlak_detected_at"),
                features.get("first_vlak_detected_at"),
                self.safe_float(features.get("first_call_market_cap")) or self.safe_float(features.get("market_cap_at_detection")),
                self.safe_float(features.get("market_cap_at_detection")) or self.safe_float(features.get("first_call_market_cap")),
                self.safe_float(features.get("liquidity_at_detection")),
                self.safe_float(features.get("market_cap_at_detection")) or self.safe_float(features.get("first_call_market_cap")),
                self.safe_float(features.get("ath_market_cap")),
                self.safe_float(features.get("max_multiple_from_snapshot_a")),
                features.get("first_vlak_detected_at"),
            ),
        ).fetchone()

    def snapshot_a_shadow_candidates(self, limit: int = 20) -> list[str]:
        db_path = self.snapshot_a_db_path()
        if not db_path.exists():
            return []
        now = utc_now_iso()
        with self.connect() as conn:
            live_start_at = self.get_or_create_snapshot_shadow_live_start_at(conn, now)
            existing = {
                row["mint"]
                for row in conn.execute("SELECT mint FROM vlak_shadow_alerts WHERE COALESCE(dm_shadow_alert_sent, 0) = 1").fetchall()
            }
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT r.mint
                FROM raw_vlak_detections r
                JOIN snapshot_a_trade_features tf ON tf.mint = r.mint AND tf.enrichment_status = 'done'
                JOIN snapshot_a_ohlcv_features oh ON oh.mint = r.mint AND oh.ohlcv_status = 'done'
                JOIN snapshot_a_first_buyer_features fb ON fb.mint = r.mint
                WHERE datetime(r.first_vlak_detected_at) >= datetime(?)
                ORDER BY datetime(r.first_vlak_detected_at) ASC
                LIMIT ?
                """,
                (live_start_at, limit * 5),
            ).fetchall()
            conn.close()
        except Exception as exc:
            logger.warning("Snapshot A shadow candidate scan failed error=%s", exc)
            return []
        return [row["mint"] for row in rows if row["mint"] not in existing][:limit]

    async def process_snapshot_a_shadow_candidates(self, limit: int = 20) -> int:
        # Shadow Strong Watch private DMs are disabled. Public survivor alerts are unchanged.
        return 0

    @staticmethod
    def safe_float(value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def strong_watch_scores(self, features: dict[str, Any]) -> dict[str, Any]:
        def ge(key: str, threshold: float) -> bool:
            value = self.safe_float(features.get(key))
            return value is not None and value >= threshold

        def le(key: str, threshold: float) -> bool:
            value = self.safe_float(features.get(key))
            return value is not None and value <= threshold

        death_score = 0
        death_reasons = []
        if ge("ohlcv_pre_detection_pullback_1m", 0.444):
            death_score += 2
            death_reasons.append("pullback_1m_high")
        if le("ohlcv_close_position_in_range_10m", 0.497):
            death_score += 2
            death_reasons.append("weak_10m_close")
        if ge("sell_pressure_10m", 0.50):
            death_score += 2
            death_reasons.append("sell_pressure_10m_high")
        if le("ohlcv_close_1m", 13300):
            death_score += 1
            death_reasons.append("low_close_1m")

        fuel_score = 0
        fuel_reasons = []
        if ge("net_buy_volume_sol_10m", 96.6):
            fuel_score += 2
            fuel_reasons.append("net_buy_volume_10m_high")
        if ge("buy_pressure_5m", 0.695):
            fuel_score += 1
            fuel_reasons.append("buy_pressure_5m_high")
        if le("sell_pressure_10m", 0.315):
            fuel_score += 1
            fuel_reasons.append("sell_pressure_10m_low")
        if ge("ohlcv_close_1m", 53400):
            fuel_score += 1
            fuel_reasons.append("close_1m_high")
        if ge("ohlcv_close_position_in_range_10m", 0.70):
            fuel_score += 1
            fuel_reasons.append("strong_10m_close")
        if ge("top_buyer_volume_sol_5m", 27.3):
            fuel_score += 1
            fuel_reasons.append("top_buyer_volume_5m_high")
        if ge("first_100_initial_buy_volume_sol", 154.9):
            fuel_score += 1
            fuel_reasons.append("first_100_buy_volume_high")

        vlak_score = fuel_score - death_score
        if death_score >= 4 and fuel_score <= 2:
            decision = "AVOID"
        elif vlak_score >= 5:
            decision = "STRONG_WATCH"
        elif vlak_score >= 2:
            decision = "WATCH"
        else:
            decision = "AVOID"

        passed_simple = ge("net_buy_volume_sol_10m", 96.6) and le("sell_pressure_10m", 0.315)
        passed_vlak = decision == "STRONG_WATCH"
        return {
            "death_score": death_score,
            "fuel_score": fuel_score,
            "vlak_score": vlak_score,
            "decision": decision,
            "passed_simple_rule": int(passed_simple),
            "passed_vlak_score_strong_watch": int(passed_vlak),
            "passes_shadow": bool(passed_simple or passed_vlak),
            "fuel_reasons": fuel_reasons,
            "death_reasons": death_reasons,
        }

    def format_shadow_dm_message(self, row: sqlite3.Row, features: dict[str, Any], scores: dict[str, Any]) -> str:
        symbol = row["symbol"] or "UNKNOWN"
        mint = row["mint"]
        row_keys = set(row.keys())
        raw = raw_json_dict(row)

        def raw_first(*keys: str) -> Any:
            for key in keys:
                value = raw.get(key) if isinstance(raw, dict) else None
                if value not in (None, ""):
                    return value
            return None

        snapshot_entry_mc = features.get("market_cap_at_detection") or features.get("first_call_market_cap")
        snapshot_entry_ts = features.get("first_vlak_detected_at")
        market_cap = snapshot_entry_mc or (
            row["first_alert_market_cap"] if "first_alert_market_cap" in row_keys else None
        ) or (
            row["current_mc"] if "current_mc" in row_keys else None
        ) or raw_first("marketCap", "market_cap", "mcap", "fdv")
        liquidity = features.get("liquidity_at_detection") or (
            row["first_alert_liquidity"] if "first_alert_liquidity" in row_keys else None
        ) or raw_first("liquidity", "liquidityUsd", "liquidity_usd")

        fuel_reasons = ", ".join(scores["fuel_reasons"]) or "none"
        death_reasons = ", ".join(scores["death_reasons"]) or "none"
        token_url = dexscreener_link(mint)
        return "\n".join(
            [
                "<b>🟢🟢🟢 VLAK SHADOW STRONG WATCH 🟢🟢🟢</b>",
                "<b>SHADOW MODE — NOT PUBLIC CHANNEL GATE YET</b>",
                "",
                f"Token: <a href='{html_escape(token_url)}'>{html_escape(symbol)}</a>",
                f"Mint: <code>{html_escape(mint)}</code>",
                f"Market Cap: <b>{fmt_shadow_money(market_cap)}</b>",
                f"Liquidity: <b>{fmt_shadow_money(liquidity)}</b>",
                "",
                "Snapshot A Entry:",
                f"Entry Market Cap: <b>{fmt_shadow_money(snapshot_entry_mc)}</b>",
                f"Entry Timestamp: <code>{html_escape(str(snapshot_entry_ts or 'n/a'))}</code>",
                "",
                f"Net Buy 10m: <b>{fmt_shadow_number(features.get('net_buy_volume_sol_10m'))}</b>",
                f"Sell Pressure 10m: <b>{fmt_shadow_number(features.get('sell_pressure_10m'))}</b>",
                f"Buy Pressure 5m: <b>{fmt_shadow_number(features.get('buy_pressure_5m'))}</b>",
                "",
                f"Fuel Score: <b>{scores['fuel_score']}</b>",
                f"Death Score: <b>{scores['death_score']}</b>",
                f"Vlak Score: <b>{scores['vlak_score']}</b>",
                "",
                f"Simple Rule: <b>{'YES' if scores['passed_simple_rule'] else 'NO'}</b>",
                f"Vlak Score Strong Watch: <b>{'YES' if scores['passed_vlak_score_strong_watch'] else 'NO'}</b>",
                "",
                "Fuel reasons:",
                f"<code>{html_escape(fuel_reasons)}</code>",
                "",
                "Death reasons:",
                f"<code>{html_escape(death_reasons)}</code>",
                "",
                "Historical research note:",
                "Early Strong Watch is now measured from <b>Snapshot A</b> to test remaining opportunity before the old 1.4x delay.",
            ]
        )

    def upsert_shadow_alert(self, conn: sqlite3.Connection, row: sqlite3.Row, features: dict[str, Any], scores: dict[str, Any], now: str) -> bool:
        max_multiple = float(row["max_multiple"] or 0)
        thread = conn.execute("SELECT root_message_id FROM telegram_survivor_threads WHERE mint = ?", (row["mint"],)).fetchone()
        survivor_time = self.first_root_crossing_at(conn, row)
        active_session_id = self.active_shadow_session_id(conn)
        conn.execute(
            """
            INSERT INTO vlak_shadow_alerts (
                mint, symbol, raw_vlak_detected_at, survivor_1_4x_time, shadow_alert_sent_at,
                shadow_session_id, shadow_row_source,
                passed_simple_rule, passed_vlak_score_strong_watch,
                net_buy_volume_sol_10m, sell_pressure_10m, buy_pressure_5m,
                ohlcv_close_1m, ohlcv_close_position_in_range_10m, ohlcv_pre_detection_pullback_1m,
                top_buyer_volume_sol_5m, first_100_initial_buy_volume_sol,
                fuel_score, death_score, vlak_score,
                telegram_channel_alert_sent, dm_shadow_alert_sent,
                hit_2x, hit_3x, hit_5x, hit_10x, max_multiple_from_snapshot_a,
                outcome_updated_at, updated_at
            ) VALUES (?, ?, ?, ?, NULL, ?, 'fresh_live', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(mint) DO UPDATE SET
                symbol = excluded.symbol,
                raw_vlak_detected_at = COALESCE(vlak_shadow_alerts.raw_vlak_detected_at, excluded.raw_vlak_detected_at),
                survivor_1_4x_time = COALESCE(vlak_shadow_alerts.survivor_1_4x_time, excluded.survivor_1_4x_time),
                shadow_session_id = COALESCE(vlak_shadow_alerts.shadow_session_id, excluded.shadow_session_id),
                shadow_row_source = COALESCE(vlak_shadow_alerts.shadow_row_source, excluded.shadow_row_source),
                passed_simple_rule = excluded.passed_simple_rule,
                passed_vlak_score_strong_watch = excluded.passed_vlak_score_strong_watch,
                net_buy_volume_sol_10m = excluded.net_buy_volume_sol_10m,
                sell_pressure_10m = excluded.sell_pressure_10m,
                buy_pressure_5m = excluded.buy_pressure_5m,
                ohlcv_close_1m = excluded.ohlcv_close_1m,
                ohlcv_close_position_in_range_10m = excluded.ohlcv_close_position_in_range_10m,
                ohlcv_pre_detection_pullback_1m = excluded.ohlcv_pre_detection_pullback_1m,
                top_buyer_volume_sol_5m = excluded.top_buyer_volume_sol_5m,
                first_100_initial_buy_volume_sol = excluded.first_100_initial_buy_volume_sol,
                fuel_score = excluded.fuel_score,
                death_score = excluded.death_score,
                vlak_score = excluded.vlak_score,
                telegram_channel_alert_sent = excluded.telegram_channel_alert_sent,
                hit_2x = excluded.hit_2x,
                hit_3x = excluded.hit_3x,
                hit_5x = excluded.hit_5x,
                hit_10x = excluded.hit_10x,
                max_multiple_from_snapshot_a = MAX(COALESCE(vlak_shadow_alerts.max_multiple_from_snapshot_a, 0), COALESCE(excluded.max_multiple_from_snapshot_a, 0)),
                outcome_updated_at = excluded.outcome_updated_at,
                updated_at = excluded.updated_at
            """,
            (
                row["mint"], row["symbol"], features.get("first_vlak_detected_at"), survivor_time,
                active_session_id,
                scores["passed_simple_rule"], scores["passed_vlak_score_strong_watch"],
                self.safe_float(features.get("net_buy_volume_sol_10m")),
                self.safe_float(features.get("sell_pressure_10m")),
                self.safe_float(features.get("buy_pressure_5m")),
                self.safe_float(features.get("ohlcv_close_1m")),
                self.safe_float(features.get("ohlcv_close_position_in_range_10m")),
                self.safe_float(features.get("ohlcv_pre_detection_pullback_1m")),
                self.safe_float(features.get("top_buyer_volume_sol_5m")),
                self.safe_float(features.get("first_100_initial_buy_volume_sol")),
                scores["fuel_score"], scores["death_score"], scores["vlak_score"],
                1 if thread and thread["root_message_id"] else 0,
                1 if max_multiple >= 2 else 0,
                1 if max_multiple >= 3 else 0,
                1 if max_multiple >= 5 else 0,
                1 if max_multiple >= 10 else 0,
                max_multiple,
                now,
                now,
            ),
        )
        conn.commit()
        existing_sent = conn.execute(
            "SELECT dm_shadow_alert_sent FROM vlak_shadow_alerts WHERE mint = ?",
            (row["mint"],),
        ).fetchone()
        return bool(existing_sent and not int(existing_sent["dm_shadow_alert_sent"] or 0))

    def update_shadow_outcome(self, conn: sqlite3.Connection, row: sqlite3.Row, now: str) -> None:
        max_multiple = float(row["max_multiple"] or 0)
        thread = conn.execute("SELECT root_message_id FROM telegram_survivor_threads WHERE mint = ?", (row["mint"],)).fetchone()
        conn.execute(
            """
            UPDATE vlak_shadow_alerts
            SET telegram_channel_alert_sent = ?,
                hit_2x = ?, hit_3x = ?, hit_5x = ?, hit_10x = ?,
                max_multiple_from_snapshot_a = MAX(COALESCE(max_multiple_from_snapshot_a, 0), ?),
                outcome_updated_at = ?, updated_at = ?
            WHERE mint = ?
            """,
            (
                1 if thread and thread["root_message_id"] else 0,
                1 if max_multiple >= 2 else 0,
                1 if max_multiple >= 3 else 0,
                1 if max_multiple >= 5 else 0,
                1 if max_multiple >= 10 else 0,
                max_multiple,
                now,
                now,
                row["mint"],
            ),
        )
        conn.commit()

    async def maybe_send_shadow_strong_watch_dm(self, mint: str, *, require_survivor: bool = False) -> None:
        now = utc_now_iso()
        with self.connect() as conn:
            features = self.load_snapshot_a_features(mint)
            if not features:
                return
            scores = self.strong_watch_scores(features)
            if not scores["passes_shadow"]:
                return
            row = self.load_token(conn, mint)
            if require_survivor and (row is None or row["max_multiple"] is None or float(row["max_multiple"] or 0) < ROOT_THRESHOLD):
                return
            if row is None:
                row = self.load_shadow_candidate_row(conn, mint, features)
            if row is None:
                return
            should_send = self.upsert_shadow_alert(conn, row, features, scores, now)
            self.update_shadow_outcome(conn, row, now)
            if not should_send:
                return
            text = self.format_shadow_dm_message(row, features, scores)
        try:
            message_id = await self.send_shadow_dm(text, mint=mint)
        except Exception as exc:
            logger.error("Shadow Strong Watch DM failed mint=%s error=%s", mint, exc)
            return
        if message_id is None:
            return
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE vlak_shadow_alerts
                SET dm_shadow_alert_sent = 1,
                    shadow_alert_sent_at = COALESCE(shadow_alert_sent_at, ?),
                    updated_at = ?
                WHERE mint = ?
                """,
                (now, now, mint),
            )
            conn.commit()
            logger.info("Shadow Strong Watch DM sent mint=%s message_id=%s", mint, message_id)

    def format_root_message(self, row: sqlite3.Row, reached: list[float], waiting: list[float]) -> str:
        symbol = row["symbol"] or "UNKNOWN"
        name = row["name"] or symbol
        mint = row["mint"]
        raw = raw_json_dict(row)
        holders = nested_get(raw, "holders") or {}
        audit = nested_get(raw, "audit") or {}
        trackers = nested_get(raw, "trackers") or {}
        social = nested_get(raw, "social") or {}
        first_mc = row["first_call_market_cap"] or row["first_alert_market_cap"]
        current_mc = row["current_mc"]
        total_buy = trackers.get("totalBuy") if isinstance(trackers, dict) else None
        buy_count = trackers.get("countBuy") if isinstance(trackers, dict) else None
        sniper_value = holders.get("sniperHoldPercent") if isinstance(holders, dict) else None
        bundle_value = holders.get("bundleHoldPercent") if isinstance(holders, dict) else None
        dev_hold = holders.get("devHoldPercent") if isinstance(holders, dict) else None
        holder_count = holders.get("total") if isinstance(holders, dict) else None
        top10_percent = holders.get("top10Percent") if isinstance(holders, dict) else None
        top10 = holders.get("top10") if isinstance(holders, dict) else []
        dex_paid = audit.get("dexPaid") if isinstance(audit, dict) else None
        age = elapsed_text(raw.get("createdAt"), row["latest_snapshot_time"] or utc_now_iso())

        def raw_number(value: Any, decimals: int = 0) -> str:
            try:
                return f"{float(value):.{decimals}f}"
            except (TypeError, ValueError):
                return "n/a"

        social_links: list[str] = []
        if isinstance(social, dict):
            if social.get("twitter"):
                social_links.append(f"[X]({mdv2_url(str(social['twitter']))})")
            if social.get("telegram"):
                social_links.append(f"[Telegram]({mdv2_url(str(social['telegram']))})")
            if social.get("website"):
                social_links.append(f"[Website]({mdv2_url(str(social['website']))})")
        social_text = " \\| ".join(social_links) if social_links else mdv2_escape("n/a")

        holder_links: list[str] = []
        if isinstance(top10, list):
            for item in top10[:10]:
                if not isinstance(item, dict) or not item.get("wallet"):
                    continue
                percent = raw_number(item.get("percent"), 1)
                wallet_url = f"https://gmgn.ai/sol/address/sToNrJHb_{item['wallet']}"
                holder_links.append(f"[{mdv2_escape(percent)}]({mdv2_url(wallet_url)})")
        holders_text = " \\| ".join(holder_links) if holder_links else mdv2_escape("n/a")

        label = raw.get("label") or "n/a"
        return "\n".join(
            [
                f"{mdv2_bold('🚨 NEW ALERT:')} {mdv2_bold(raw_number(total_buy))} SOL in {mdv2_bold(raw_number(buy_count))} buys ⚠️",
                "",
                f"{mdv2_bold('🌖 CA:')} `{mdv2_escape(mint)}`",
                "",
                f"┌ {mdv2_bold(name)} \\| {mdv2_bold('#' + symbol)}",
                f"├ Label: {mdv2_bold(label)}",
                f"├ Market Cap: {mdv2_bold(fmt_money(current_mc))}",
                f"├ Liq: {mdv2_bold(fmt_money(raw.get('liquidity') or row['first_alert_liquidity']))}",
                f"├ Vol: {mdv2_bold(fmt_money(raw.get('vol1h')))} \\| Total Fees: {mdv2_bold(raw_number(raw.get('totalFee'), 2) + ' SOL')}",
                f"├ Age: {mdv2_bold(age)}",
                f"└ Social: {social_text}",
                "",
                f"┌ Holder: {mdv2_bold(raw_number(holder_count))} \\| Top 10: {mdv2_bold(fmt_pct(top10_percent))}",
                f"├ DEX Paid: {mdv2_bold(yes_no_icon(dex_paid))}",
                f"├ Bundle: {mdv2_bold(fmt_pct(bundle_value))}",
                f"├ Snipers: {mdv2_bold(fmt_pct(sniper_value))}",
                f"├ Dev: {mdv2_bold(dev_sold_icon_text(dev_hold))}",
                f"└ {holders_text}",
            ]
        )

    def previous_milestone_time(self, conn: sqlite3.Connection, mint: str, threshold: float) -> str | None:
        row = conn.execute(
            """
            SELECT sent_at
            FROM telegram_entry_outcome_milestones
            WHERE mint = ? AND threshold < ?
            ORDER BY threshold DESC
            LIMIT 1
            """,
            (mint, threshold),
        ).fetchone()
        if row:
            return row["sent_at"]
        thread = conn.execute("SELECT first_alerted_at FROM telegram_survivor_threads WHERE mint = ?", (mint,)).fetchone()
        return thread["first_alerted_at"] if thread else None

    def format_milestone_message(self, row: sqlite3.Row, threshold: float, previous_sent_at: str | None) -> str:
        symbol = row["symbol"] or "UNKNOWN"
        entry_mc = row["telegram_entry_market_cap"]
        target_mc = row["ath_market_cap"] or row["current_mc"]
        telegram_alerted_at = row["telegram_alerted_at"]
        milestone_observed_at = row["latest_snapshot_time"] or utc_now_iso()
        entry_outcome = row["telegram_entry_outcome_multiple"]
        return "\n".join(
            [
                f"\U0001F525\U0001F525\U0001F525 {fmt_multiple(entry_outcome)} from Telegram entry",
                "",
                f"#{symbol}  {fmt_money(entry_mc)} \u2197\ufe0f {fmt_money(target_mc)} within {elapsed_text(telegram_alerted_at, milestone_observed_at)} from Telegram alert",
                "",
                "credit: Aladdin",
            ]
        )

    async def process_mint(self, mint: str) -> None:
        now = utc_now_iso()
        with self.connect() as conn:
            row = self.load_token(conn, mint)
            if row is None or row["max_multiple"] is None:
                return
            max_multiple = float(row["max_multiple"] or 0)
            if max_multiple >= ARMING_THRESHOLD:
                armed_new = self.mark_armed(conn, row, now)
                if armed_new:
                    logger.info("Vlak survivor armed mint=%s multiple=%s", mint, fmt_multiple(max_multiple))
            if not self.enabled:
                return
            if max_multiple < ROOT_THRESHOLD:
                return
            live_start_at = self.get_or_create_live_start_at(conn, now)
            if not live_start_at:
                logger.info("Survivor Telegram live start missing; root suppressed mint=%s", mint)
                return
            if self.is_shadow_excluded(conn, mint) or self.mark_shadow_if_pre_live(conn, row, live_start_at, now):
                return
            thread = conn.execute("SELECT * FROM telegram_survivor_threads WHERE mint = ?", (mint,)).fetchone()
            if thread is None and self.mark_late_root_if_above_cap(conn, row, live_start_at, now):
                return

        if thread is None:
            await self.send_root_alert(mint)
            return

        if thread["root_message_id"] is None:
            logger.info("Survivor root already claimed but no root_message_id yet mint=%s", mint)
            return

        with self.connect() as conn:
            row = self.load_token(conn, mint)
            if row is None or row["max_multiple"] is None:
                return
            max_multiple = float(row["max_multiple"] or 0)
            root_dt = parse_time(thread["first_alerted_at"])
            cutoff_dt = parse_time(MILESTONE_ROOT_ALERT_CUTOFF_AT)
            if not root_dt or not cutoff_dt or root_dt < cutoff_dt:
                logger.info(
                    "Historical survivor milestone suppressed by cutoff mint=%s root_alert=%s cutoff=%s",
                    mint,
                    thread["first_alerted_at"],
                    MILESTONE_ROOT_ALERT_CUTOFF_AT,
                )
                return
            entry_live_start_at = self.get_or_create_telegram_entry_outcome_live_start_at(conn, now)
            entry_live_dt = parse_time(entry_live_start_at)
            if not entry_live_dt or root_dt < entry_live_dt:
                logger.info(
                    "Telegram-entry outcome milestone suppressed before entry-outcome live start mint=%s root_alert=%s cutoff=%s",
                    mint,
                    thread["first_alerted_at"],
                    entry_live_start_at,
                )
                return
            entry_outcome_multiple = self.upsert_telegram_entry_outcome(conn, row, thread, now)
            if entry_outcome_multiple is None:
                return
            conn.commit()
            last_sent_row = conn.execute(
                """
                SELECT MAX(multiple_at_send) AS last_sent_multiple
                FROM telegram_entry_outcome_milestones
                WHERE mint = ? AND multiple_at_send IS NOT NULL
                """,
                (mint,),
            ).fetchone()
            last_sent_multiple = float(last_sent_row["last_sent_multiple"] or 1.0)
            existing = {
                float(r["threshold"])
                for r in conn.execute(
                    "SELECT threshold FROM telegram_entry_outcome_milestones WHERE mint = ?",
                    (mint,),
                ).fetchall()
            }
            missing_fixed = [t for t in REPLY_THRESHOLDS if entry_outcome_multiple >= t and float(t) not in existing]
            should_send_update = entry_outcome_multiple >= last_sent_multiple + ATH_UPDATE_STEP_MULTIPLE
            update_marker = telegram_entry_update_marker(entry_outcome_multiple)
            marker_exists = float(update_marker) in existing

        if missing_fixed or (should_send_update and not marker_exists):
            await self.send_milestone_reply(mint, update_marker, missing_fixed + ([update_marker] if should_send_update and not marker_exists else []))

    async def send_root_alert(self, mint: str) -> None:
        now = utc_now_iso()
        with self.connect() as conn:
            row = self.load_token(conn, mint)
            if row is None or row["max_multiple"] is None:
                return
            max_multiple = float(row["max_multiple"] or 0)
            if max_multiple < ROOT_THRESHOLD:
                return
            live_start_at = self.get_or_create_live_start_at(conn, now)
            if not live_start_at:
                logger.info("Survivor Telegram live start missing; root suppressed mint=%s", mint)
                return
            if self.is_shadow_excluded(conn, mint) or self.mark_shadow_if_pre_live(conn, row, live_start_at, now):
                return
            if self.mark_late_root_if_above_cap(conn, row, live_start_at, now):
                return
            reached = thresholds_reached(max_multiple)
            waiting = thresholds_waiting(max_multiple)
            if self.dry_run:
                logger.info(
                    "DRY RUN survivor root eligible mint=%s multiple=%s reached=%s",
                    mint,
                    fmt_multiple(max_multiple),
                    ",".join(f"{threshold:g}x" for threshold in reached),
                )
                return
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO telegram_survivor_threads
                (mint, chat_id, root_message_id, first_alert_threshold, first_alert_multiple, first_alerted_at, source)
                VALUES (?, ?, NULL, ?, ?, ?, 'vlak')
                """,
                (mint, self.chat_id, ROOT_THRESHOLD, max_multiple, now),
            )
            conn.commit()
            if not cur.rowcount:
                return
            text = self.format_root_message(row, reached, waiting)
            image_url = token_image_url(row)
        try:
            if image_url:
                try:
                    message_id = await self.send_photo_message(image_url, text, reply_markup=buy_button_markup(mint), parse_mode="MarkdownV2")
                except Exception as photo_exc:
                    logger.warning("Survivor root photo send failed mint=%s error=%s; falling back to text", mint, photo_exc)
                    message_id = await self.send_root_text_fallback(text, reply_markup=buy_button_markup(mint), parse_mode="MarkdownV2")
            else:
                message_id = await self.send_root_text_fallback(text, reply_markup=buy_button_markup(mint), parse_mode="MarkdownV2")
        except Exception as exc:
            logger.error("Survivor root send failed mint=%s error=%s", mint, exc)
            return
        if message_id is None:
            logger.warning("Survivor root send returned no message_id mint=%s", mint)
            return
        with self.connect() as conn:
            conn.execute("UPDATE telegram_survivor_threads SET root_message_id = ? WHERE mint = ?", (message_id, mint))
            for threshold in reached:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO telegram_survivor_milestones
                    (mint, threshold, multiple_at_send, telegram_message_id, sent_at, source)
                    VALUES (?, ?, ?, ?, ?, 'vlak')
                    """,
                    (mint, threshold, max_multiple, message_id, now),
                )
            conn.commit()
            logger.info(
                "Survivor root sent mint=%s message_id=%s included_milestones=%s",
                mint,
                message_id,
                ",".join(f"{threshold:g}x" for threshold in reached),
            )
        try:
            from survivor_stage_ml_shadow import score_survivor_alert

            score_survivor_alert(mint)
        except ModuleNotFoundError as exc:
            if exc.name != "survivor_stage_ml_shadow":
                logger.warning("Survivor CatBoost shadow scoring failed mint=%s error=%s", mint, exc)
            else:
                logger.info("Survivor CatBoost shadow scoring skipped mint=%s reason=module_not_deployed", mint)
        except Exception as exc:
            logger.warning("Survivor CatBoost shadow scoring failed mint=%s error=%s", mint, exc)

    async def send_milestone_reply(self, mint: str, threshold: float, thresholds_to_mark: list[float] | None = None) -> None:
        now = utc_now_iso()
        thresholds_to_mark = sorted(set(thresholds_to_mark or [threshold]))
        threshold = max(thresholds_to_mark)
        first_new_threshold = min(thresholds_to_mark)
        with self.connect() as conn:
            row = self.load_token(conn, mint)
            thread = conn.execute("SELECT * FROM telegram_survivor_threads WHERE mint = ?", (mint,)).fetchone()
            if row is None or thread is None or thread["root_message_id"] is None:
                return
            live_start_at = self.current_live_start_at(conn)
            if not live_start_at:
                return
            root_dt = parse_time(thread["first_alerted_at"])
            cutoff_dt = parse_time(MILESTONE_ROOT_ALERT_CUTOFF_AT)
            if not root_dt or not cutoff_dt or root_dt < cutoff_dt:
                logger.info(
                    "Historical survivor milestone send suppressed by cutoff mint=%s root_alert=%s cutoff=%s",
                    mint,
                    thread["first_alerted_at"],
                    MILESTONE_ROOT_ALERT_CUTOFF_AT,
                )
                return
            live_dt = parse_time(live_start_at)
            if not root_dt or not live_dt or root_dt < live_dt:
                return
            if self.is_shadow_excluded(conn, mint):
                return
            max_multiple = float(row["max_multiple"] or 0)
            entry_outcome_multiple = self.upsert_telegram_entry_outcome(conn, row, thread, now)
            if entry_outcome_multiple is None:
                return
            conn.commit()
            last_sent_row = conn.execute(
                """
                SELECT MAX(multiple_at_send) AS last_sent_multiple
                FROM telegram_entry_outcome_milestones
                WHERE mint = ? AND multiple_at_send IS NOT NULL
                """,
                (mint,),
            ).fetchone()
            last_sent_multiple = float(last_sent_row["last_sent_multiple"] or 1.0)
            update_marker = telegram_entry_update_marker(entry_outcome_multiple)
            existing = {
                float(r["threshold"])
                for r in conn.execute(
                    "SELECT threshold FROM telegram_entry_outcome_milestones WHERE mint = ?",
                    (mint,),
                ).fetchall()
            }
            requested = list(thresholds_to_mark or [])
            requested.extend(t for t in REPLY_THRESHOLDS if entry_outcome_multiple >= t)
            if entry_outcome_multiple >= last_sent_multiple + ATH_UPDATE_STEP_MULTIPLE:
                requested.append(update_marker)
            thresholds_to_mark = sorted({float(t) for t in requested if entry_outcome_multiple >= float(t) and float(t) not in existing})
            if not thresholds_to_mark:
                return
            threshold = max(thresholds_to_mark)
            first_new_threshold = min(thresholds_to_mark)
            previous_sent_at = self.previous_milestone_time(conn, mint, first_new_threshold)
            if self.dry_run:
                logger.info(
                    "DRY RUN survivor milestone eligible mint=%s thresholds=%s multiple=%s",
                    mint,
                    ",".join(f"{t:g}x" for t in thresholds_to_mark),
                    fmt_multiple(max_multiple),
                )
                return
            inserted = []
            for mark_threshold in thresholds_to_mark:
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO telegram_entry_outcome_milestones
                    (mint, threshold, multiple_at_send, overall_multiple_at_send, telegram_message_id, sent_at, source)
                    VALUES (?, ?, ?, ?, NULL, ?, 'telegram_entry')
                    """,
                    (mint, mark_threshold, entry_outcome_multiple, max_multiple, now),
                )
                if cur.rowcount:
                    inserted.append(mark_threshold)
            conn.commit()
            if not inserted:
                return
            text = self.format_milestone_message(row, threshold, previous_sent_at)
            root_message_id = int(thread["root_message_id"])
        try:
            message_id = await self.send_message(text, reply_to_message_id=root_message_id)
        except Exception as exc:
            with self.connect() as conn:
                for mark_threshold in inserted:
                    conn.execute(
                        "DELETE FROM telegram_entry_outcome_milestones WHERE mint = ? AND threshold = ? AND telegram_message_id IS NULL",
                        (mint, mark_threshold),
                    )
                conn.commit()
            logger.error("Survivor milestone send failed mint=%s thresholds=%s error=%s", mint, thresholds_to_mark, exc)
            return
        if message_id is None:
            with self.connect() as conn:
                for mark_threshold in inserted:
                    conn.execute(
                        "DELETE FROM telegram_entry_outcome_milestones WHERE mint = ? AND threshold = ? AND telegram_message_id IS NULL",
                        (mint, mark_threshold),
                    )
                conn.commit()
            logger.warning("Survivor milestone send returned no message_id mint=%s thresholds=%s", mint, thresholds_to_mark)
            return
        with self.connect() as conn:
            for mark_threshold in inserted:
                conn.execute(
                    "UPDATE telegram_entry_outcome_milestones SET telegram_message_id = ? WHERE mint = ? AND threshold = ?",
                    (message_id, mint, mark_threshold),
                )
            conn.commit()
            logger.info(
                "Survivor milestone sent mint=%s thresholds=%s message_id=%s",
                mint,
                ",".join(f"{t:g}x" for t in inserted),
                message_id,
            )


async def _smoke(mint: str) -> None:
    alerts = SurvivorTelegramAlerts(ROOT / "vlak_aladdin_research.sqlite")
    try:
        await alerts.process_mint(mint)
    finally:
        await alerts.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        asyncio.run(_smoke(sys.argv[1]))


