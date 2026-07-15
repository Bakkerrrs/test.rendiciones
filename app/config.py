"""Configuración centralizada vía variables de entorno."""

import base64
import binascii
import json
import logging
import os

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """Falta o es inválida una variable de entorno requerida."""


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"Falta la variable de entorno requerida: {name}")
    return value


class Settings:
    def __init__(self) -> None:
        self.telegram_bot_token = _require("TELEGRAM_BOT_TOKEN")
        self.openai_api_key = _require("OPENAI_API_KEY")
        self.google_sheet_id = _require("GOOGLE_SHEET_ID")
        self.gdrive_folder_id = _require("GDRIVE_FOLDER_ID")
        # Opcional: token secreto de Telegram para validar el webhook
        # (header X-Telegram-Bot-Api-Secret-Token).
        self.telegram_webhook_secret = os.environ.get(
            "TELEGRAM_WEBHOOK_SECRET", ""
        ).strip()
        self.sheet_worksheet_name = os.environ.get("SHEET_WORKSHEET_NAME", "").strip()
        self.openai_model = os.environ.get("OPENAI_MODEL", "gpt-4o").strip()
        self._service_account_info: dict | None = None

    @property
    def service_account_info(self) -> dict:
        """Credenciales de la service account, desde ruta a JSON o base64.

        Acepta cualquiera de las dos:
        - GOOGLE_SERVICE_ACCOUNT_FILE: ruta a un archivo .json
        - GOOGLE_SERVICE_ACCOUNT_B64: el JSON completo codificado en base64
        """
        if self._service_account_info is not None:
            return self._service_account_info

        file_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
        b64 = os.environ.get("GOOGLE_SERVICE_ACCOUNT_B64", "").strip()

        if file_path:
            try:
                with open(file_path, encoding="utf-8") as fh:
                    self._service_account_info = json.load(fh)
            except (OSError, json.JSONDecodeError) as exc:
                raise ConfigError(
                    f"No se pudo leer GOOGLE_SERVICE_ACCOUNT_FILE ({file_path}): {exc}"
                ) from exc
        elif b64:
            try:
                self._service_account_info = json.loads(base64.b64decode(b64))
            except (binascii.Error, ValueError, json.JSONDecodeError) as exc:
                raise ConfigError(
                    "GOOGLE_SERVICE_ACCOUNT_B64 no es JSON válido en base64"
                ) from exc
        else:
            raise ConfigError(
                "Define GOOGLE_SERVICE_ACCOUNT_FILE (ruta al JSON) o "
                "GOOGLE_SERVICE_ACCOUNT_B64 (JSON en base64)"
            )
        return self._service_account_info


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
