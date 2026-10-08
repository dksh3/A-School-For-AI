"""S7 tests: school_workflow."""

from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from core.agent.workflows import BUILTINS, workflow


@pytest.fixture
def worktree() -> Iterator[str]:
    """Isolated worktree via tempfile.mkdtemp (not tmp_path: OneDrive-safe)."""
    wt = tempfile.mkdtemp(prefix="school_wf_")
    try:
        yield wt
    finally:
        shutil.rmtree(wt, ignore_errors=True)


def _state(wt: str) -> dict[str, object]:
    path = Path(wt) / ".school" / "agent" / "workflows.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _only_run(wt: str) -> dict[str, object]:
    runs = _state(wt)
    assert len(runs) == 1
    return next(iter(runs.values()))  # type: ignore[return-value]


class TestWorkflowStart:
    @pytest.mark.parametrize(
        ("name", "first"),
        [
            ("tdd", "red"),
            ("debug", "reproduce"),
            ("brainstorm", "diverge"),
            ("review", "read"),
        ],
    )
    def test_start_builtin_first_phase(
        self, worktree: str, name: str, first: str
    ) -> None:
        r = workflow(worktree, name)
        assert r.ok is True
        assert r.phase == first
        assert r.state == "running"
        assert r.guidance
        assert r.phases == []

    def test_builtin_definitions(self) -> None:
        assert set(BUILTINS) == {"tdd", "debug", "brainstorm", "review"}
        assert BUILTINS["tdd"] == ["red", "green", "refactor", "commit"]

    def test_start_at_named_phase(self, worktree: str) -> None:
        r = workflow(worktree, "tdd", action="start", phase="refactor")
        assert r.ok is True
        assert r.phase == "refactor"


class TestWorkflowLifecycle:
    def test_advance_tdd_to_complete(self, worktree: str) -> None:
        r = workflow(worktree, "tdd")
        assert r.phase == "red"
        r = workflow(worktree, "tdd", action="advance", notes="failing test written")
        assert r.phase == "green"
        assert r.state == "running"
        r = workflow(worktree, "tdd", action="advance")
        assert r.phase == "refactor"
        r = workflow(worktree, "tdd", action="advance")
        assert r.phase == "commit"
        r = workflow(worktree, "tdd", action="advance")
        assert r.state == "complete"
        assert r.phase == ""
        assert [p["name"] for p in r.phases] == ["red", "green", "refactor", "commit"]
        assert all(p["status"] == "done" for p in r.phases)
        assert all(p["duration_ms"] >= 0 for p in r.phases)

    def test_status_shows_progress(self, worktree: str) -> None:
        workflow(worktree, "tdd")
        workflow(worktree, "tdd", action="advance")
        r = workflow(worktree, "tdd", action="status")
        assert r.ok is True
        assert r.phase == "green"
        assert r.state == "running"
        assert [p["name"] for p in r.phases] == ["red"]
        assert r.phases[0]["duration_ms"] >= 0

    def test_status_before_start(self, worktree: str) -> None:
        r = workflow(worktree, "tdd", action="status")
        assert r.ok is True
        assert r.phase == ""
        assert r.phases == []

    def test_abort_marks_aborted(self, worktree: str) -> None:
        workflow(worktree, "debug")
        workflow(worktree, "debug", action="advance")
        r = workflow(worktree, "debug", action="abort")
        assert r.ok is True
        assert r.state == "aborted"
        assert r.phase == "isolate"
        assert _only_run(worktree)["state"] == "aborted"

    def test_block_marks_blocked(self, worktree: str) -> None:
        workflow(worktree, "tdd")
        r = workflow(worktree, "tdd", action="block", notes="need the API key")
        assert r.state == "blocked"
        assert _only_run(worktree)["state"] == "blocked"

    def test_advance_when_complete(self, worktree: str) -> None:
        workflow(worktree, "tdd")
        for _ in range(4):
            workflow(worktree, "tdd", action="advance")
        r = workflow(worktree, "tdd", action="advance")
        assert r.ok is False
        assert r.error == "workflow already complete"

    def test_advance_without_start(self, worktree: str) -> None:
        r = workflow(worktree, "tdd", action="advance")
        assert r.ok is False
        assert r.error is not None


class TestWorkflowErrors:
    def test_unknown_workflow(self, worktree: str) -> None:
        r = workflow(worktree, "bogus")
        assert r.ok is False
        assert r.error == "unknown workflow: bogus"

    def test_unknown_action(self, worktree: str) -> None:
        r = workflow(worktree, "tdd", action="bogus")
        assert r.ok is False
        assert r.error == "unknown action: bogus"

    def test_kill_switch(self, worktree: str, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SCHOOL_WORKFLOW", "0")
        r = workflow(worktree, "tdd")
        assert r.ok is True
        assert r.workflow == "tdd"
        assert r.phase == ""
        assert r.phases == []
        assert r.guidance == "workflow disabled"
        assert r.state == "disabled"


class TestWorkflowList:
    def test_list_returns_builtins(self, worktree: str) -> None:
        r = workflow(worktree, "tdd", action="list")
        assert r.ok is True
        names = [p["name"] for p in r.phases]
        for expected in ("tdd", "debug", "brainstorm", "review"):
            assert expected in names
            assert expected in r.guidance


class TestWorkflowCustom:
    def test_define_and_run_custom(self, worktree: str) -> None:
        r = workflow(worktree, "deploy", action="define", phase="build, test, ship")
        assert r.ok is True
        r = workflow(worktree, "deploy", action="start")
        assert r.ok is True
        assert r.phase == "build"
        r = workflow(worktree, "deploy", action="list")
        assert "deploy" in r.guidance

    def test_register_workflow(self, worktree: str) -> None:
        from core.agent.workflows import register_workflow

        assert register_workflow("release", ["tag", "publish"]) is True
        assert register_workflow("", ["x"]) is False
        r = workflow(worktree, "release", action="start")
        assert r.phase == "tag"


class TestWorkflowPersistence:
    def test_state_survives_second_call(self, worktree: str) -> None:
        workflow(worktree, "tdd")
        workflow(worktree, "tdd", action="advance", notes="red done")
        # second "call": fresh status read from disk
        r = workflow(worktree, "tdd", action="status")
        assert r.phase == "green"
        assert [p["name"] for p in r.phases] == ["red"]

    def test_notes_recorded_in_phase_entries(self, worktree: str) -> None:
        workflow(worktree, "tdd")
        workflow(worktree, "tdd", action="advance", notes="wrote the failing test")
        run = _only_run(worktree)
        phases = run["phases"]  # type: ignore[index]
        assert phases[0]["name"] == "red"  # type: ignore[index]
        assert phases[0]["notes"] == "wrote the failing test"  # type: ignore[index]
        assert phases[0]["status"] == "done"  # type: ignore[index]
        assert phases[0]["duration_ms"] >= 0  # type: ignore[index]

    def test_phase_durations_recorded(self, worktree: str) -> None:
        workflow(worktree, "review")
        for _ in range(4):
            workflow(worktree, "review", action="advance")
        run = _only_run(worktree)
        phases = run["phases"]  # type: ignore[index]
        assert all(p["duration_ms"] >= 0 for p in phases)  # type: ignore[index]
        assert run["finished_at"] != ""  # type: ignore[index]

    def test_history_note_in_guidance(self, worktree: str) -> None:
        workflow(worktree, "tdd")
        for _ in range(4):
            workflow(worktree, "tdd", action="advance")
        r = workflow(worktree, "tdd", action="start")
        assert "run history" in r.guidance
        assert "1 complete" in r.guidance
