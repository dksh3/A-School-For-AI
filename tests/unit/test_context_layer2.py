from __future__ import annotations

from core.context.layer2 import emergency_span
from core.context.types import Block


def msg(role: str, content: str) -> dict:
    return {"role": role, "content": content}


def test_picks_oldest_free_segment(monkeypatch) -> None:
    monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
    msgs = [
        msg("user", "first"),
        msg("assistant", "answer"),
        msg("user", "second"),
        msg("assistant", "answer2"),
        msg("user", "tail"),  # protected (tail=0 -> last msg only)
    ]
    span = emergency_span(msgs, [])
    assert span is not None
    start, end, summary = span
    assert (start, end) == (0, 4)  # everything before protected tail, one span
    assert "emergency" in summary
    assert "2 messages" in summary or "4 messages" in summary or "messages" in summary


def test_skips_existing_blocks(monkeypatch) -> None:
    monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
    msgs = [msg("user", "a"), msg("assistant", "b"), msg("user", "c"), msg("user", "tail")]
    existing = [Block.make("b1", 0, 2, msgs[:2], "prior", 0)]
    span = emergency_span(msgs, existing)
    assert span is not None
    start, end, _ = span
    assert (start, end) == (2, 3)  # only the free middle segment


def test_none_when_nothing_free(monkeypatch) -> None:
    monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
    msgs = [msg("user", "only"), msg("user", "tail")]
    existing = [Block.make("b1", 0, 1, msgs[:1], "prior", 0)]
    assert emergency_span(msgs, existing) is None
    assert emergency_span([], []) is None


def test_pair_safety(monkeypatch) -> None:
    monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
    msgs = [
        {"role": "assistant", "content": "", "tool_calls": [{"id": "t1"}]},
        msg("tool", "result"),
        msg("user", "tail"),
    ]
    span = emergency_span(msgs, [])
    assert span is not None
    assert (span[0], span[1]) == (0, 2)  # pair kept whole


def test_summary_redacts_first_line_secrets(monkeypatch) -> None:
    monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
    secret = "sk-" + "a" * 40
    msgs = [
        msg("user", f"using {secret} now"),
        msg("assistant", "ok"),
        msg("user", "tail"),
    ]
    span = emergency_span(msgs, [])
    assert span is not None
    summary = span[2]
    assert "[REDACTED]" in summary
    assert secret not in summary
