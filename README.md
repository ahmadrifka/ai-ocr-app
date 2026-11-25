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
# Optional: set LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY and LANGFUSE_BASE_URL to trace
# each OCR call in Langfuse (model, tokens, latency), grouped by upload ID as session.

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

## Authentication

Authentication is enforced when `DASHBOARD_PASSWORD` or `API_KEY` is set (always required when `APP_ENV=production`). It protects `/api/*` and the OpenAPI docs; `/health`, the static dashboard files and the Telegram webhook (which checks its own secret) stay public.

- **Dashboard:** open `/dashboard/`, sign in with `DASHBOARD_PASSWORD`. The session cookie is signed with `SESSION_SECRET`.
- **Machine clients:** send `X-API-Key: <API_KEY>`. The bot uses `OCR_API_KEY`, falling back to `API_KEY`.

## Deploy to Render (free tier)

The free plan allows one web service, so a single container runs the API, dashboard, OCR worker (`RUN_WORKER_IN_API=true`) and the Telegram bot in webhook mode (`TELEGRAM_WEBHOOK_ENABLED=true`). Receipt images go to a private Supabase Storage bucket because the container disk is wiped on every restart.

1. **Supabase**
   - Apply every migration in `supabase/migrations/`.
   - Copy the **Session pooler** connection string (Connect → Session pooler, port 5432). The direct host is IPv6-only and the transaction pooler breaks asyncpg prepared statements.
   - Create a **private** Storage bucket named `receipts`, and copy the project URL and a secret (service role) key.
2. **Render**
   - New → Blueprint, select this repository; `render.yaml` defines the service.
   - Fill in the secret values: `DATABASE_URL`, `LLM_API_KEY`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `DASHBOARD_PASSWORD`, `TELEGRAM_BOT_TOKEN`, `ALLOWED_TELEGRAM_USER_IDS` (Langfuse keys are optional).
   - `SESSION_SECRET` and `API_KEY` are generated automatically.
3. **Verify**
   - `GET https://<service>.onrender.com/health` returns `{"status": "ok"}`.
   - Sign in at `/dashboard/`, upload a receipt and wait for `COMPLETED`.
   - Send a receipt photo to the bot. On startup the service registers its webhook at `/telegram/webhook`.

A free service sleeps after 15 minutes without traffic; the next request (including a Telegram message) wakes it in roughly a minute. Queued OCR jobs resume once it is awake.

Build and run the container locally:
```bash
docker build -t ai-ocr-app .
docker run --env-file .env -p 8000:8000 ai-ocr-app
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
