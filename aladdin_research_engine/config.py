from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value:
        return value
    env_path = Path(".env")
    if not env_path.exists():
        return default
    try:
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            if not line or line.lstrip().startswith("#") or "=" not in line:
                continue
            key, raw_value = line.split("=", 1)
            if key.strip() == name:
                return raw_value.strip().strip('"').strip("'")
    except OSError:
        return default
    return default


def _int_env(name: str, default: int) -> int:
    raw = _env(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _bool_env(name: str, default: bool = False) -> bool:
    raw = _env(name)
    if not raw:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _strategy_telegram_defaults() -> dict[str, bool]:
    return {
        "research_v2_live": False,
        "early_discovery": False,
        "continuation_runner": True,
        "premium_runner": True,
        "confirmed_runner": True,
    }


def _strategy_bool_map_env(name: str) -> dict[str, bool]:
    values = _strategy_telegram_defaults()
    raw = _env(name)
    if not raw:
        return values
    for item in raw.split(","):
        if not item.strip() or "=" not in item:
            continue
        key, value = item.split("=", 1)
        values[key.strip()] = value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return values


@dataclass(frozen=True)
class Settings:
    vlak_api_key: str = _env("VLAK_API_KEY")
    vlak_base_url: str = _env("VLAK_BASE_URL").rstrip("/")
    telegram_bot_token: str = _env("TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = _env("TELEGRAM_CHAT_ID")
    solana_tracker_api_key: str = _env("SOLANA_TRACKER_API_KEY")
    solana_tracker_base_url: str = _env(
        "SOLANA_TRACKER_BASE_URL", "https://data.solanatracker.io"
    ).rstrip("/")
    solana_tracker_trade_windows_path_template: str = _env(
        "SOLANA_TRACKER_TRADE_WINDOWS_PATH_TEMPLATE"
    )
    database_path: Path = Path(_env("DATABASE_PATH", "vlak_aladdin_research.sqlite"))
    signal_poll_seconds: int = _int_env("SIGNAL_POLL_SECONDS", 10)
    outcome_poll_seconds: int = _int_env("OUTCOME_POLL_SECONDS", 60)
    outcome_track_hours: int = _int_env("OUTCOME_TRACK_HOURS", 24)
    dry_run: bool = _bool_env("DRY_RUN", True)
    telegram_enabled_by_strategy: dict[str, bool] = None

    def require_vlak(self) -> None:
        missing = []
        if not self.vlak_api_key:
            missing.append("VLAK_API_KEY")
        if not self.vlak_base_url:
            missing.append("VLAK_BASE_URL")
        if missing:
            raise RuntimeError(f"Missing required Vlak settings: {', '.join(missing)}")

    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    def telegram_enabled_for_strategy(self, strategy_name: str) -> bool:
        values = self.telegram_enabled_by_strategy or _strategy_telegram_defaults()
        return bool(values.get(strategy_name, False))

    def solana_tracker_enabled(self) -> bool:
        return bool(self.solana_tracker_api_key)

    def solana_tracker_trade_windows_enabled(self) -> bool:
        return bool(
            self.solana_tracker_api_key
            and self.solana_tracker_trade_windows_path_template
        )


settings = Settings(
    telegram_enabled_by_strategy=_strategy_bool_map_env("TELEGRAM_ENABLED_BY_STRATEGY")
)
