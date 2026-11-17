"""Stable keys for matching duplicate bank transactions."""

import datetime as dt
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import re


WIB = dt.timezone(dt.timedelta(hours=7))


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def transaction_dedupe_key(
    source_bank: str | None,
    transaction_id: str | None,
    amount: Decimal | None,
    transaction_date: dt.datetime | None,
) -> str | None:
    """Return a hash only when every agreed duplicate-identifying field exists."""
    if not source_bank or not transaction_id or amount is None or transaction_date is None:
        return None

    bank = _normalize(source_bank)
    reference = _normalize(transaction_id)
    if not bank or not reference:
        return None

    event_date = transaction_date
    if event_date.tzinfo is None:
        event_date = event_date.replace(tzinfo=WIB)
    event_date = event_date.astimezone(dt.timezone.utc).isoformat(timespec="microseconds")
    normalized_amount = format(
        Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f"
    )
    payload = json.dumps(
        [bank, reference, normalized_amount, event_date],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
