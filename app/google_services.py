"""Integración con Google Drive (subida de imagen) y Google Sheets (registro).

Todas las funciones de este módulo son síncronas (las librerías de Google no
son async); el llamador debe ejecutarlas con asyncio.to_thread.
"""

import io
import logging

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

logger = logging.getLogger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_credentials: Credentials | None = None


def _get_credentials(service_account_info: dict) -> Credentials:
    global _credentials
    if _credentials is None:
        _credentials = Credentials.from_service_account_info(
            service_account_info, scopes=_SCOPES
        )
    return _credentials


def upload_image_to_drive(
    service_account_info: dict,
    folder_id: str,
    image_bytes: bytes,
    filename: str,
    mime_type: str = "image/jpeg",
) -> str:
    """Sube la imagen a la carpeta de Drive y devuelve un link compartible."""
    creds = _get_credentials(service_account_info)
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)

    media = MediaIoBaseUpload(io.BytesIO(image_bytes), mimetype=mime_type)
    file = (
        drive.files()
        .create(
            body={"name": filename, "parents": [folder_id]},
            media_body=media,
            fields="id, webViewLink",
            supportsAllDrives=True,
        )
        .execute()
    )

    # Link compartible: cualquiera con el enlace puede ver.
    drive.permissions().create(
        fileId=file["id"],
        body={"type": "anyone", "role": "reader"},
        supportsAllDrives=True,
    ).execute()

    return file["webViewLink"]


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
