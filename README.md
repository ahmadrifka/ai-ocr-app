# AI OCR App

FastAPI service that uses an LLM (OpenAI vision) to read images, extract text, classify documents, and store results.

## Features

- **Upload** an image (JPEG, PNG, WebP, GIF, TIFF) with a required `Idempotency-Key`
- **Queue** OCR work in PostgreSQL and return an upload ID immediately
- **Process** jobs in a separate worker with bounded retries
- **Deduplicate** transactions by normalized source bank, bank transaction ID, amount, and transaction date
- **Store** images under `filestore/YYYY/MM/DD/<upload_id>.<ext>`

Completed transactions are stored in `public."transaction"`; upload processing state is stored in `public.ocr_upload_job`. If OCR succeeds but any dedupe field is missing, the transaction is saved without automatic deduplication. Duplicate uploads keep the original transaction/image and remove the duplicate image after the database status is committed. Temporary OCR failures are retried up to five attempts; failed jobs retain their image for review.

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
# Configure the LLM endpoint, model and key in `.env`:
# LLM_BASE_URL=https://api.openai.com/v1
# LLM_MODEL=gpt-4o-mini
# LLM_API_KEY=your-provider-api-key
# Configure DATABASE_URL with your Supabase direct PostgreSQL connection URL.
# The app uses asyncpg and translates `sslmode=require` to its SSL setting.
# For another OpenAI-compatible provider, set its API base URL, model and key.


# Run the API and worker in separate terminals
uvicorn app.main:app --reload
# In another terminal:
python -m app.services.worker
```

## API

### `POST /api/documents/upload`
Upload an image with a required `Idempotency-Key`. The API saves the file and returns `202 Accepted` with an `upload_id` and `status_url`; it does not wait for OCR. Reuse the same idempotency key when retrying the same request.

```bash
curl -X POST http://localhost:8000/api/documents/upload --header "Idempotency-Key: receipt-upload-unique-request-id" --form "file=@receipt.jpg"
```

### `GET /api/documents/uploads/{upload_id}`
Polls the upload job and returns `PENDING`, `PROCESSING`, `COMPLETED`, `DUPLICATE`, or `FAILED`, along with attempt count and transaction record ID when available.

### `GET /api/documents/`
List stored transactions. Optional query params: `skip`, `limit`, `category`.

### `GET /api/documents/{id}`
Get a single transaction by ID.

### `GET /health`
Health check.

## API Docs

Interactive docs at `http://localhost:8000/docs` (Swagger UI).
