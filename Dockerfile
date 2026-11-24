FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

WORKDIR /srv

COPY pyproject.toml README.md ./
COPY app ./app
COPY bot ./bot
COPY dashboard ./dashboard
RUN pip install .

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

# Proxy headers let FastAPI see the original HTTPS scheme behind Render's load balancer.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"$PORT\" --proxy-headers --forwarded-allow-ips '*'"]
