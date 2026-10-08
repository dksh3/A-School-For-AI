"""S6 tests: telemetry collector."""

from __future__ import annotations

from pathlib import Path

from core.context.telemetry import TelemetryCollector


class TestTelemetry:
    def test_record_and_read(self, tmp_path: Path) -> None:
        tc = TelemetryCollector(worktree=str(tmp_path), session="s1")
        tc.record("compress", ratio=0.5, tokens_saved=100)
        tc.flush()
        events = tc.events()
        assert len(events) == 1
        assert events[0]["event"] == "compress"
        assert events[0]["session"] == "s1"

    def test_flush_is_atomic(self, tmp_path: Path) -> None:
        tc = TelemetryCollector(worktree=str(tmp_path))
        tc.record("ev1")
        tc.record("ev2")
        tc.flush()
        assert tc._buffer == []
        tc.record("ev3")
        tc.flush()
        events = tc.events()
        assert len(events) == 3

    def test_bounded_retention(self, tmp_path: Path) -> None:
        tc = TelemetryCollector(worktree=str(tmp_path))
        for i in range(250):
            tc.record(f"ev{i}", index=i)
        tc.flush()
        events = tc.events()
        assert len(events) <= 200

    def test_corrupt_line_skipped(self, tmp_path: Path) -> None:
        log_path = tmp_path / ".school" / "context" / "telemetry.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text('{"event":"ok"}\nNOT_JSON\n{"event":"ok2"}\n', encoding="utf-8")
        tc = TelemetryCollector(worktree=str(tmp_path))
        events = tc.events()
        assert len(events) == 2

    def test_kill_switch_silent(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("SCHOOL_TELEMETRY", "0")
        tc = TelemetryCollector(worktree=str(tmp_path))
        tc.record("should_not_persist")
        tc.flush()
        events = tc.events()
        assert len(events) == 0

    def test_auto_flush_on_threshold(self, tmp_path: Path) -> None:
        tc = TelemetryCollector(worktree=str(tmp_path))
        for i in range(25):
            tc.record(f"ev{i}")
        # threshold 20 triggers flush mid-way
        assert len(tc._buffer) < 25
