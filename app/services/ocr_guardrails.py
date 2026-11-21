"""Deterministic review flags for OCR-extracted transaction descriptions."""

import re


_RULES = {
    "abusive_language": re.compile(
        r"\b(?:fuck(?:ing)?|shit|bitch|bastard|asshole|bangsat|bajingan|anjing|kontol|memek)\b",
        re.I,
    ),
    "sensitive_credentials_request": re.compile(
        r"\b(?:password|passcode|otp|one[- ]time code|pin)\b", re.I
    ),
    "urgent_payment_pressure": re.compile(
        r"\b(?:urgent|immediately|right now|segera|mendesak|sekarang)\b.{0,60}\b(?:transfer|pay|payment|send money|bayar|pembayaran|kirim uang)\b"
        r"|\b(?:transfer|pay|payment|send money|bayar|pembayaran|kirim uang)\b.{0,60}\b(?:urgent|immediately|right now|segera|mendesak|sekarang)\b",
        re.I,
    ),
    "instruction_like_content": re.compile(
        r"\b(?:ignore (?:all )?(?:previous|prior) instructions|reveal (?:the )?(?:system prompt|secrets?)|abaikan instruksi (?:sebelumnya|terdahulu)|ungkap (?:prompt sistem|rahasia))\b",
        re.I,
    ),
}


def review_flags(description: str) -> list[str]:
    """Return review reason codes; matches are advisory, not proof of fraud."""
    return [code for code, pattern in _RULES.items() if pattern.search(description)]
