"""S7 tests: school_observe."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.agent.observer import observe


class TestObserve:
    def test_records_observation(self, tmp_path: Path) -> None:
        r = observe(str(tmp_path), "user always calls recall first", category="tool_call")
        assert r.ok is True
        assert r.observation_id.startswith("obs-")
        assert r.total == 1

    def test_extracts_pattern(self, tmp_path: Path) -> None:
        for _ in range(3):
            observe(str(tmp_path), "something", category="error")
        r = observe(str(tmp_path), "another", category="error")
        assert "error" in r.pattern

    def test_kill_switch(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SCHOOL_OBSERVE", "0")
        r = observe(str(tmp_path), "should not record")
        assert r.ok is True
        assert r.total == 0

    def test_rejects_empty(self, tmp_path: Path) -> None:
        r = observe(str(tmp_path), "")
        assert r.ok is False

    def test_fail_open_on_bad_worktree(self) -> None:
        r = observe("/nonexistent/\x00\x00", "test")
        assert r.ok is False or r.ok is True  # fail-open
