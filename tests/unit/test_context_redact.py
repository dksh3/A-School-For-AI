from __future__ import annotations

import pytest

from core.context.redact import redact

CASES = [
    ("token ghp_abc123XYZ7890123 used", "token [REDACTED] used"),
    ("api_key = sk-abcdef1234567890", "api_key = [REDACTED]"),
    ("Authorization: Bearer eyJhbGciOi.abc123", "Authorization: [REDACTED]"),
    ("AKIA1234567890ABCD12 is the id", "[REDACTED] is the id"),
    ("password: hunter2 okay", "password: [REDACTED] okay"),
    ("plain text with no secrets", "plain text with no secrets"),
    ("", ""),
]


@pytest.mark.parametrize(("raw", "expected"), CASES)
def test_redact(raw: str, expected: str) -> None:
    assert redact(raw) == expected


def test_redact_idempotent() -> None:
    once = redact("key ghp_abcdefghijklmnopqrstuvwxyz")
    assert redact(once) == once
