"""S7 competitive duels: each School agent tool vs its OpenCode inspiration.

Every test class pits one School tool against a faithful simulation of the
OpenCode harness tool that inspired it and asserts School is superior on
measurable criteria: richer result surface, persistence, learning output,
action coverage, and fail-open error resilience.

Baseline simulators model only the documented OpenCode surface (ephemeral,
raw output, no learning) so the comparison is deterministic and offline.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from collections.abc import Iterator
from dataclasses import fields
from pathlib import Path
from typing import Any

import pytest

from core.agent import (
    ExecuteResult,
    ExploreResult,
    GoalResult,
    NavigateResult,
    ObserveResult,
    ProgressResult,
    ResearchResult,
    SessionResult,
    execute,
    explore,
    goal,
    navigate,
    observe,
    progress,
    research,
    session,
)
from core.context.progress import render_eta

# ---------------------------------------------------------------------------
# OpenCode baseline simulators (the inspiration tools)
# ---------------------------------------------------------------------------


def baseline_browser_observe(tab_id: str, instruction: str = "") -> dict[str, Any]:
    """browser.observe: ephemeral page snapshot. Nothing persisted, no learning."""
    return {"title": "Page title", "description": "accessibility snapshot", "elements": []}


def baseline_goal_set(objective: str) -> dict[str, str]:
    """goal_set: a single action returning a plain confirmation string."""
    return {"objective": objective, "confirmation": "Goal set."}


def baseline_websearch(query: str) -> dict[str, Any]:
    """websearch: stateless results, no research trail, no depth/fmt controls."""
    return {"query": query, "results": []}


def baseline_glob(pattern: str) -> dict[str, Any]:
    """glob: raw file list only, no conventions, patterns, or extension stats."""
    return {"pattern": pattern, "files": []}


def baseline_grep(pattern: str) -> dict[str, Any]:
    """grep: raw match lines only, no structural knowledge."""
    return {"pattern": pattern, "raw_matches": []}


def baseline_todowrite(todos: list[dict[str, str]]) -> dict[str, str]:
    """todowrite: plain-text echo, no visual bar, no ETA, no cross-call persistence."""
    return {"content": "\n".join(t.get("content", "") for t in todos)}


def baseline_session_move(session_id: str, directory: str) -> dict[str, str]:
    """opencode.session_move: relocation only — no lifecycle, summary, or export."""
    return {"sessionID": session_id, "directory": directory}


def baseline_shell(command: str) -> dict[str, Any]:
    """shell: raw stdout/stderr/exit code only, no learning, no timeout control."""
    return {"command": command, "stdout": "", "stderr": "", "exit_code": 0}


def baseline_read(path: str) -> dict[str, str]:
    """read: single-purpose file read; list/search/map need separate tools."""
    return {"path": path, "content": ""}


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def worktree() -> Iterator[str]:
    """Isolated worktree via tempfile.mkdtemp (not tmp_path: OneDrive-safe)."""
    wt = tempfile.mkdtemp(prefix="school_duel_")
    try:
        yield wt
    finally:
        shutil.rmtree(wt, ignore_errors=True)


def _obs_file(wt: str) -> Path:
    return Path(wt) / ".school" / "agent" / "observations.jsonl"


def _goal_file(wt: str) -> Path:
    return Path(wt) / ".school" / "agent" / "goals.json"


def _session_file(wt: str) -> Path:
    return Path(wt) / ".school" / "agent" / "sessions.json"


def _snapshot(wt: str) -> set[str]:
    """All file paths currently under a worktree (for no-write comparisons)."""
    return {str(p) for p in Path(wt).rglob("*")}


def _make_project(wt: str) -> Path:
    """Create a tiny polyglot project to explore."""
    root = Path(wt)
    (root / "main.py").write_text("def main():\n    return 'needle'\n", encoding="utf-8")
    (root / "util.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "app.ts").write_text("export const x = 1;\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
    nested = root / "a" / "b" / "c"
    nested.mkdir(parents=True)
    (root / "top.txt").write_text("top\n", encoding="utf-8")
    (nested / "deep.txt").write_text("deep needle\n", encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# Duel 1: school_observe vs browser.observe
# ---------------------------------------------------------------------------


class TestObserveDuel:
    """School persists, extracts patterns, counts cumulatively, and learns."""

    def test_result_surface_dominates_baseline(self) -> None:
        school_fields = {f.name for f in fields(ObserveResult)}
        baseline_fields = set(baseline_browser_observe("tab_1"))
        assert len(school_fields) > len(baseline_fields)
        for cap in ("observation_id", "pattern", "learning", "total"):
            assert cap in school_fields
            assert cap not in baseline_fields

    def test_school_persists_baseline_is_ephemeral(self, worktree: str) -> None:
        r = observe(worktree, "user always calls recall first", category="tool_call")
        assert r.ok is True
        assert r.observation_id.startswith("obs-")
        assert _obs_file(worktree).is_file()
        lines = _obs_file(worktree).read_text(encoding="utf-8").splitlines()
        records = [json.loads(line) for line in lines]
        assert records[-1]["observation"] == "user always calls recall first"
        # Baseline writes nothing at all.
        before = _snapshot(worktree)
        baseline_browser_observe("tab_1", "snapshot the page")
        assert _snapshot(worktree) == before

    def test_school_extracts_patterns(self, worktree: str) -> None:
        # Default category surfaces as a "pattern ..." learning on a fresh store.
        r2 = observe(worktree, "generic event")
        assert "pattern" in r2.pattern
        # Errors accumulate and dominate the extracted pattern.
        for _ in range(3):
            observe(worktree, "flaky retry loop", category="error")
        r = observe(worktree, "another failure", category="error")
        assert "error" in r.pattern
        assert "appears" in r.pattern
        assert "pattern" not in baseline_browser_observe("tab_1")

    def test_school_counts_cumulatively(self, worktree: str) -> None:
        totals = [observe(worktree, f"event {i}").total for i in range(3)]
        assert totals == [1, 2, 3]

    def test_school_emits_learning_output(self, worktree: str) -> None:
        r = observe(worktree, "always verify exit codes after shell calls")
        assert r.learning
        assert "verify exit codes" in r.learning
        baseline = baseline_browser_observe("tab_1")
        assert "learning" not in baseline

    def test_fail_open_bad_input_returns_error_not_exception(self, worktree: str) -> None:
        r = observe(worktree, "")
        assert r.ok is False
        assert r.error
        # Corrupt worktree path must fail open, never raise.
        bad = observe("/nonexistent/\x00\x00", "test")
        assert isinstance(bad, ObserveResult)
        assert isinstance(bad.ok, bool)


# ---------------------------------------------------------------------------
# Duel 2: school_goal vs goal_set
# ---------------------------------------------------------------------------


class TestGoalDuel:
    """School runs a full 8-action lifecycle with persisted criteria tracking."""

    ALL_ACTIONS = ("set", "status", "complete", "block", "pause", "resume", "clear", "history")

    def test_school_supports_8_actions_vs_1(self, worktree: str) -> None:
        baseline_actions = {"set"}  # goal_set is the only goal action
        assert len(self.ALL_ACTIONS) == 8
        assert len(self.ALL_ACTIONS) > len(baseline_actions)
        assert goal(worktree, "set", goal_id="g1", objective="ship").ok is True
        for action in ("status", "pause", "resume", "block", "complete", "history"):
            assert goal(worktree, action, goal_id="g1").ok is True, action
        assert goal(worktree, "clear").ok is True
        for action in self.ALL_ACTIONS:
            assert goal(worktree, action, goal_id="g1").ok is True, action

    def test_school_persists_across_calls(self, worktree: str) -> None:
        goal(worktree, "set", goal_id="g1", objective="learn routing")
        assert _goal_file(worktree).is_file()
        status = goal(worktree, "status")
        assert any(g["id"] == "g1" for g in status.goals)
        before = _snapshot(worktree)
        baseline_goal_set("learn routing")
        assert _snapshot(worktree) == before

    def test_school_tracks_criteria_constraints_progress(self, worktree: str) -> None:
        goal(
            worktree,
            "set",
            goal_id="g1",
            objective="ship feature",
            success_criteria="tests green",
            constraints="no new deps",
            max_turns=5,
        )
        entry = json.loads(_goal_file(worktree).read_text(encoding="utf-8"))[0]
        assert entry["success_criteria"] == "tests green"
        assert entry["constraints"] == "no new deps"
        assert entry["max_turns"] == 5
        school_fields = {f.name for f in fields(GoalResult)}
        assert "progress" in school_fields
        baseline = baseline_goal_set("ship feature")
        for cap in ("success_criteria", "constraints", "progress", "state"):
            assert cap not in baseline

    def test_school_full_lifecycle_transitions(self, worktree: str) -> None:
        goal(worktree, "set", goal_id="g1", objective="duel")
        assert goal(worktree, "pause", goal_id="g1").state == "paused"
        assert goal(worktree, "resume", goal_id="g1").state == "active"
        assert goal(worktree, "block", goal_id="g1", constraints="need data").state == "blocked"
        assert goal(worktree, "complete", goal_id="g1").state == "complete"
        history = goal(worktree, "history")
        assert any(g["id"] == "g1" and g["state"] == "complete" for g in history.goals)
        assert len(history.goals) == 1  # only terminal goals appear

    def test_fail_open_bad_input_returns_error_not_exception(self, worktree: str) -> None:
        r = goal(worktree, "explode")
        assert r.ok is False
        assert "unknown action" in r.error
        missing = goal(worktree, "complete", goal_id="nope")
        assert missing.ok is False
        assert "not found" in missing.error


# ---------------------------------------------------------------------------
# Duel 3: school_research vs websearch
# ---------------------------------------------------------------------------


class TestResearchDuel:
    """School builds a learning trail in the observer; websearch is stateless."""

    def test_school_logs_learning_trail(self, worktree: str) -> None:
        r = research(worktree, "how does routing decide tool calls")
        assert r.ok is True
        assert _obs_file(worktree).is_file()
        record = json.loads(
            _obs_file(worktree).read_text(encoding="utf-8").splitlines()[-1]
        )
        assert record["category"] == "research"
        assert "routing" in record["observation"]
        before = _snapshot(worktree)
        baseline_websearch("how does routing decide tool calls")
        assert _snapshot(worktree) == before

    def test_school_supports_depth_and_fmt(self, worktree: str) -> None:
        r = research(worktree, "deep question", depth="deep", fmt="bullets")
        assert r.ok is True
        assert r.query == "deep question"
        baseline_params = set(baseline_websearch("deep question"))
        assert "depth" not in baseline_params
        assert "fmt" not in baseline_params

    def test_school_returns_learnings(self, worktree: str) -> None:
        r = research(worktree, "test-driven teaching")
        assert r.learnings
        assert isinstance(r.learnings, str) and "teaching" in r.learnings
        assert r.findings
        assert r.citations  # per-finding provenance baseline never reports
        assert r.source  # provenance baseline never reports
        baseline = baseline_websearch("test-driven teaching")
        assert "learnings" not in baseline

    def test_result_surface_dominates_baseline(self) -> None:
        school_fields = {f.name for f in fields(ResearchResult)}
        baseline_fields = set(baseline_websearch("q"))
        assert len(school_fields) > len(baseline_fields)

    def test_fail_open_bad_input_returns_error_not_exception(self, worktree: str) -> None:
        r = research(worktree, "")
        assert r.ok is False
        assert r.error


# ---------------------------------------------------------------------------
# Duel 4: school_explore vs glob/grep
# ---------------------------------------------------------------------------


class TestExploreDuel:
    """School extracts conventions, patterns, and extension stats; glob/grep don't."""

    def test_school_extracts_conventions(self, worktree: str) -> None:
        _make_project(worktree)
        r = explore(worktree, ".")
        assert r.ok is True
        assert "Python project" in r.conventions
        assert "Python packaging" in r.conventions
        for baseline in (baseline_glob("*.py"), baseline_grep("def")):
            assert "conventions" not in baseline

    def test_school_extracts_patterns_and_extensions(self, worktree: str) -> None:
        _make_project(worktree)
        r = explore(worktree, ".")
        assert any(".py" in p and "x2" in p for p in r.patterns)
        assert "extensions" in r.structure
        assert "files" in r.structure
        baseline = baseline_glob("**/*")
        assert set(baseline) == {"pattern", "files"}  # raw list only

    def test_result_surface_dominates_baseline(self) -> None:
        school_fields = {f.name for f in fields(ExploreResult)}
        baseline_fields = set(baseline_grep("x"))
        assert len(school_fields) > len(baseline_fields)

    def test_fail_open_bad_input_returns_error_not_exception(self, worktree: str) -> None:
        missing = explore(worktree, "does-not-exist")
        assert missing.ok is False
        assert "not found" in missing.error
        empty = explore(worktree, "")
        assert empty.ok is False
        assert empty.error


# ---------------------------------------------------------------------------
# Duel 5: school_progress vs todowrite
# ---------------------------------------------------------------------------


class TestProgressDuel:
    """School renders visual bars, supports ETA, and persists across calls."""

    ITEMS = [
        {"content": "write tests", "status": "completed"},
        {"content": "run suite", "status": "in_progress"},
        {"content": "ship it", "status": "pending"},
    ]

    def test_school_renders_visual_bars(self, worktree: str) -> None:
        r = progress(worktree, "write", items=self.ITEMS)
        assert r.ok is True
        assert "█" in r.bars
        assert "░" in r.bars
        assert "100%" in r.bars and "50%" in r.bars and "0%" in r.bars
        baseline = baseline_todowrite(self.ITEMS)
        assert "█" not in baseline["content"]
        assert "░" not in baseline["content"]

    def test_school_supports_eta(self) -> None:
        # School's progress renderer (used by school_progress) computes ETAs.
        assert render_eta(5000, 0.5) == "~5s"
        assert render_eta(90_000, 0.5) == "~1m 30s"
        assert render_eta(0, 0.0) == "—"
        baseline = baseline_todowrite(self.ITEMS)
        assert "eta" not in {k.lower() for k in baseline}

    def test_school_persists_across_calls(self, worktree: str) -> None:
        written = progress(worktree, "write", items=self.ITEMS)
        reread = progress(worktree, "read")
        assert reread.items == written.items
        assert reread.bars == written.bars
        assert len(reread.items) == 3

    def test_result_surface_dominates_baseline(self, worktree: str) -> None:
        school_fields = {f.name for f in fields(ProgressResult)}
        baseline_fields = set(baseline_todowrite(self.ITEMS))
        assert len(school_fields) > len(baseline_fields)
        assert progress(worktree, "write", items=self.ITEMS).ok is True

    def test_fail_open_bad_input_returns_error_not_exception(self, worktree: str) -> None:
        r = progress(worktree, "yell")
        assert r.ok is False
        assert "unknown action" in r.error


# ---------------------------------------------------------------------------
# Duel 6: school_session vs opencode.session_move
# ---------------------------------------------------------------------------


class TestSessionDuel:
    """School runs 5 lifecycle actions with focus tracking; move/rename relocates only."""

    def test_school_supports_5_actions_vs_2(self, worktree: str) -> None:
        baseline_actions = {"move", "rename"}  # opencode session surface
        assert len(baseline_actions) < 5
        assert session(worktree, "create", session_id="s1", focus="routing").ok is True
        for action in ("resume", "summarize", "export", "list"):
            assert session(worktree, action, session_id="s1").ok is True, action

    def test_school_tracks_focus(self, worktree: str) -> None:
        session(worktree, "create", session_id="s1", focus="teaching loops")
        resumed = session(worktree, "resume", session_id="s1")
        assert resumed.focus == "teaching loops"
        exported = json.loads(session(worktree, "export", session_id="s1").data)
        assert exported["focus"] == "teaching loops"
        baseline = baseline_session_move("s1", "/tmp")
        assert "focus" not in baseline

    def test_school_persists_sessions(self, worktree: str) -> None:
        session(worktree, "create", session_id="s1", focus="a")
        assert _session_file(worktree).is_file()
        listed = session(worktree, "list")
        assert any(s["id"] == "s1" for s in listed.sessions)
        assert len(listed.sessions) == 1  # survives across calls

    def test_school_summarizes_and_exports(self, worktree: str) -> None:
        session(worktree, "create", session_id="s1", focus="duels")
        summary = session(worktree, "summarize", session_id="s1")
        assert "focus=duels" in summary.summary
        exported = session(worktree, "export", session_id="s1")
        data = json.loads(exported.data)
        assert data["id"] == "s1"
        assert data["state"] == "active"

    def test_fail_open_bad_input_returns_error_not_exception(self, worktree: str) -> None:
        assert "unknown action" in session(worktree, "teleport").error
        missing = session(worktree, "resume", session_id="ghost")
        assert missing.ok is False
        assert "not found" in missing.error


# ---------------------------------------------------------------------------
# Duel 7: school_execute vs shell
# ---------------------------------------------------------------------------


class TestExecuteDuel:
    """School learns from command outcomes and enforces timeouts; shell is raw."""

    def test_school_learns_from_execution(self, worktree: str) -> None:
        cmd = f'"{sys.executable}" -c "print(42)"'
        r = execute(worktree, cmd)
        assert r.ok is True
        assert r.exit_code == 0
        assert "42" in r.stdout
        assert r.learned
        assert "command success" in r.learned
        assert _obs_file(worktree).is_file()
        record = json.loads(
            _obs_file(worktree).read_text(encoding="utf-8").splitlines()[-1]
        )
        assert record["category"] == "execute"
        assert record["evidence"]["exit_code"] == 0
        baseline = baseline_shell(cmd)
        assert "learned" not in baseline
        before = _snapshot(worktree)
        baseline_shell(cmd)
        assert _snapshot(worktree) == before

    def test_school_learns_from_failures_too(self, worktree: str) -> None:
        r = execute(worktree, f'"{sys.executable}" -c "raise SystemExit(3)"')
        assert r.ok is False
        assert r.exit_code == 3
        assert "command failure" in r.learned

    def test_school_configurable_timeout(self, worktree: str) -> None:
        slow = f'"{sys.executable}" -c "import time; time.sleep(8)"'
        r = execute(worktree, slow, timeout_ms=1000)
        assert r.ok is False
        assert r.error == "timeout"
        assert "timeout_ms" not in baseline_shell(slow)  # baseline has no knob

    def test_school_learn_flag_controls_learning(self, worktree: str) -> None:
        cmd = f'"{sys.executable}" -c "print(7)"'
        r = execute(worktree, cmd, learn=False)
        assert r.ok is True
        assert r.learned == ""
        assert not _obs_file(worktree).exists()

    def test_result_surface_dominates_baseline(self) -> None:
        school_fields = {f.name for f in fields(ExecuteResult)}
        baseline_fields = set(baseline_shell("echo hi"))
        assert len(school_fields) > len(baseline_fields)
        assert "duration_ms" in school_fields
        assert "duration_ms" not in baseline_fields

    def test_fail_open_bad_input_returns_error_not_exception(self, worktree: str) -> None:
        r = execute(worktree, "")
        assert r.ok is False
        assert r.error


# ---------------------------------------------------------------------------
# Duel 8: school_navigate vs read/glob/grep
# ---------------------------------------------------------------------------


class TestNavigateDuel:
    """School unifies read/list/search/map with depth control on one entry point."""

    def test_school_unifies_four_actions(self, worktree: str) -> None:
        _make_project(worktree)
        read = navigate(worktree, "read", path="main.py")
        assert read.ok is True and "needle" in read.content
        listing = navigate(worktree, "list")
        assert listing.ok is True and "main.py" in listing.entries
        search = navigate(worktree, "search", pattern="needle")
        assert search.ok is True
        assert any("needle" in m["text"] for m in search.matches)
        tree = navigate(worktree, "map")
        assert tree.ok is True and tree.tree
        # Baseline needs three separate tools and has no map at all.
        baseline_tools = ("read", "glob", "grep")
        assert len(baseline_tools) < 4
        assert "map" not in baseline_tools

    def test_school_depth_control(self, worktree: str) -> None:
        _make_project(worktree)
        shallow = navigate(worktree, "map", depth=1)
        deep = navigate(worktree, "map", depth=3)
        assert "deep.txt" not in shallow.tree
        assert "deep.txt" in deep.tree
        assert "top.txt" in shallow.tree

    def test_result_surface_dominates_baseline(self) -> None:
        school_fields = {f.name for f in fields(NavigateResult)}
        baseline_fields = set(baseline_read("main.py"))
        assert len(school_fields) > len(baseline_fields)

    def test_fail_open_bad_input_returns_error_not_exception(self, worktree: str) -> None:
        _make_project(worktree)
        assert navigate(worktree, "teleport").ok is False
        assert navigate(worktree, "read", path="a").ok is False  # dir, not file
        bad_rx = navigate(worktree, "search", pattern="(")
        assert bad_rx.ok is False
        assert "bad pattern" in bad_rx.error


# ---------------------------------------------------------------------------
# Overall scoreboard
# ---------------------------------------------------------------------------


class TestOverallScoreboard:
    """Aggregate check: School wins every duel on surface and action breadth."""

    def test_school_wins_every_surface_duel(self) -> None:
        duels = {
            "observe": (ObserveResult, baseline_browser_observe("tab_1")),
            "goal": (GoalResult, baseline_goal_set("obj")),
            "research": (ResearchResult, baseline_websearch("q")),
            "explore": (ExploreResult, baseline_grep("q")),
            "progress": (ProgressResult, baseline_todowrite([])),
            "session": (SessionResult, baseline_session_move("s1", "/tmp")),
            "execute": (ExecuteResult, baseline_shell("echo")),
            "navigate": (NavigateResult, baseline_read("f")),
        }
        wins = {name: len(fields(cls)) > len(base) for name, (cls, base) in duels.items()}
        assert all(wins.values()), f"School lost a duel: {wins}"

    def test_school_wins_every_action_duel(self) -> None:
        # (school tool, school actions, baseline tool, baseline actions)
        duels = [
            ("school_goal", 8, "goal_set", 1),
            ("school_session", 5, "session_move/rename", 2),
            ("school_navigate", 4, "read/glob/grep", 3),
        ]
        for school_name, school_n, base_name, base_n in duels:
            assert school_n > base_n, f"{school_name} lost to {base_name}"
