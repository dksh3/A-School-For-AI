"""S7 tests: school_goal."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.agent.goals import goal


class TestGoal:
    def test_set(self, tmp_path: Path) -> None:
        r = goal(str(tmp_path), "set", objective="learn routing")
        assert r.ok is True
        assert r.goal_id.startswith("g")
        assert r.state == "active"

    def test_status(self, tmp_path: Path) -> None:
        goal(str(tmp_path), "set", objective="learn X")
        r = goal(str(tmp_path), "status")
        assert len(r.goals) == 1

    def test_complete(self, tmp_path: Path) -> None:
        goal(str(tmp_path), "set", goal_id="g1", objective="learn X")
        r = goal(str(tmp_path), "complete", goal_id="g1")
        assert r.state == "complete"

    def test_block(self, tmp_path: Path) -> None:
        goal(str(tmp_path), "set", goal_id="g1", objective="learn X")
        r = goal(str(tmp_path), "block", goal_id="g1", constraints="need docs")
        assert r.state == "blocked"

    def test_history(self, tmp_path: Path) -> None:
        goal(str(tmp_path), "set", goal_id="g1", objective="A")
        goal(str(tmp_path), "complete", goal_id="g1")
        goal(str(tmp_path), "set", goal_id="g2", objective="B")
        r = goal(str(tmp_path), "history")
        assert len(r.goals) == 1

    def test_clear(self, tmp_path: Path) -> None:
        goal(str(tmp_path), "set", objective="A")
        goal(str(tmp_path), "clear")
        r = goal(str(tmp_path), "status")
        assert len(r.goals) == 0

    def test_kill_switch(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SCHOOL_GOAL", "0")
        r = goal(str(tmp_path), "set", objective="A")
        assert r.ok is True

    def test_unknown_action(self, tmp_path: Path) -> None:
        r = goal(str(tmp_path), "bogus")
        assert r.ok is False

    def test_not_found(self, tmp_path: Path) -> None:
        r = goal(str(tmp_path), "complete", goal_id="nope")
        assert r.ok is False
