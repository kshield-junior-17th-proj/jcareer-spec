"""Small, dependency-free redaction helpers for integration boundaries."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any


_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"https://hooks\.slack\.com/services/[^\s\"'<>]+", re.IGNORECASE),
        "[REDACTED_SLACK_WEBHOOK]",
    ),
    (
        re.compile(r"\b(?:xox[baprs]-[A-Za-z0-9-]{8,}|secret_[A-Za-z0-9_-]{8,})\b"),
        "[REDACTED_TOKEN]",
    ),
    (
        re.compile(
            r"(?i)\b(?:authorization|token|password|api[_-]?key)\s*[:=]\s*[^\s,;]+"
        ),
        "[REDACTED_CREDENTIAL]",
    ),
    (
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"),
        "Bearer [REDACTED]",
    ),
    (
        re.compile(r"(?i)(https?://)[^/@\s:]+:[^/@\s]+@"),
        r"\1[REDACTED]@",
    ),
    (
        re.compile(
            r"\b[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
        ),
        "[REDACTED_EMAIL]",
    ),
    (
        re.compile(r"(?<!\d)(?:\+?82[-. ]?)?0?1[016789][-. ]?\d{3,4}[-. ]?\d{4}(?!\d)"),
        "[REDACTED_PHONE]",
    ),
)


def redact_text(value: object, *, secrets: Iterable[str] = ()) -> str:
    """Return a printable value with configured and recognisable secrets removed."""

    rendered = str(value)
    for secret in sorted({item for item in secrets if item}, key=len, reverse=True):
        rendered = rendered.replace(secret, "[REDACTED]")
    for pattern, replacement in _PATTERNS:
        rendered = pattern.sub(replacement, rendered)
    return rendered


def redact_value(value: Any, *, secrets: Iterable[str] = ()) -> Any:
    """Recursively redact values before they cross a log or diagnostic boundary."""

    if isinstance(value, Mapping):
        return {
            str(key): redact_value(item, secrets=secrets) for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [redact_value(item, secrets=secrets) for item in value]
    if isinstance(value, str):
        return redact_text(value, secrets=secrets)
    return value


def contains_sensitive_text(value: str) -> bool:
    """Detect obvious credentials and direct contact fields in outbound text."""

    return redact_text(value) != value
