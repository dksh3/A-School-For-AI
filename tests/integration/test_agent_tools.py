"""S7 integration tests: agent tools end-to-end."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from core.agent.executor import execute
from core.agent.explorer import explore
from core.agent.goals import goal
from core.agent.navigator import navigate
from core.agent.observer import observe
from core.agent.progress import progress
from core.agent.researcher import research
from core.agent.sessions import session


class TestAgentToolsEndToEnd:
    def test_observe_and_goal_flow(self, tmp_path: Path) -> None:
        r1 = observe(str(tmp_path), "user prefers grep first", category="tool_call")
        assert r1.ok
        r2 = goal(str(tmp_path), "set", goal_id="g1", objective="learn routing")
        assert r2.ok and r2.goal_id == "g1"
        r3 = goal(str(tmp_path), "status")
        assert any(g["id"] == "g1" for g in r3.goals)

    def test_research_then_explore(self, tmp_path: Path) -> None:
        (tmp_path / "app.py").write_text("print('hello')", encoding="utf-8")
        r1 = research(str(tmp_path), "python basics")
        assert r1.ok
        r2 = explore(str(tmp_path), ".")
        assert r2.ok and "files" in r2.structure

    def test_execute_learns(self, tmp_path: Path) -> None:
        r = execute(str(tmp_path), f'"{sys.executable}" -c "print(\'done\')"')
        assert r.ok
        assert r.learned != ""

    def test_navigate_full_flow(self, tmp_path: Path) -> None:
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "f.txt").write_text("content here", encoding="utf-8")
        r1 = navigate(str(tmp_path), "read", path="sub/f.txt")
        assert "content" in r1.content
        r2 = navigate(str(tmp_path), "map", path=".", depth=1)
        assert r2.ok

    def test_session_lifecycle(self, tmp_path: Path) -> None:
        session(str(tmp_path), "create", session_id="e2e", focus="integration")
        r = session(str(tmp_path), "summarize", session_id="e2e")
        assert "e2e" in r.summary

    def test_progress_with_goals(self, tmp_path: Path) -> None:
        items = [
            {"content": "step 1", "status": "completed"},
            {"content": "step 2", "status": "pending"},
        ]
        r = progress(str(tmp_path), "write", items=items)
        assert "\u2588" in r.bars

    def test_dashboard_shows_goals(self, tmp_path: Path) -> None:
        goal(str(tmp_path), "set", goal_id="g1", objective="obj1")
        r = goal(str(tmp_path), "status")
        assert len(r.goals) == 1
        assert r.goals[0]["objective"] == "obj1"

    def test_footer_shows_progress(self, tmp_path: Path) -> None:
        items = [{"content": "task", "status": "in_progress"}]
        r = progress(str(tmp_path), "write", items=items)
        assert "50%" in r.bars or "task" in r.bars

    def test_bridge_agent_commands(self, tmp_path: Path) -> None:
        """Bridge now exposes observe/goal/research/etc. commands."""
        bridge_path = Path(__file__).parent.parent.parent / "school" / "bridge.py"
        proc = subprocess.run(
            [sys.executable, str(bridge_path)],
            input=json.dumps({
                "command": "observe",
                "worktree": str(tmp_path),
                "observation": "test",
            }),
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert proc.returncode == 0
        result = json.loads(proc.stdout)
        assert result.get("ok") is True

    def test_all_imports_work(self) -> None:
        """All 8 agent tool modules import cleanly."""
        from core.agent import (
            execute,
            explore,
            goal,
            navigate,
            observe,
            progress,
            research,
            session,
        )
        assert all(
            callable(f)
            for f in [observe, goal, research, explore, progress, session, execute, navigate]
        )
