# AI OCR App

FastAPI service that uses an LLM (OpenAI vision) to read images, extract text, classify documents, and store results.

## Features

- **Upload** an image (JPEG, PNG, WebP, GIF, TIFF)
- **Extraction** — LLM reads transaction details from the image and classifies the document
- **Storage** — image saved to local filestore; extracted transaction fields and timestamps saved to Supabase PostgreSQL

Stored records are in the `public."transaction"` table and include `created_at`, `updated_at`, `transaction_date`, `description`, `category`, `transaction_type`, beneficiary/source bank and account details, `amount`, and `asset_path`. Expense receipts are initially classified from the expense-description table in the LLM prompt; if the beneficiary matches an account in `public.accounts`, the transaction is saved as `transaction_type = "INCOMING"` and `category = "sale"`. Indonesian amount dots are treated as thousands separators. Fields the image does not provide are stored as `null`; `amount` is numeric and does not store a currency because there is no currency column.

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


# Run
uvicorn app.main:app --reload
```

## API

### `POST /api/documents/upload`
Upload an image file. Returns extracted transaction fields, including the transaction date and category.

```bash
curl -X POST http://localhost:8000/api/documents/upload \
  -F "file=@receipt.jpg"
```

### `GET /api/documents/`
List transactions. Optional query params: `skip`, `limit`, `category`.

### `GET /api/documents/{id}`
Get a single document by ID.

### `GET /health`
Health check.

## API Docs

Interactive docs at `http://localhost:8000/docs` (Swagger UI).
