"""Bounded secret-safe provider diagnostics."""

import re

_SECRET = re.compile(
    r"(?i)\b(token|secret|password|api[_-]?key|credential)"
    r"(\s*[:=]\s*)([^\s,;]+)"
)


def redact(value: str, secrets=(), *, limit=2_000) -> str:
    result = str(value)
    for secret in sorted({item for item in secrets if item}, key=len, reverse=True):
        result = result.replace(secret, "[REDACTED]")
    return _SECRET.sub(r"\1\2[REDACTED]", result)[:limit]
