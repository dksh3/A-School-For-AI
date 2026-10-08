from __future__ import annotations

from core.context.layer0 import estimate_tokens, find_spans, protected_from
from core.context.types import Block

ERR = "Traceback (most recent call last): something exploded with a long tail " + "x" * 40


def msg(role: str, content: str, **extra) -> dict:
    return {"role": role, "content": content, **extra}


def test_estimate_tokens() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("a" * 40) == 10


def test_protected_from_respects_tail_budget(monkeypatch) -> None:
    monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "15")
    msgs = [msg("user", "y" * 40) for _ in range(5)]  # 10 tokens each
    assert protected_from(msgs) == 3


def test_duplicate_errors_and_runs_become_spans(monkeypatch) -> None:
    monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
    msgs = [
        msg("user", "please fix"),
        msg("tool", ERR),
        msg("user", "please try again"),
        msg("tool", ERR),
        msg("user", "one more go"),
        msg("tool", "FAILED: another distinct error " + "z" * 50),
        msg("tool", "FAILED: another distinct error " + "z" * 50),
        msg("user", "tail"),
    ]
    spans = find_spans(msgs, [])
    # tail=0 protects only the last message -> region is [0, 7)
    dup = [(s, e) for s, e, _ in spans if (s, e) == (3, 4)]
    run = [(s, e) for s, e, _ in spans if (s, e) == (5, 7)]
    assert dup and run
    assert len(spans) == 2
    summaries = {s: summ for s, e, summ in spans}
    assert "duplicate" in summaries[3]
    assert "collapsed" in summaries[5]


def test_pair_safety_never_splits_tool_call_result(monkeypatch) -> None:
    monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
    assistant = msg("assistant", "", tool_calls=[{"id": "t1"}])
    result = msg("tool", ERR)
    msgs = [
        msg("tool", ERR),  # dup source (index 0)
        msg("user", "context"),
        assistant,  # index 2: tool_calls -> pair with index 3
        result,  # index 3: would be dup span alone; must pull start back to 2
        msg("user", "tail"),
    ]
    spans = find_spans(msgs, [])
    starts_ends = [(s, e) for s, e, _ in spans if s <= 3 <= e]
    # span covering index 3 must include index 2
    assert starts_ends, spans
    assert starts_ends[0][0] == 2


def test_existing_blocks_excluded(monkeypatch) -> None:
    monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
    msgs = [msg("tool", ERR), msg("assistant", "ok"), msg("tool", ERR), msg("user", "tail")]
    existing = [Block.make("b1", 0, 1, [msgs[0]], "prior", 1)]
    spans = find_spans(msgs, existing)
    assert all(not (s < 1 < e) for s, e, _ in spans)  # index 1 (dup target) inside block
    # index 2 is duplicate of 0 but 0 is inside existing block -> no span
    assert spans == []


def test_fail_open_on_junk(monkeypatch) -> None:
    monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
    assert find_spans([None, {"role": "tool", "content": None}], []) == []


def test_fail_open_on_exception() -> None:
    assert find_spans(None, []) == []


def test_run_flushes_on_non_error_tool(monkeypatch) -> None:
    monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
    msgs = [
        msg("tool", ERR),
        msg("tool", ERR),
        msg("tool", "plain ok output"),
        msg("user", "tail"),
    ]
    assert [(s, e) for s, e, _ in find_spans(msgs, [])] == [(0, 2)]
