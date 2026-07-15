"""Cliente mínimo de la Bot API de Telegram (getFile, descarga, sendMessage)."""

import logging

import httpx

logger = logging.getLogger(__name__)

_API_BASE = "https://api.telegram.org"
_TIMEOUT = httpx.Timeout(30.0)


class TelegramError(Exception):
    pass


class TelegramClient:
    def __init__(self, bot_token: str) -> None:
        self._token = bot_token
        self._api = f"{_API_BASE}/bot{bot_token}"
        self._file_api = f"{_API_BASE}/file/bot{bot_token}"

    async def _call(self, method: str, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(f"{self._api}/{method}", json=payload)
        data = resp.json()
        if not data.get("ok"):
            raise TelegramError(
                f"Telegram {method} falló: {data.get('description', resp.text)}"
            )
        return data["result"]

    async def download_file(self, file_id: str) -> bytes:
        """Resuelve el file_id con getFile y descarga el contenido."""
        result = await self._call("getFile", {"file_id": file_id})
        file_path = result.get("file_path")
        if not file_path:
            raise TelegramError(f"getFile no devolvió file_path para {file_id}")
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{self._file_api}/{file_path}")
            resp.raise_for_status()
            return resp.content

    async def send_message(self, chat_id: int, text: str) -> None:
        try:
            await self._call("sendMessage", {"chat_id": chat_id, "text": text})
        except (TelegramError, httpx.HTTPError):
            # Responder al usuario es best-effort: no debe tumbar el webhook.
            logger.exception("No se pudo enviar mensaje al chat %s", chat_id)
