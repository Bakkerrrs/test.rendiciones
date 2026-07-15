"""Bot de Telegram para rendiciones: OCR de boletas → Google Drive + Sheets."""

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request, Response

from app import google_services, ocr
from app.config import ConfigError, get_settings
from app.telegram_client import TelegramClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

SANTIAGO_TZ = ZoneInfo("America/Santiago")

app = FastAPI(title="Bot de rendiciones", docs_url=None, redoc_url=None)

MSG_ERROR_OCR = (
    "⚠️ No pude leer los datos de la boleta. Intenta con una foto más nítida, "
    "bien iluminada y donde se vea el monto total."
)
MSG_ERROR_GENERICO = (
    "⚠️ Ocurrió un error al procesar tu boleta. Inténtalo de nuevo en unos minutos."
)
MSG_SOLO_FOTOS = "Envíame una foto de la boleta o recibo para registrarla. 📸"


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(request: Request) -> Response:
    try:
        settings = get_settings()
    except ConfigError:
        logger.exception("Configuración inválida")
        return Response(status_code=500)

    # Si se configuró un secreto, validar el header que envía Telegram.
    if settings.telegram_webhook_secret:
        header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if header != settings.telegram_webhook_secret:
            logger.warning("Webhook con secret token inválido; se descarta")
            return Response(status_code=403)

    try:
        update = await request.json()
    except Exception:
        logger.warning("Webhook con body no-JSON; se descarta")
        return {"ok": True}

    message = update.get("message") or update.get("edited_message")
    if not isinstance(message, dict):
        return {"ok": True}

    chat_id = (message.get("chat") or {}).get("id")
    if chat_id is None:
        return {"ok": True}

    telegram = TelegramClient(settings.telegram_bot_token)

    file_id, mime_type = _extract_image(message)
    if file_id is None:
        # Solo damos una pista si el usuario escribió texto; stickers y otros
        # tipos de mensaje se ignoran en silencio.
        if message.get("text"):
            await telegram.send_message(chat_id, MSG_SOLO_FOTOS)
        return {"ok": True}

    try:
        await _process_receipt(settings, telegram, chat_id, file_id, mime_type)
    except ocr.OCRError:
        logger.exception("OCR falló para chat %s", chat_id)
        await telegram.send_message(chat_id, MSG_ERROR_OCR)
    except Exception:
        logger.exception("Error procesando boleta para chat %s", chat_id)
        await telegram.send_message(chat_id, MSG_ERROR_GENERICO)

    # Siempre 200: si Telegram recibe un error reintenta el mismo update en loop.
    return {"ok": True}


def _extract_image(message: dict) -> tuple[str | None, str]:
    """Devuelve (file_id, mime_type) si el mensaje trae una imagen."""
    photos = message.get("photo")
    if isinstance(photos, list) and photos:
        # Telegram envía varias resoluciones; la última es la más grande.
        return photos[-1].get("file_id"), "image/jpeg"

    document = message.get("document")
    if isinstance(document, dict):
        mime = document.get("mime_type", "")
        if mime.startswith("image/"):
            return document.get("file_id"), mime

    return None, ""


async def _process_receipt(
    settings, telegram: TelegramClient, chat_id: int, file_id: str, mime_type: str
) -> None:
    image_bytes = await telegram.download_file(file_id)

    now = datetime.now(SANTIAGO_TZ)
    extension = mime_type.split("/")[-1] if "/" in mime_type else "jpg"
    filename = f"boleta_{now.strftime('%Y%m%d_%H%M%S')}_{file_id[-8:]}.{extension}"

    drive_link = await asyncio.to_thread(
        google_services.upload_image_to_drive,
        settings.service_account_info,
        settings.gdrive_folder_id,
        image_bytes,
        filename,
        mime_type,
    )

    data = await ocr.extract_receipt(
        settings.openai_api_key, settings.openai_model, image_bytes, mime_type
    )
    fecha_boleta = data["fecha_boleta"]
    descripcion = data["descripcion"]
    monto = data["monto"]

    row = [
        now.strftime("%Y-%m-%d %H:%M:%S"),
        fecha_boleta or "",
        descripcion,
        monto,
        drive_link,
    ]
    await asyncio.to_thread(
        google_services.append_receipt_row,
        settings.service_account_info,
        settings.google_sheet_id,
        row,
        settings.sheet_worksheet_name,
    )

    monto_fmt = f"{monto:,}".replace(",", ".")
    detalle_fecha = f"boleta del {fecha_boleta}" if fecha_boleta else "boleta sin fecha"
    await telegram.send_message(
        chat_id, f"✅ Guardado: ${monto_fmt} — {descripcion}, {detalle_fecha}"
    )
