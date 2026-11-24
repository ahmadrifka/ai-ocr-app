"""Shared-password dashboard sessions and API-key access for machine clients."""

import hashlib
import hmac
import logging
import time

from starlette.requests import Request

from app.config import API_KEY, APP_ENV, DASHBOARD_PASSWORD, SESSION_SECRET


logger = logging.getLogger(__name__)

SESSION_COOKIE = "ocr_session"
API_KEY_HEADER = "X-API-Key"
PROTECTED_PREFIXES = ("/api/", "/docs", "/redoc", "/openapi.json")


def auth_enabled() -> bool:
    return bool(DASHBOARD_PASSWORD or API_KEY)


def validate_auth_config() -> None:
    """Fail fast on unsafe or incomplete auth settings."""
    if APP_ENV == "production" and not auth_enabled():
        raise RuntimeError("Set DASHBOARD_PASSWORD or API_KEY before running in production")
    if DASHBOARD_PASSWORD and not SESSION_SECRET:
        raise RuntimeError("SESSION_SECRET is required when DASHBOARD_PASSWORD is set")
    if not auth_enabled():
        logger.warning("Authentication is disabled; every API endpoint is public")


def requires_auth(path: str) -> bool:
    return auth_enabled() and path.startswith(PROTECTED_PREFIXES)


def is_authorized(request: Request) -> bool:
    if API_KEY and _matches(request.headers.get(API_KEY_HEADER), API_KEY):
        return True
    if DASHBOARD_PASSWORD:
        return is_valid_session(request.cookies.get(SESSION_COOKIE))
    return False


def password_matches(candidate: str) -> bool:
    return bool(DASHBOARD_PASSWORD) and _matches(candidate, DASHBOARD_PASSWORD)


def create_session_token(max_age_seconds: int, *, now: float | None = None) -> str:
    expires_at = int((now or time.time()) + max_age_seconds)
    return f"{expires_at}.{_sign(str(expires_at))}"


def is_valid_session(token: str | None, *, now: float | None = None) -> bool:
    if not token or not SESSION_SECRET:
        return False
    expires_at, _, signature = token.partition(".")
    if not expires_at.isdigit() or not _matches(signature, _sign(expires_at)):
        return False
    return int(expires_at) > (now or time.time())


def _sign(value: str) -> str:
    return hmac.new(SESSION_SECRET.encode(), value.encode(), hashlib.sha256).hexdigest()


def _matches(candidate: str | None, expected: str) -> bool:
    return hmac.compare_digest((candidate or "").encode(), expected.encode())
