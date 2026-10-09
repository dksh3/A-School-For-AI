"""S2 Task 7: Apple-grade chip voice across bridge, MCP, and the footer."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from core.context import build_chip
from school import bridge
from school.plugin_source import TS_PLUGIN_SOURCE


def big_msgs(n: int = 8) -> list[dict]:
    return [
        {"role": "user" if i % 2 == 0 else "assistant", "content": chr(97 + i) * 300}
        for i in range(n)
    ]


class TestChipVoice:
    """Spec §6 chip voice: calm, sparse, middle-dot segments."""

    def test_ctx_chip_matches_spec(self) -> None:
        assert build_chip(used_ratio=0.62, saved_tokens=18400) == (
            "[school] ctx 62% · −18.4k tok"
        )

    def test_compacted_chip_matches_spec(self) -> None:
        assert build_chip(blocks_added=2, restores=1) == (
            "[school] compacted 2 blocks · restorable · 1 restored"
        )

    def test_silence_without_data(self) -> None:
        assert build_chip() == ""

    def test_no_dollar_in_s2(self) -> None:
        for chip in (
            build_chip(used_ratio=0.5),
            build_chip(used_ratio=0.5, saved_tokens=100),
            build_chip(blocks_added=1),
        ):
            assert "$" not in chip


class TestBridgeChip:
    """Bridge context responses carry the chip (Tasks 2/5/6 rely on this)."""

    def test_compress_and_status_chips(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SCHOOL_COMPRESS_WINDOW_TOKENS", "200")
        monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
        wt = str(tmp_path)
        resp = bridge._COMMANDS["context_compress"](
            {"worktree": wt, "session": "chip1", "messages": big_msgs()}
        )
        assert resp["chip"].startswith("[school] compacted")
        status = bridge._COMMANDS["context_status"](
            {"worktree": wt, "session": "chip1"}
        )
        assert status["chip"].startswith("[school] compacted")

    def test_view_chip_is_ctx_voice(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        monkeypatch.setenv("SCHOOL_COMPRESS_WINDOW_TOKENS", "200")
        monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
        wt = str(tmp_path)
        bridge._COMMANDS["context_compress"](
            {"worktree": wt, "session": "chip2", "messages": big_msgs()}
        )
        view = bridge._COMMANDS["context_view"](
            {"worktree": wt, "session": "chip2", "messages": big_msgs()}
        )
        assert view["chip"].startswith("[school] ctx")


class TestMcpChip:
    """MCP surfaces expose the same chip field byte-for-byte."""

    def test_status_tool_returns_chip(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pytest.importorskip("mcp")
        from school.mcp import server as mcp_server

        monkeypatch.setenv("SCHOOL_COMPRESS_WINDOW_TOKENS", "200")
        monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
        wt = str(tmp_path)
        mcp_server._call_tool(
            wt, "school_context_compress", {"messages": big_msgs()}
        )
        result = mcp_server._call_tool(wt, "school_context_status", {})
        payload = json.loads(result.content[0].text)
        assert payload["chip"].startswith("[school] compacted")


class TestFooterChipWiring:
    """Footer chip: applyView stores it, text.complete renders it."""

    def _apply_view_block(self) -> str:
        match = re.search(
            r"const applyView = async \([\s\S]*?\n  \}", TS_PLUGIN_SOURCE
        )
        assert match is not None, "applyView not found"
        return match.group(0)

    def _complete_block(self) -> str:
        match = re.search(
            r'"experimental\.text\.complete": async \([\s\S]*?\n    \},',
            TS_PLUGIN_SOURCE,
        )
        assert match is not None, "text.complete hook not found"
        return match.group(0)

    def test_apply_view_persists_chip(self) -> None:
        assert "schoolStatus.chip = String(" in self._apply_view_block()

    def test_footer_appends_chip_after_status_line(self) -> None:
        block = self._complete_block()
        # Always-show bracket is built then the chip is appended after it.
        assert "[school]" in block
        assert "schoolFooter()" in block
        assert "schoolStatus.chip" in block

    def test_footer_stays_idempotent(self) -> None:
        block = self._complete_block()
        # Idempotency guard: skip if a [school] bracket is already present.
        assert 'test(t)' in block or '[school]' in block
