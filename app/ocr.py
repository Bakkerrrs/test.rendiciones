"""Extracción de datos de boletas con OpenAI gpt-4o Vision y salida estructurada."""

import base64
import json
import logging

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class OCRError(Exception):
    """El modelo no pudo extraer datos válidos de la imagen."""


_RECEIPT_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "boleta",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "fecha_boleta": {
                    "type": ["string", "null"],
                    "description": (
                        "Fecha de emisión de la boleta en formato YYYY-MM-DD, "
                        "o null si no aparece en la imagen."
                    ),
                },
                "descripcion": {
                    "type": "string",
                    "description": (
                        "Descripción breve de la compra (comercio y/o ítems "
                        "principales)."
                    ),
                },
                "monto": {
                    "type": "integer",
                    "description": (
                        "Monto total en pesos chilenos, como entero sin "
                        "separadores de miles ni símbolo de moneda. Ej: 15990."
                    ),
                },
            },
            "required": ["fecha_boleta", "descripcion", "monto"],
            "additionalProperties": False,
        },
    },
}

_PROMPT = (
    "Eres un asistente que extrae datos de boletas y recibos chilenos. "
    "Analiza la imagen y extrae: fecha_boleta (fecha de emisión, formato "
    "YYYY-MM-DD, null si no es visible), descripcion (breve, en español) y "
    "monto (total en pesos chilenos como entero, ej. $15.990 -> 15990)."
)


async def extract_receipt(
    api_key: str, model: str, image_bytes: bytes, mime_type: str = "image/jpeg"
) -> dict:
    """Devuelve {"fecha_boleta": str|None, "descripcion": str, "monto": int}."""
    client = AsyncOpenAI(api_key=api_key)
    data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode()}"

    response = await client.chat.completions.create(
        model=model,
        response_format=_RECEIPT_SCHEMA,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
    )

    choice = response.choices[0]
    if choice.message.refusal:
        raise OCRError(f"El modelo rechazó la solicitud: {choice.message.refusal}")

    raw = choice.message.content
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        logger.error("Respuesta OCR no es JSON válido: %r", raw)
        raise OCRError("La respuesta del OCR no es JSON válido") from exc

    if not isinstance(data.get("monto"), int) or not isinstance(
        data.get("descripcion"), str
    ):
        logger.error("Respuesta OCR con estructura inesperada: %r", data)
        raise OCRError("La respuesta del OCR no tiene la estructura esperada")

    return data
