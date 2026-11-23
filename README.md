# AI OCR App

FastAPI service that uses a configurable LLM provider to read images, extract text, classify documents, and store results.

## Features

- **Upload** an image (JPEG, WebP, GIF, TIFF) with a required `Idempotency-Key`
- **Queue** OCR work in PostgreSQL and return an upload ID immediately
- **Process** jobs in a separate worker with bounded retries
- **Deduplicate** transactions by normalized source bank, bank transaction ID, amount, and transaction date
- **Store** images under `filestore/YYYY/MM/DD/<upload_id>.<ext>`
- **Review** upload processing and saved transactions in the local Receipt Desk dashboard
- **Telegram Bot** (`bot/`): capture receipts via chat/photo, trigger async OCR ingestion, and deliver structured transaction confirmation

Completed transactions are stored in `public."transaction"`; upload processing state is stored in `public.ocr_upload_job`. Transactions use a normalized bank/reference key when source bank, transaction ID, amount, and date are available. If that key cannot be built, the worker uses a namespaced SHA-256 fingerprint of the uploaded image, so byte-identical files are deduplicated while different images with the same OCR amount/date remain separate. For older unkeyed transactions, the worker compares stored image bytes among up to 100 most recent rows with matching OCR amount and date, then stores the fingerprint on a matched legacy transaction for subsequent lookups. Re-encoded or recompressed versions are not considered byte-identical. Duplicate jobs point to the matched transaction's existing image path so the dashboard can show which image matched; the redundant uploaded file is removed, and cleanup preserves any image still referenced by a transaction. Temporary OCR failures are retried up to five attempts; failed jobs retain their image for review.

For local development, SQLite tables are created automatically. PostgreSQL schemas are managed by the reviewed migration only; apply it before running the API or worker against Supabase. The API and worker must share the same `FILESTORE_PATH`. Local filestore is suitable only while both processes share a filesystem.

## Setup

```bash
cd ai-ocr-app

# Create venv & install
python -m venv .venv
source .venv/bin/activate
pip install -e .

# Configure
cp .env.example .env
# Configure the LLM provider, endpoint, model and key in `.env`:
# LLM_PROVIDER=openai  # set to google_genai to temporarily use Google's Gen AI SDK
# LLM_BASE_URL=https://api.openai.com/v1  # used by the openai provider
# LLM_MODEL=gpt-4o-mini
# LLM_API_KEY=your-provider-api-key
# For google_genai, LLM_BASE_URL is ignored; set LLM_MODEL and LLM_API_KEY.
# Configure DATABASE_URL with your Supabase direct PostgreSQL connection URL.
# The app uses asyncpg and translates `sslmode=require` to its SSL setting.
# For another OpenAI-compatible provider, set its API base URL, model and key.
# Configure TELEGRAM_BOT_TOKEN for the Telegram bot interface.

# Run the API and worker in separate terminals
uvicorn app.main:app --reload
# In another terminal (worker daemon):
python -m app.services.worker
# In another terminal (Telegram bot):
python -m bot.main
```

Open the local dashboard at `http://127.0.0.1:8765/dashboard/` when the API is running. The dashboard's upload form enqueues supported images; the separate worker must be running to process them.

## Telegram Bot

The `bot/` directory contains the Telegram integration daemon built on `python-telegram-bot`:
- `/start`: Greeting and overview
- `/help`: Upload guidelines, supported formats, and troubleshooting tips
- `/status`: Health check against the FastAPI OCR API
- Receipt Upload (Photo / Document): Ingests images, converts format when necessary, pushes to `/api/documents/upload`, polls completion, and displays transaction summaries with deduplication alerts

Run the bot with:
```bash
python -m bot.main
```

## API

### `POST /api/documents/upload`
Upload an image with a required `Idempotency-Key`. The API saves the file and returns `202 Accepted` with an `upload_id` and `status_url`; it does not wait for OCR. Reuse the same idempotency key when retrying the same request.

```bash
curl -X POST http://localhost:8000/api/documents/upload --header "Idempotency-Key: receipt-upload-unique-request-id" --form "file=@receipt.jpg"
```

### `GET /api/documents/uploads?skip=0&limit=20`
List recent OCR jobs for the dashboard. Pages are bounded to at most 50 jobs and ordered newest first.

### `GET /api/documents/uploads/{upload_id}`
Polls the upload job and returns `PENDING`, `PROCESSING`, `COMPLETED`, `DUPLICATE`, or `FAILED`, along with attempt count and transaction record ID when available.

### `GET /api/documents/`
List stored transactions. Optional query params: `skip` (0 or higher), `limit` (1–50), and `category`.

### `GET /api/documents/{id}`
Get a single transaction by ID.

### `GET /api/documents/{id}/receipt`
Serve the transaction's stored receipt image inline. The route returns `404` when the transaction or image is missing and rejects paths outside the configured filestore.

### `GET /health`
Health check.

## API Docs

Interactive docs at `http://localhost:8000/docs` (Swagger UI).
