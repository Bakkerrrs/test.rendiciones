"""Integración con Google Cloud Storage (imágenes) y Google Sheets (registro).

Todas las funciones de este módulo son síncronas (las librerías de Google no
son async); el llamador debe ejecutarlas con asyncio.to_thread.
"""

import logging

import gspread
from google.cloud import storage
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/devstorage.read_write",
]

_credentials: Credentials | None = None


def _get_credentials(service_account_info: dict) -> Credentials:
    global _credentials
    if _credentials is None:
        _credentials = Credentials.from_service_account_info(
            service_account_info, scopes=_SCOPES
        )
    return _credentials


def upload_image_to_gcs(
    service_account_info: dict,
    bucket_name: str,
    image_bytes: bytes,
    filename: str,
    mime_type: str = "image/jpeg",
) -> str:
    """Sube la imagen al bucket y devuelve su URL pública.

    El bucket debe tener lectura pública a nivel de bucket
    (allUsers: roles/storage.objectViewer) para que el link del Sheet
    sea visible sin autenticación.
    """
    creds = _get_credentials(service_account_info)
    client = storage.Client(
        project=service_account_info.get("project_id"), credentials=creds
    )
    blob = client.bucket(bucket_name).blob(filename)
    blob.upload_from_string(image_bytes, content_type=mime_type)
    return f"https://storage.googleapis.com/{bucket_name}/{filename}"


def append_receipt_row(
    service_account_info: dict,
    sheet_id: str,
    row: list,
    worksheet_name: str = "",
) -> None:
    """Agrega una fila al Sheet.

    Orden de columnas: Fecha de Subida, Fecha de Boleta, Descripción,
    Monto, Link Imagen.
    """
    creds = _get_credentials(service_account_info)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(sheet_id)
    worksheet = (
        spreadsheet.worksheet(worksheet_name) if worksheet_name else spreadsheet.sheet1
    )
    worksheet.append_row(row, value_input_option="USER_ENTERED")
