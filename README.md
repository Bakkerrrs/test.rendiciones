# Bot de rendiciones — Telegram + OCR + Google Sheets/Drive

Bot de Telegram que recibe fotos de boletas/recibos, extrae los datos con
OpenAI `gpt-4o` (Vision, salida estructurada), sube la imagen original a
Google Drive y registra todo en Google Sheets.

## Flujo

1. El usuario envía una foto al bot.
2. El webhook (`POST /webhook`) valida que el mensaje traiga una imagen
   (foto o documento con `mime_type` de imagen; texto y stickers se ignoran).
3. Se descarga la imagen vía `getFile` de Telegram.
4. Se sube el original a una carpeta de Google Drive y se obtiene un link
   compartible.
5. `gpt-4o` extrae `fecha_boleta` (YYYY-MM-DD o null), `descripcion` y
   `monto` (entero, pesos chilenos).
6. Se agrega una fila al Sheet: **Fecha de Subida** (hora de
   America/Santiago), **Fecha de Boleta**, **Descripción**, **Monto**,
   **Link Imagen**.
7. El bot confirma: `✅ Guardado: $15.990 — Almuerzo, boleta del 2026-07-14`.

## Estructura

```
app/
├── main.py              # FastAPI: POST /webhook, GET /health
├── config.py            # Variables de entorno y credenciales
├── telegram_client.py   # getFile, descarga, sendMessage
├── ocr.py               # gpt-4o Vision con json_schema
└── google_services.py   # Drive (subida) + Sheets (append_row)
```

## Variables de entorno

| Variable | Requerida | Descripción |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | ✅ | Token del bot (de @BotFather) |
| `OPENAI_API_KEY` | ✅ | API key de OpenAI |
| `GOOGLE_SHEET_ID` | ✅ | ID del spreadsheet (está en su URL) |
| `GDRIVE_FOLDER_ID` | ✅ | ID de la carpeta de Drive (está en su URL) |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | una de las dos | Ruta al JSON de la service account |
| `GOOGLE_SERVICE_ACCOUNT_B64` | una de las dos | El JSON de la service account en base64 |
| `TELEGRAM_WEBHOOK_SECRET` | opcional | Valida el header `X-Telegram-Bot-Api-Secret-Token` |
| `SHEET_WORKSHEET_NAME` | opcional | Hoja dentro del spreadsheet (default: la primera) |
| `OPENAI_MODEL` | opcional | Default `gpt-4o` |

Copia `.env.example` a `.env` como punto de partida para correr en local.

## 1. Crear la service account y compartir accesos

1. En [Google Cloud Console](https://console.cloud.google.com), crea (o elige)
   un proyecto y habilita las APIs **Google Sheets API** y **Google Drive API**
   (APIs & Services → Enable APIs).
2. Ve a **IAM & Admin → Service Accounts → Create Service Account**. No
   necesita roles del proyecto.
3. Entra a la service account → **Keys → Add Key → Create new key → JSON** y
   descarga el archivo (ej. `service-account.json`). **No lo commitees.**
4. Copia el email de la service account (algo como
   `mi-bot@mi-proyecto.iam.gserviceaccount.com`) y compárte con él:
   - El **Google Sheet**: botón "Compartir" → pegar el email → rol **Editor**.
   - La **carpeta de Drive** donde irán las imágenes: "Compartir" → pegar el
     email → rol **Editor** (o "Administrador de contenido" si es una unidad
     compartida).
5. Deja la primera fila del Sheet con los encabezados:
   `Fecha de Subida | Fecha de Boleta | Descripción | Monto | Link Imagen`.

Para pasar las credenciales por variable en vez de archivo (útil en Cloud Run):

```bash
base64 -w0 service-account.json   # el resultado va en GOOGLE_SERVICE_ACCOUNT_B64
```

## 2. Correr en local con ngrok

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # completa los valores
set -a; source .env; set +a

uvicorn app.main:app --port 8080
```

En otra terminal, expone el puerto con ngrok:

```bash
ngrok http 8080
```

Copia la URL pública HTTPS que entrega ngrok (ej. `https://abc123.ngrok.app`)
y configura el webhook (paso 3).

Verifica el healthcheck: `curl http://localhost:8080/health` → `{"status":"ok"}`.

## 3. Configurar el webhook de Telegram

Con la URL pública (de ngrok o de Cloud Run):

```bash
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -d "url=https://TU-URL-PUBLICA/webhook" \
  -d "secret_token=${TELEGRAM_WEBHOOK_SECRET}"   # opcional pero recomendado
```

Para revisar el estado del webhook:

```bash
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo"
```

Si usas `secret_token`, define la misma cadena en la variable
`TELEGRAM_WEBHOOK_SECRET` del servicio; los requests sin ese header se
rechazan con 403.

> Nota: cada vez que ngrok cambie de URL debes volver a llamar `setWebhook`.

## 4. Desplegar a Cloud Run

El mismo código corre sin cambios; solo cambian las variables de entorno.

```bash
gcloud run deploy rendiciones-bot \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars "TELEGRAM_BOT_TOKEN=...,OPENAI_API_KEY=...,GOOGLE_SHEET_ID=...,GDRIVE_FOLDER_ID=...,GOOGLE_SERVICE_ACCOUNT_B64=$(base64 -w0 service-account.json),TELEGRAM_WEBHOOK_SECRET=..."
```

(Para producción es preferible guardar los secretos en Secret Manager y
montarlos con `--set-secrets`.)

Al terminar, `gcloud` muestra la URL del servicio (ej.
`https://rendiciones-bot-xxxx.a.run.app`). Apunta el webhook de Telegram a
`https://rendiciones-bot-xxxx.a.run.app/webhook` (paso 3) y listo.

El contenedor respeta la variable `PORT` que inyecta Cloud Run; el
healthcheck queda disponible en `GET /health`.

## Manejo de errores

- Si el OCR falla o devuelve JSON inválido, el bot responde con un mensaje
  claro pidiendo una foto más nítida; el error queda logueado y el servicio
  sigue arriba.
- El webhook siempre responde 200 a Telegram (salvo secreto inválido) para
  evitar que Telegram reintente el mismo update en loop.
- Mensajes que no son imágenes: los textos reciben una pista
  ("Envíame una foto…"); stickers y otros tipos se ignoran.
