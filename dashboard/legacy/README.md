# Receipt Desk dashboard

A small browser dashboard for the AI OCR API. It is served by FastAPI at `http://127.0.0.1:8765/dashboard/`, so browser requests use the same origin and need no separate frontend server or CORS setup.

## Start locally

From the repository root, start the API and OCR worker in separate terminals:

```bash
./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8765
./.venv/bin/python -m app.services.worker
```

Open `http://127.0.0.1:8765/dashboard/`. The page queues supported receipt images, refreshes the 20 most recent jobs every five seconds, and shows transactions in 20-row pages. Select **View** on a transaction to open its extracted details and receipt image. The worker must be running for queued receipts to progress.
