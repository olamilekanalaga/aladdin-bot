from __future__ import annotations

import logging
import asyncio

import httpx

from .config import Settings

logger = logging.getLogger(__name__)


class TelegramClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = httpx.AsyncClient(timeout=20)

    async def close(self) -> None:
        await self.client.aclose()

    async def send_message(
        self,
        text: str,
        reply_to_message_id: str | None = None,
        reply_markup: dict | None = None,
        retries: int = 2,
    ) -> str | None:
        if not self.settings.telegram_enabled():
            logger.info("Telegram disabled; message was not sent")
            return None
        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
        payload = {
            "chat_id": self.settings.telegram_chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if reply_to_message_id:
            payload["reply_to_message_id"] = int(reply_to_message_id)
            payload["allow_sending_without_reply"] = False
        if reply_markup:
            payload["reply_markup"] = reply_markup
        for attempt in range(retries + 1):
            try:
                response = await self.client.post(url, json=payload)
                response.raise_for_status()
                payload = response.json()
                message_id = payload.get("result", {}).get("message_id")
                return str(message_id) if message_id is not None else None
            except httpx.HTTPStatusError as exc:
                retry_after = None
                try:
                    retry_after = exc.response.json().get("parameters", {}).get("retry_after")
                except ValueError:
                    retry_after = None
                if exc.response.status_code == 429 and retry_after and attempt < retries:
                    await asyncio.sleep(int(retry_after) + 1)
                    continue
                logger.error(
                    "Failed to send Telegram message: status=%s body=%s",
                    exc.response.status_code,
                    exc.response.text[:500],
                )
                return None
            except Exception as exc:
                logger.error("Failed to send Telegram message: %s", exc)
                return None
        return None
