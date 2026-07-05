"""PII redaction for ingested text."""

from __future__ import annotations

import re

PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?\d{1,3}[\s-]?)?(?:\(\d{2,4}\)[\s-]?)?\d{3,4}[\s-]?\d{3,4}(?!\d)"
)
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
URL_RE = re.compile(r"https?://\S+|www\.\S+")
OTP_RE = re.compile(r"\b\d{4,8}\b(?=\s*(?:is|code|otp|pin))", re.IGNORECASE)


def redact_text(text: str) -> str:
    text = URL_RE.sub("[URL]", text)
    text = EMAIL_RE.sub("[EMAIL]", text)
    text = PHONE_RE.sub("[PHONE]", text)
    text = OTP_RE.sub("[OTP]", text)
    return text
