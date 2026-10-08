from __future__ import annotations

import copy

from core.context.types import Block
from core.context.view import build_view


def msg(role: str, content: str) -> dict:
    return {"role": role, "content": content}


def test_range_replaced_by_compaction_marker() -> None:
    msgs = [msg("user", "a"), msg("assistant", "b"), msg("user", "c")]
    block = Block.make("b1", 0, 2, msgs[:2], "User asked a; assistant answered b", 1)
    view = build_view(msgs, [block])
    assert len(view.messages) == 2
    marker = view.messages[0]
    assert marker["role"] == "system"
    assert marker["school_block"] == "b1"
    assert "User asked a" in marker["content"]
    assert view.messages[1]["content"] == "c"
    assert view.blocks_included == ["b1"]


def test_originals_never_mutated() -> None:
    msgs = [msg("user", "a"), {"role": "tool", "content": "nested", "meta": {"x": [1]}}]
    snapshot = copy.deepcopy(msgs)
    block = Block.make("b1", 0, 1, msgs[:1], "sum", 0)
    view = build_view(msgs, [block])
    assert msgs == snapshot
    view.messages[-1]["meta"]["x"].append(2)  # mutating view must not touch msgs
    assert msgs == snapshot
    assert view.mutated is False


def test_skeletonized_tool_body_collapsed_in_view() -> None:
    body = (
        "def parse():\n"
        "    return 1\n"
        "    # filler line\n"
        "# … parse() — 12 lines"
    )
    msgs = [msg("tool", body), msg("user", "next")]
    view = build_view(msgs, [])
    assert view.messages[0]["content"] == "# … parse() — 12 lines"
    assert "return 1" not in view.messages[0]["content"]
    assert msgs[0]["content"] == body  # original intact


def test_non_skeleton_content_untouched() -> None:
    msgs = [msg("tool", "plain output line1\nline2")]
    view = build_view(msgs, [])
    assert view.messages[0]["content"] == "plain output line1\nline2"


def test_overlapping_block_skipped_fail_open() -> None:
    msgs = [msg("user", "a"), msg("user", "b"), msg("user", "c")]
    first = Block.make("b1", 0, 2, msgs[:2], "first", 0)
    overlapping = Block.make("b2", 1, 3, msgs[1:], "second", 0)
    view = build_view(msgs, [first, overlapping])
    assert view.blocks_included == ["b1"]  # b2 overlaps -> skipped
    assert any("first" in str(m.get("content")) for m in view.messages)
    assert view.messages[-1]["content"] == "c"


def test_empty_and_junk_inputs() -> None:
    assert build_view([], []).messages == []
    junk = Block(id="", start=5, end=2, messages=[], summary="")
    out = build_view([msg("user", "x")], [junk])
    assert len(out.messages) == 1
    assert out.messages[0]["content"] == "x"
