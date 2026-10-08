"""S2 Task 2: view segments and the five context bridge commands."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from core.context import ContextEngine, build_chip, build_view
from core.context.view import apply_segments, view_segments
from school import bridge


def big_msgs(n: int = 8) -> list[dict]:
    return [
        {"role": "user" if i % 2 == 0 else "assistant", "content": chr(97 + i) * 300}
        for i in range(n)
    ]


@pytest.fixture()
def compressed(tmp_path, monkeypatch) -> tuple[str, list[dict], list]:
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.setenv("SCHOOL_COMPRESS_WINDOW_TOKENS", "200")
    monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
    messages = big_msgs()
    engine = ContextEngine(str(tmp_path), "s1", judge=None)
    report = engine.compress(messages)
    assert report.blocks_added >= 1
    return str(tmp_path), messages, engine.store.load()


def call(command: str, req: dict) -> dict:
    return bridge._COMMANDS[command](req)


class TestSegments:
    def test_segments_match_build_view(self, compressed) -> None:
        _, messages, blocks = compressed

        def roles(items):
            return [(m.get("role"), m.get("content")) for m in items]

        applied = apply_segments(messages, view_segments(messages, blocks))
        assert roles(applied) == roles(build_view(messages, blocks).messages)

    def test_segments_do_not_mutate_input(self, compressed) -> None:
        _, messages, blocks = compressed
        snapshot = copy.deepcopy(messages)
        view_segments(messages, blocks)
        assert messages == snapshot

    def test_no_blocks_means_identity(self) -> None:
        messages = big_msgs(4)
        assert view_segments(messages, []) == []
        assert apply_segments(messages, []) == messages

    def test_skeleton_lines_become_replacements(self) -> None:
        messages = [
            {"role": "user", "content": "q"},
            {"role": "tool", "content": "one\nkeep … marker\nthree"},
            {"role": "assistant", "content": "a"},
        ]
        segments = view_segments(messages, [])
        assert segments == [
            {"index": 1, "role": "", "content": "keep … marker"},
        ]

    def test_apply_segments_never_mutates(self) -> None:
        messages = [{"role": "user", "content": "keep"}]
        out = apply_segments(
            messages, [{"index": 0, "role": "system", "content": "replaced"}]
        )
        assert messages[0]["content"] == "keep"
        assert out[0]["content"] == "replaced"
        assert out[0]["role"] == "system"


class TestContextView:
    def test_returns_segments_and_ctx_chip(self, compressed) -> None:
        worktree, messages, _ = compressed
        resp = call(
            "context_view",
            {"worktree": worktree, "session": "s1", "messages": messages},
        )
        assert resp["ok"] is True
        assert resp["mode"] == "school"
        assert resp["segments"], "compressed session must yield segments"
        assert resp["segments"][0]["content"].startswith(
            "[school] compacted b"
        )
        assert resp["chip"].startswith("[school] ctx")
        assert "tok" in resp["chip"]

    def test_kill_switch_returns_no_segments(self, compressed, monkeypatch) -> None:
        worktree, messages, _ = compressed
        monkeypatch.setenv("SCHOOL_COMPRESS", "0")
        resp = call(
            "context_view",
            {"worktree": worktree, "session": "s1", "messages": messages},
        )
        assert resp == {"ok": True, "mode": "off", "segments": [], "chip": ""}

    def test_disabled_by_school_ctx(self, compressed, monkeypatch) -> None:
        worktree, messages, _ = compressed
        monkeypatch.setenv("SCHOOL_CTX", "0")
        resp = call(
            "context_view",
            {"worktree": worktree, "session": "s1", "messages": messages},
        )
        assert resp["mode"] == "off"
        assert resp["segments"] == []

    def test_dcp_keep_decision_yields_no_segments(self, compressed) -> None:
        worktree, messages, _ = compressed
        from core.context.coexist import save_state

        save_state(worktree, {"decision": "keep"})
        resp = call(
            "context_view",
            {"worktree": worktree, "session": "s1", "messages": messages},
        )
        assert resp["mode"] == "dcp"
        assert resp["segments"] == []
        assert resp["chip"] == ""

    def test_junk_messages_fail_open(self, compressed) -> None:
        worktree, _, _ = compressed
        resp = call(
            "context_view",
            {"worktree": worktree, "session": "s1", "messages": "nope"},
        )
        assert resp["ok"] is True
        assert resp["segments"] == []


class TestContextStatusCompressRestore:
    def test_status_reports_blocks_and_chip(self, compressed) -> None:
        worktree, _, _ = compressed
        resp = call(
            "context_status", {"worktree": worktree, "session": "s1"}
        )
        assert resp["ok"] is True
        assert resp["mode"] == "school"
        assert resp["dcp"] is False
        assert resp["blocks"] >= 1
        assert resp["chip"].startswith("[school] compacted")
        assert resp["tokens_saved"] > 0

    def test_status_empty_session(self, tmp_path) -> None:
        resp = call(
            "context_status",
            {"worktree": str(tmp_path), "session": "fresh"},
        )
        assert resp["ok"] is True
        assert resp["blocks"] == 0
        assert resp["chip"] == ""
        assert resp["decision"] == ""

    def test_status_disabled(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("SCHOOL_CTX", "0")
        resp = call(
            "context_status", {"worktree": str(tmp_path), "session": "s1"}
        )
        assert resp["disabled"] is True
        assert resp["mode"] == "off"
        assert resp["chip"] == ""

    def test_compress_writes_blocks(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("SCHOOL_COMPRESS_WINDOW_TOKENS", "200")
        monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
        resp = call(
            "context_compress",
            {"worktree": str(tmp_path), "session": "c1", "messages": big_msgs()},
        )
        assert resp["ok"] is True
        assert resp["triggered"] is True
        assert resp["blocks_added"] >= 1
        assert resp["tokens_saved"] > 0
        assert resp["chip"].startswith("[school] compacted")

    def test_compress_empty_messages_skips(self, tmp_path) -> None:
        resp = call(
            "context_compress",
            {"worktree": str(tmp_path), "session": "c1", "messages": []},
        )
        assert resp["ok"] is True
        assert resp["triggered"] is False
        assert resp["skipped"] in {"empty", "below_threshold"}
        assert resp["chip"] == ""

    def test_restore_roundtrip_is_idempotent(self, compressed) -> None:
        worktree, _, _ = compressed
        first = call(
            "context_restore", {"worktree": worktree, "session": "s1"}
        )
        assert first["ok"] is True
        assert first["messages"]
        assert first["chip"].startswith("[school] compacted")
        assert first["restores"] >= 1
        second = call(
            "context_restore", {"worktree": worktree, "session": "s1"}
        )
        assert second["restores"] == first["restores"] + 1

    def test_restore_unknown_block(self, tmp_path) -> None:
        resp = call(
            "context_restore",
            {"worktree": str(tmp_path), "session": "s1", "block_id": "b999"},
        )
        assert resp["ok"] is False
        assert resp["reason"] in {"no_blocks", "block_not_found"}
        assert resp["chip"] == ""

    def test_status_survives_corrupt_store(self, tmp_path) -> None:
        from core.context.store import session_file

        path = session_file(str(tmp_path), "bad")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{{{", encoding="utf-8")
        resp = call(
            "context_status", {"worktree": str(tmp_path), "session": "bad"}
        )
        assert resp["ok"] is True
        assert resp["blocks"] == 0


class TestContextCoexist:
    def test_get_defaults(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        resp = call(
            "context_coexist",
            {"worktree": str(tmp_path), "action": "get"},
        )
        assert resp["ok"] is True
        assert resp["dcp"] is False
        assert resp["decision"] == ""
        assert resp["mode"] == "school"
        assert resp["offer"].startswith("School can now handle compression")

    def test_set_offer_and_decision(self, tmp_path) -> None:
        wt = str(tmp_path)
        set_offer = call(
            "context_coexist",
            {"worktree": wt, "action": "set_offer"},
        )
        assert set_offer == {"ok": True, "offer_shown": True}
        switch = call(
            "context_coexist",
            {"worktree": wt, "action": "set_decision", "decision": "switch"},
        )
        assert switch["ok"] is True
        assert switch["mode"] == "school"
        state = json.loads(
            Path(wt, ".school", "context", "coexistence.json").read_text(
                encoding="utf-8"
            )
        )
        assert state["decision"] == "switch"
        assert state["offer_shown"] is True

    def test_rejects_bad_inputs(self, tmp_path) -> None:
        wt = str(tmp_path)
        bad = call(
            "context_coexist",
            {"worktree": wt, "action": "set_decision", "decision": "delete"},
        )
        assert bad["ok"] is False
        assert bad["error"]["type"] == "validation"
        unknown = call(
            "context_coexist", {"worktree": wt, "action": "explode"}
        )
        assert unknown["ok"] is False

    def test_hint_marks_dcp_seen(self, tmp_path) -> None:
        wt = str(tmp_path)
        resp = call(
            "context_coexist",
            {"worktree": wt, "action": "get", "dcp": True},
        )
        assert resp["dcp"] is True
        assert resp["mode"] == "dcp"
        state = json.loads(
            Path(wt, ".school", "context", "coexistence.json").read_text(
                encoding="utf-8"
            )
        )
        assert state["dcp_seen"] is True


class TestWiring:
    def test_all_five_commands_registered(self) -> None:
        for name in (
            "context_status",
            "context_compress",
            "context_restore",
            "context_view",
            "context_coexist",
        ):
            assert name in bridge._COMMANDS, name

    def test_chip_voice_helpers(self, compressed) -> None:
        worktree, messages, _ = compressed
        view = call(
            "context_view",
            {"worktree": worktree, "session": "s1", "messages": messages},
        )
        assert build_chip(used_ratio=0.62, saved_tokens=18400) == (
            "[school] ctx 62% · −18.4k tok"
        )
        assert view["chip"].startswith("[school] ctx")
