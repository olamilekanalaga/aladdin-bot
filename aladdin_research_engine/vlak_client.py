from __future__ import annotations

import logging
from typing import Any

import httpx

from .config import Settings

logger = logging.getLogger(__name__)


class VlakClient:
    def __init__(self, settings: Settings) -> None:
        settings.require_vlak()
        self.settings = settings
        self.client = httpx.AsyncClient(timeout=20)

    async def close(self) -> None:
        await self.client.aclose()

    async def fetch_signals(self) -> Any | None:
        url = f"{self.settings.vlak_base_url}/api/signals"
        try:
            response = await self.client.get(url, params={"apikey": self.settings.vlak_api_key})
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Failed to fetch Vlak signals: status=%s body=%s",
                exc.response.status_code,
                exc.response.text[:500],
            )
            return None
        except Exception as exc:
            logger.error("Failed to fetch Vlak signals: %s", exc)
            return None

    async def fetch_outcome(self, mint: str) -> dict[str, Any] | None:
        url = f"{self.settings.vlak_base_url}/api/signal/{mint}/outcome"
        try:
            response = await self.client.get(url, params={"apikey": self.settings.vlak_api_key})
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, dict) else {"data": payload}
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Failed to fetch Vlak outcome for %s: status=%s body=%s",
                mint,
                exc.response.status_code,
                exc.response.text[:500],
            )
            return None
        except Exception as exc:
            logger.error("Failed to fetch Vlak outcome for %s: %s", mint, exc)
            return None
