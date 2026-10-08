"""S7 tests: school_progress."""

from __future__ import annotations

from pathlib import Path

from core.agent.progress import progress


class TestProgress:
    def test_progress_write(self, tmp_path: Path) -> None:
        items = [
            {"content": "task 1", "status": "completed"},
            {"content": "task 2", "status": "pending"},
        ]
        r = progress(str(tmp_path), "write", items=items)
        assert r.ok is True
        assert len(r.items) == 2

    def test_progress_read(self, tmp_path: Path) -> None:
        items = [{"content": "done", "status": "completed"}]
        progress(str(tmp_path), "write", items=items)
        r = progress(str(tmp_path), "read")
        assert r.ok is True
        assert len(r.items) == 1

    def test_progress_bars(self, tmp_path: Path) -> None:
        items = [
            {"content": "step 1", "status": "completed"},
            {"content": "step 2", "status": "in_progress"},
        ]
        r = progress(str(tmp_path), "write", items=items)
        assert "\u2588" in r.bars  # █
        assert "step 1" in r.bars

    def test_progress_kill_switch(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("SCHOOL_PROGRESS", "0")
        r = progress(str(tmp_path), "write", items=[{"content": "x", "status": "pending"}])
        assert r.ok is True
        assert r.items == []

    def test_progress_unknown_action(self, tmp_path: Path) -> None:
        r = progress(str(tmp_path), "invalid")
        assert r.ok is False
