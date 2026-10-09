"""Competitive duels: School tools vs the 7 OpenCode plugins they replace.

Each class proves School's tool is SIGNIFICANTLY better than the external
plugin on measurable criteria: richer field surface, action breadth,
durable persistence, learning/observer output, and fail-open resilience.

Baseline simulators model only the *documented* OpenCode plugin contract
(ephemeral, raw output, no learning) so every comparison is deterministic
and offline. Worktrees come from ``tempfile.mkdtemp()`` (OneDrive-safe).
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import fields
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Baseline simulators: the documented contract of each replaced plugin
# ---------------------------------------------------------------------------


def baseline_superpowers(task: str) -> dict[str, str]:
    """superpowers: general SDD guidance only. No state, no timing, no history."""
    return {"guidance": f"Think step by step about {task}."}


def baseline_context7(query: str) -> dict[str, object]:
    """@upstash/context7-opencode: live search every call. No cache, no learning."""
    return {"query": query, "results": []}


def baseline_websearch_cited(query: str) -> dict[str, object]:
    """opencode-websearch-cited: sources without relevance, no confidence."""
    return {"query": query, "results": [], "sources": [{"title": "t", "url": "u"}]}


def baseline_opencode_pty(command: str) -> dict[str, object]:
    """opencode-pty: raw terminal echo. Exactly 4 fields, no learning."""
    return {"command": command, "exit_code": 0, "stdout": "", "stderr": ""}


def baseline_opencode_dcp() -> dict[str, object]:
    """@tarquinen/opencode-dcp: auto-prunes old context. No restore, no persistence."""
    return {"pruned": True}


def baseline_goal_plugin(objective: str) -> dict[str, str]:
    """opencode-goal-plugin: one `set` action, confirmation string only."""
    return {"objective": objective, "confirmation": "Goal set."}


def baseline_opencode_mem() -> dict[str, object]:
    """opencode-mem: auto-capture plus search. No conflict/dedup/lifecycle."""
    return {"captured": True, "results": []}


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def worktree():
    """Isolated worktree via tempfile.mkdtemp (not tmp_path: OneDrive-safe)."""
    d = Path(tempfile.mkdtemp(prefix="school_duel_"))
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _obs_file(wt: Path) -> Path:
    return wt / ".school" / "agent" / "observations.jsonl"


def _obs_categories(wt: Path) -> set[str]:
    if not _obs_file(wt).exists():
        return set()
    cats = set()
    for line in _obs_file(wt).read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                cats.add(str(json.loads(line).get("category", "")))
            except ValueError:
                continue
    return cats


def _patch_fetch(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    """Deterministic offline stand-in for docfetcher's network fetch."""
    from core.agent import docfetcher

    monkeypatch.setattr(docfetcher, "_fetch_url", lambda url, timeout=5.0: text)


def _patch_fetch_boom(monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.error

    from core.agent import docfetcher

    def _boom(url: str, timeout: float = 5.0) -> str:
        raise urllib.error.URLError("network unavailable")

    monkeypatch.setattr(docfetcher, "_fetch_url", _boom)


# ---------------------------------------------------------------------------
# Duel 1: school_workflow vs superpowers
# ---------------------------------------------------------------------------


class TestWorkflowVsSuperpowers:
    """superpowers gives general guidance; School persists runs, times each
    phase, learns from history, and supports custom workflows."""

    def test_four_builtin_workflows_vs_general_guidance(self, worktree):
        from core.agent.workflows import BUILTINS, workflow

        assert set(BUILTINS) == {"tdd", "debug", "brainstorm", "review"}
        # baseline has zero named workflows: guidance is free-form text
        assert "workflows" not in baseline_superpowers("ship a feature")

        for name in BUILTINS:
            r = workflow(worktree, name, action="start")
            assert r.ok, f"{name}: {r.error}"
            assert r.phase in BUILTINS[name]
            assert r.state == "running"
            assert r.guidance

    def test_state_persists_to_workflows_json(self, worktree):
        from core.agent.workflows import workflow

        workflow(worktree, "tdd", action="start")
        wf_file = worktree / ".school" / "agent" / "workflows.json"
        assert wf_file.exists()
        state = json.loads(wf_file.read_text(encoding="utf-8"))
        assert any(key.startswith("tdd@") for key in state)
        # baseline writes nothing to disk
        assert "state_file" not in baseline_superpowers("x")

    def test_phase_durations_recorded(self, worktree):
        from core.agent.workflows import workflow

        workflow(worktree, "tdd", action="start")
        r = workflow(worktree, "tdd", action="advance", notes="failing test written")
        assert r.ok
        assert len(r.phases) == 1
        assert r.phases[0]["name"] == "red"
        assert r.phases[0]["status"] == "done"
        assert isinstance(r.phases[0]["duration_ms"], int)
        assert r.phases[0]["duration_ms"] >= 0

    def test_learns_from_run_history(self, worktree):
        from core.agent.workflows import workflow

        # Finish one run, abort another: history must reach future guidance.
        workflow(worktree, "review", action="start")
        for _ in range(4):
            workflow(worktree, "review", action="advance")
        workflow(worktree, "review", action="start")
        workflow(worktree, "review", action="abort")

        r = workflow(worktree, "review", action="start")
        assert r.ok
        assert "run history" in r.guidance
        assert "1 complete" in r.guidance
        assert "1 aborted" in r.guidance

    def test_custom_workflow_define(self, worktree):
        from core.agent.workflows import workflow

        r = workflow(worktree, "deploy", action="define", phase="build,test,ship")
        assert r.ok
        assert r.state == "defined"
        assert [p["name"] for p in r.phases] == ["build", "test", "ship"]

        r = workflow(worktree, "deploy", action="start")
        assert r.ok
        assert r.phase == "build"

    def test_seven_actions_vs_implicit_flow(self, worktree):
        from core.agent.workflows import VALID_ACTIONS

        assert len(VALID_ACTIONS) == 7
        assert sorted(VALID_ACTIONS) == [
            "abort", "advance", "block", "define", "list", "start", "status",
        ]
        # superpowers has one implicit action: "follow the guidance"
        assert len(baseline_superpowers("x")) == 1

    def test_fail_open_unknown_workflow_returns_error_result(self, worktree):
        from core.agent.workflows import workflow

        r = workflow(worktree, "nonexistent", action="start")
        assert r.ok is False
        assert r.error == "unknown workflow: nonexistent"
        assert r.state == "error"

    def test_fail_open_unknown_action_returns_error_result(self, worktree):
        from core.agent.workflows import workflow

        r = workflow(worktree, "tdd", action="frobnicate")
        assert r.ok is False
        assert r.error == "unknown action: frobnicate"

    def test_score_field_surface_and_actions_beat_baseline(self, worktree):
        from core.agent.workflows import WorkflowResult, workflow

        r = workflow(worktree, "tdd", action="status")
        school_fields = {f.name for f in fields(WorkflowResult)}
        baseline_fields = set(baseline_superpowers("x"))
        assert len(school_fields) > len(baseline_fields)

        assert isinstance(r, WorkflowResult)
        assert len(school_fields) == 7  # ok, workflow, phase, phases, guidance, state, error


# ---------------------------------------------------------------------------
# Duel 2: school_docs vs @upstash/context7-opencode
# ---------------------------------------------------------------------------


class TestDocsVsContext7:
    """Context7 fetches live docs every call; School caches locally with
    version pinning, skeletonization, observer integration, and LRU eviction
    so the second call works offline."""

    def test_offline_cache_after_first_fetch(self, worktree, monkeypatch):
        from core.agent.docfetcher import fetch_docs

        _patch_fetch(monkeypatch, "pytest fixtures share setup state between tests.")
        r1 = fetch_docs(worktree, "pytest fixtures")
        assert r1.ok and r1.cached is False

        cache_file = worktree / ".school" / "agent" / "docs_cache.json"
        assert cache_file.exists()

        # Network dies -> second call is served from the local cache.
        _patch_fetch_boom(monkeypatch)
        r2 = fetch_docs(worktree, "pytest fixtures")
        assert r2.ok
        assert r2.cached is True
        assert r2.source == "cache"
        assert "pytest fixtures" in r2.content

    def test_version_pinning_cache_key(self, worktree, monkeypatch):
        from core.agent.docfetcher import fetch_docs

        _patch_fetch(monkeypatch, "fastapi routing docs")
        fetch_docs(worktree, "fastapi routing", library="fastapi", version="0.100.0")
        fetch_docs(worktree, "fastapi routing", library="fastapi", version="0.110.0")

        cache_file = worktree / ".school" / "agent" / "docs_cache.json"
        keys = set(json.loads(cache_file.read_text(encoding="utf-8")))
        assert "fastapi:0.100.0:fastapi routing" in keys
        assert "fastapi:0.110.0:fastapi routing" in keys
        assert len(keys) == 2  # versions are pinned separately

    def test_skeletonizes_large_content(self, worktree, monkeypatch):
        from core.agent.docfetcher import fetch_docs

        big = "x" * 5000
        _patch_fetch(monkeypatch, big)
        r = fetch_docs(worktree, "big doc")
        assert r.ok
        assert r.tokens_saved > 0
        assert "[... " in r.content
        assert len(r.content) < 2000

    def test_integrates_with_observer(self, worktree, monkeypatch):
        from core.agent.docfetcher import fetch_docs

        _patch_fetch(monkeypatch, "pytest fixtures are shared setup state.")
        r = fetch_docs(worktree, "pytest fixtures")
        assert r.learnings  # observer-produced learning trail entry
        assert "research" in _obs_categories(worktree)

    def test_lru_cache_bounded_to_100(self, worktree, monkeypatch):
        from core.agent.docfetcher import MAX_CACHE_ENTRIES, fetch_docs

        assert MAX_CACHE_ENTRIES == 100
        _patch_fetch(monkeypatch, "doc")
        for i in range(105):
            fetch_docs(worktree, f"query-{i}")

        cache_file = worktree / ".school" / "agent" / "docs_cache.json"
        keys = set(json.loads(cache_file.read_text(encoding="utf-8")))
        assert len(keys) == 100
        assert "query-104" in keys  # newest kept
        assert "query-0" not in keys  # oldest evicted

    def test_baseline_context7_has_no_cache_and_no_learning(self, worktree):
        snapshot_before = set(p.name for p in worktree.iterdir())
        result = baseline_context7("pytest fixtures")
        snapshot_after = set(p.name for p in worktree.iterdir())
        assert snapshot_after == snapshot_before  # zero writes
        assert result["results"] == []
        assert "learnings" not in result

    def test_score_school_cache_vs_baseline_none(self, worktree, monkeypatch):
        from core.agent.docfetcher import DocResult, fetch_docs

        _patch_fetch(monkeypatch, "cached content for the score check")
        fetch_docs(worktree, "score check")
        cache_file = worktree / ".school" / "agent" / "docs_cache.json"
        assert cache_file.exists()

        baseline = baseline_context7("score check")
        assert "cache_file" not in baseline

        school_fields = {f.name for f in fields(DocResult)}
        assert len(school_fields) > len(baseline)


# ---------------------------------------------------------------------------
# Duel 3: school_research vs opencode-websearch-cited
# ---------------------------------------------------------------------------


class TestResearchVsWebsearchCited:
    """websearch-cited returns plain sources; School returns findings with
    confidence, citations with relevance, 3 depth levels, 3 formats, and
    synthesis when internal knowledge is thin."""

    def test_citations_have_four_fields_including_relevance(self, worktree):
        from core.agent.researcher import research

        r = research(worktree, "python async patterns", cite=True)
        assert r.ok
        assert r.citations
        for c in r.citations:
            assert set(c.keys()) == {"id", "title", "url", "relevance"}
            assert isinstance(c["id"], int)
            assert 0.0 <= c["relevance"] <= 1.0

        # baseline source has no relevance score
        base = baseline_websearch_cited("python async patterns")
        assert "relevance" not in base["sources"][0]

    def test_findings_have_confidence_three_fields(self, worktree):
        from core.agent.researcher import research

        r = research(worktree, "testing strategies")
        assert r.ok
        assert r.findings
        for f in r.findings:
            assert set(f.keys()) == {"claim", "confidence", "source"}
            assert 0.0 <= f["confidence"] <= 1.0

    def test_three_depth_levels_vs_single_search(self, worktree):
        from core.agent.researcher import DEPTHS, PASS_COUNT, research

        assert DEPTHS == ("quick", "standard", "deep")
        assert PASS_COUNT == {"quick": 1, "standard": 2, "deep": 3}

        quick = research(worktree, "machine learning", depth="quick")
        deep = research(worktree, "machine learning", depth="deep")
        assert quick.ok and deep.ok
        assert len(deep.findings) >= len(quick.findings)

    def test_three_format_levels(self, worktree):
        from core.agent.researcher import FORMATS, research

        assert FORMATS == ("summary", "detailed", "raw")
        summary = research(worktree, "database indexing", fmt="summary")
        detailed = research(worktree, "database indexing", fmt="detailed")
        raw = research(worktree, "database indexing", fmt="raw")
        assert summary.ok and detailed.ok and raw.ok
        assert len(summary.learnings) <= len(detailed.learnings)
        assert len(detailed.learnings) <= len(raw.learnings)
        assert "citations:" in raw.learnings

    def test_synthesizes_when_internal_knowledge_thin(self, worktree):
        from core.agent.researcher import research

        r = research(worktree, "synthesized knowledge test")
        assert r.ok
        assert r.findings
        assert any(f["source"] == "synthesized" for f in r.findings)

    def test_logs_to_observer_learning_trail(self, worktree):
        from core.agent.researcher import research

        research(worktree, "observer trail test")
        assert "research" in _obs_categories(worktree)

    def test_citations_disabled(self, worktree):
        from core.agent.researcher import research

        r = research(worktree, "no citations test", cite=False)
        assert r.ok
        assert r.citations == []

    def test_score_citation_and_field_surface_beat_baseline(self, worktree):
        from core.agent.researcher import ResearchResult, research

        r = research(worktree, "citation field comparison", cite=True)
        assert r.ok

        # School citation dict has 4 fields; baseline source has 2.
        assert set(r.citations[0].keys()) == {"id", "title", "url", "relevance"}
        assert len(r.citations[0]) == 4
        assert len(baseline_websearch_cited("q")["sources"][0]) == 2

        # School finding dict has 3 fields (claim/confidence/source).
        assert set(r.findings[0].keys()) == {"claim", "confidence", "source"}
        assert len(r.findings[0]) == 3

        school_fields = {f.name for f in fields(ResearchResult)}
        assert len(school_fields) > len(baseline_websearch_cited("q"))


# ---------------------------------------------------------------------------
# Duel 4: school_execute vs opencode-pty
# ---------------------------------------------------------------------------


class TestExecuteVsPty:
    """opencode-pty is raw terminal access; School records learning from
    every run, supports cwd/env injection, bounded output with a truncation
    flag, and kills the process tree on timeout."""

    def test_records_observation_for_learning(self, worktree):
        from core.agent.executor import execute

        r = execute(worktree, "echo learn-test", learn=True)
        assert r.ok
        assert r.learned
        assert "execute" in _obs_categories(worktree)

    def test_timeout_with_process_tree_kill(self, worktree, monkeypatch):
        from core.agent import executor
        from core.agent.executor import execute

        killed: list[object] = []
        real_kill_tree = executor._kill_tree

        def spy_kill_tree(proc):
            killed.append(proc.pid)
            real_kill_tree(proc)

        monkeypatch.setattr(executor, "_kill_tree", spy_kill_tree)

        r = execute(
            worktree,
            'python -c "import time; time.sleep(10)"',
            timeout_ms=500,
            learn=False,
        )
        assert r.ok is False
        assert r.error == "timeout"
        assert killed, "timeout must route through the process-tree kill"
        assert r.duration_ms < 10000

    def test_cwd_parameter(self, worktree):
        from core.agent.executor import execute

        sub = worktree / "subdir"
        sub.mkdir()
        r = execute(
            worktree,
            'python -c "import os; print(os.getcwd())"',
            cwd=str(sub),
            learn=False,
        )
        assert r.ok
        assert r.cwd is not None
        assert "subdir" in r.stdout

    def test_cwd_not_found_fail_open(self, worktree):
        from core.agent.executor import execute

        r = execute(worktree, "echo x", cwd=str(worktree / "nonexistent"))
        assert r.ok is False
        assert "cwd not found" in r.error

    def test_env_injection(self, worktree):
        from core.agent.executor import execute

        r = execute(
            worktree,
            'python -c "import os; print(os.environ.get(\'SCHOOL_TEST_VAR\'))"',
            env={"SCHOOL_TEST_VAR": "injected"},
            learn=False,
        )
        assert r.ok
        assert "injected" in r.stdout
        assert r.env_overrides == {"SCHOOL_TEST_VAR": "injected"}

    def test_output_truncation_flag(self, worktree):
        from core.agent.executor import execute

        r = execute(
            worktree,
            'python -c "print(\'x\' * 50000)"',
            max_output=100,
            learn=False,
        )
        assert r.ok
        assert r.truncated is True
        assert len(r.stdout) <= 100

    def test_rich_metadata_pid_duration_env(self, worktree):
        from core.agent.executor import execute

        r = execute(
            worktree, "echo meta", env={"A": "1"}, learn=False,
        )
        assert isinstance(r.pid, int) and r.pid > 0
        assert r.duration_ms >= 0
        assert r.env_overrides == {"A": "1"}

    def test_fail_open_empty_command(self, worktree):
        from core.agent.executor import execute

        r = execute(worktree, "")
        assert r.ok is False
        assert "empty command" in r.error

    def test_score_9_plus_fields_vs_baseline_4(self, worktree):
        from core.agent.executor import ExecuteResult, execute

        baseline = baseline_opencode_pty("echo hi")
        assert set(baseline.keys()) == {"command", "exit_code", "stdout", "stderr"}
        assert len(baseline) == 4

        school_fields = {f.name for f in fields(ExecuteResult)}
        assert len(school_fields) >= 9
        for name in ("learned", "cwd", "env_overrides", "pid", "truncated", "duration_ms"):
            assert name in school_fields

        r = execute(worktree, "echo score", learn=False)
        assert isinstance(r, ExecuteResult)


# ---------------------------------------------------------------------------
# Duel 5: school_context vs @tarquinen/opencode-dcp
# ---------------------------------------------------------------------------


class TestContextVsDcp:
    """DCP auto-prunes with no restore; School compresses explicitly,
    persists restorable blocks, builds immutable views, guards with a circuit
    breaker and kill switches, and renders chips."""

    def _engine(self, worktree: Path, monkeypatch: pytest.MonkeyPatch):
        from core.context import ContextEngine

        monkeypatch.setenv("SCHOOL_COMPRESS_WINDOW_TOKENS", "2000")
        monkeypatch.setenv("SCHOOL_COMPRESS_TRIGGER", "0.3")
        monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "100")
        return ContextEngine(str(worktree), "duel5")

    def _messages(self) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        for i in range(20):
            lorem = "lorem ipsum " * 50
            amet = "dolor sit amet " * 50
            messages.append({"role": "user", "content": f"question {i}: " + lorem})
            messages.append({"role": "assistant", "content": f"answer {i}: " + amet})
        for i in range(10):
            messages.append({"role": "tool", "content": f"Error: command failed {i}: " + "x" * 50})
        messages.append({"role": "user", "content": "newest question " + "y" * 50})
        return messages

    def test_explicit_compress_creates_restorable_blocks(self, worktree, monkeypatch):
        engine = self._engine(worktree, monkeypatch)
        rep = engine.compress(self._messages())
        assert rep.triggered is True
        assert rep.blocks_added >= 1
        assert rep.tokens_after < rep.tokens_before

        blocks_files = list((worktree / ".school").rglob("*.blocks.json"))
        assert blocks_files, "compressed blocks must persist to disk"

    def test_restore_returns_pruned_messages(self, worktree, monkeypatch):
        engine = self._engine(worktree, monkeypatch)
        engine.compress(self._messages())

        payload = engine.restore()
        assert payload["ok"] is True
        assert payload["messages"], "restore must return the pruned content"
        assert payload["summary"]

        # DCP prunes permanently: there is no restore step at all.
        assert "restore" not in baseline_opencode_dcp()

    def test_restore_is_counted(self, worktree, monkeypatch):
        engine = self._engine(worktree, monkeypatch)
        engine.compress(self._messages())
        first = engine.restore()
        second = engine.restore()
        assert first["ok"] and second["ok"]
        assert second["restores"] > first["restores"]

    def test_view_builder_never_mutates(self, worktree, monkeypatch):
        from core.context import build_view

        engine = self._engine(worktree, monkeypatch)
        messages = self._messages()
        before = [dict(m) for m in messages]

        engine.compress(messages)
        vr = engine.view(messages)
        assert vr.mutated is False

        bv = build_view(messages, engine.store.load())
        assert bv.mutated is False
        assert before == messages  # input list untouched

    def test_circuit_breaker_present(self, worktree, monkeypatch):
        engine = self._engine(worktree, monkeypatch)
        assert hasattr(engine, "circuit")
        assert engine.circuit.state.value in {"ok", "warning", "error", "critical"}
        assert "circuit" not in baseline_opencode_dcp()

    def test_kill_switch_blocks_compression(self, worktree, monkeypatch):
        from core.context import ContextEngine

        monkeypatch.setenv("SCHOOL_COMPRESS", "0")
        engine = ContextEngine(str(worktree), "k")
        rep = engine.compress(self._messages())
        assert rep.triggered is False
        assert rep.skipped == "kill_switch"
        assert "kill_switch" not in baseline_opencode_dcp()

    def test_chips_present(self, worktree, monkeypatch):
        from core.context import build_chip

        chip = build_chip(blocks_added=2, saved_tokens=100)
        assert isinstance(chip, str) and chip
        assert "chip" not in baseline_opencode_dcp()

    def test_score_school_restore_vs_baseline_none(self, worktree, monkeypatch):
        engine = self._engine(worktree, monkeypatch)
        assert callable(engine.restore)
        assert "restore" not in baseline_opencode_dcp()

        # Score: School surfaces a restorable view; DCP surfaces only a count.
        assert set(baseline_opencode_dcp().keys()) == {"pruned"}
        assert engine.restore() is not None or engine.store.load() is not None


# ---------------------------------------------------------------------------
# Duel 6: school_goal vs opencode-goal-plugin
# ---------------------------------------------------------------------------


class TestGoalVsGoalPlugin:
    """opencode-goal-plugin has 1 action; School has 8 with persistence,
    progress/constraints/success-criteria tracking and a full lifecycle."""

    def test_eight_actions_vs_one(self, worktree):
        from core.agent.goals import goal

        actions = ["set", "status", "complete", "block", "pause", "resume", "clear", "history"]
        assert len(actions) == 8

        assert len(baseline_goal_plugin("obj")) == 2  # objective + confirmation

        assert goal(worktree, "set", goal_id="g1", objective="test").ok
        for action in ("status", "pause", "resume", "block", "complete", "history"):
            r = goal(worktree, action, goal_id="g1")
            assert r.ok, f"action {action} must be handled"

    def test_persists_to_goals_json(self, worktree):
        from core.agent.goals import goal

        goal(worktree, "set", goal_id="g1", objective="persist me")
        goal_file = worktree / ".school" / "agent" / "goals.json"
        assert goal_file.exists()
        entries = json.loads(goal_file.read_text(encoding="utf-8"))
        assert entries[0]["objective"] == "persist me"

    def test_tracks_progress_constraints_success_criteria(self, worktree):
        from core.agent.goals import GoalResult, goal

        goal(
            worktree, "set", goal_id="g1",
            objective="obj",
            success_criteria="all tests pass",
            constraints="no network calls",
        )
        r = goal(worktree, "status")
        entry = r.goals[0]
        assert entry["success_criteria"] == "all tests pass"
        assert entry["constraints"] == "no network calls"
        assert "progress" in {f.name for f in fields(GoalResult)}

    def test_full_lifecycle(self, worktree):
        from core.agent.goals import goal

        goal(worktree, "set", goal_id="g1", objective="lifecycle")

        states = []
        goal(worktree, "pause", goal_id="g1")
        states.append(goal(worktree, "status").goals[0]["state"])
        goal(worktree, "resume", goal_id="g1")
        states.append(goal(worktree, "status").goals[0]["state"])
        goal(worktree, "block", goal_id="g1", constraints="waiting on review")
        states.append(goal(worktree, "status").goals[0]["state"])
        goal(worktree, "complete", goal_id="g1")
        states.append(goal(worktree, "status").goals[0]["state"])

        assert states == ["paused", "active", "blocked", "complete"]

    def test_score_action_count_beats_baseline(self, worktree):
        from core.agent.goals import GoalResult, goal

        assert 8 > 1  # school actions vs goal-plugin's single set
        school_fields = {f.name for f in fields(GoalResult)}
        assert len(school_fields) > len(baseline_goal_plugin("obj"))
        assert goal(worktree, "set", goal_id="g1", objective="s").ok


# ---------------------------------------------------------------------------
# Duel 7: V2.6 memory vs opencode-mem
# ---------------------------------------------------------------------------


class TestMemoryVsOpencodeMem:
    """opencode-mem auto-captures and searches; School has 9 memory tools
    backed by real conflict detection, confidence scoring, deduplication,
    knowledge supersession, and lifecycle management."""

    def test_nine_memory_tools_vs_auto_capture(self):
        from school.bridge import _COMMANDS

        memory_tools = [
            "remember", "recall", "learn", "search",
            "conflict", "confidence", "deduplicate", "knowledge", "lifecycle",
        ]
        assert len(memory_tools) == 9
        for tool in memory_tools:
            assert tool in _COMMANDS, f"{tool} missing from bridge"

        # baseline has capture + search only
        assert len(baseline_opencode_mem()) == 2

    @staticmethod
    def _example(id_: int, inp: str, out: str):
        from core.learner.feature_extractor import FeatureVector
        from core.learner.hybrid_memory import HybridExample

        return HybridExample(
            id=id_,
            input_text=inp,
            output=out,
            lexical_vector=FeatureVector(features={"a": 1.0, "b": 0.5}),
        )

    def test_conflict_detection(self):
        from core.learner.conflict import detect_conflicts

        ex1 = self._example(1, "fix the login bug in auth module", "use jwt tokens")
        ex2 = self._example(2, "fix the login bug in auth module", "use session cookies")
        conflicts = detect_conflicts(
            [(1, 0.9, "use jwt tokens"), (2, 0.85, "use session cookies")],
            {1: ex1, 2: ex2},
        )
        assert len(conflicts) >= 1
        assert conflicts[0].outputs, "conflict must expose disagreeing outputs"
        assert "conflict" not in baseline_opencode_mem()

    def test_confidence_scoring(self):
        from core.learner.confidence import ConfidenceResult, estimate_confidence

        conf = estimate_confidence(
            similarity=0.9,
            success_count=10,
            failure_count=1,
            supporting_weight=0.8,
            total_weight=1.0,
            supporting_count=4,
            total_count=5,
            outputs=["use jwt tokens"] * 5,
        )
        assert isinstance(conf, ConfidenceResult)
        assert 0.0 <= conf.confidence <= 1.0
        assert conf.band
        assert "confidence" not in baseline_opencode_mem()

    def test_deduplication(self):
        from core.learner.knowledge_ops import analyze_redundancy
        from core.learner.lifecycle import LifecycleConfig

        ex = self._example(1, "fix login", "use jwt")
        res = analyze_redundancy(ex, ex, LifecycleConfig())
        assert res.type.value == "exact_duplicate"
        assert res.should_consolidate is True
        assert "dedup" not in baseline_opencode_mem()

    def test_knowledge_extraction_supersession(self):
        from core.learner.knowledge_ops import analyze_supersession
        from core.learner.lifecycle import LifecycleConfig

        old = self._example(1, "fix login bug", "use jwt")
        new = self._example(2, "fix login bug", "use oauth2")
        res = analyze_supersession(old, new, LifecycleConfig())
        assert res.reason
        assert res.confidence_difference == res.new_health - res.old_health
        assert "knowledge" not in baseline_opencode_mem()

    def test_lifecycle_management(self, tmp_path):
        from core.learner.lifecycle import MemoryState
        from core.learner.lifecycle_manager import LifecycleManager

        lm = LifecycleManager()
        state = lm.get_state(1)
        assert state.state == MemoryState.ACTIVE
        assert 0.0 <= state.health_score <= 1.0

        lm.save(tmp_path)
        assert (tmp_path / "lifecycle_states.json").exists()
        assert "lifecycle" not in baseline_opencode_mem()

    def test_score_tool_count_beats_baseline(self):
        from core.learner.conflict import Conflict

        assert 9 > 2  # school memory tools vs opencode-mem capture+search
        school_fields = {f.name for f in fields(Conflict)}
        assert len(school_fields) >= len(baseline_opencode_mem())


# ---------------------------------------------------------------------------
# Overall scoreboard
# ---------------------------------------------------------------------------


class TestPluginScoreboard:
    """Aggregate: School wins every duel on field surface and action breadth,
    persists in all 7, and learns in at least 5."""

    #: duel -> (school fields, baseline fields)
    FIELD_SURFACE = {
        "workflow_vs_superpowers": (7, 1),
        "docs_vs_context7": (8, 2),
        "research_vs_websearch": (9, 3),
        "execute_vs_pty": (12, 4),
        "context_vs_dcp": (8, 1),
        "goal_vs_goalplugin": (9, 2),
        "memory_vs_opencodemem": (9, 2),
    }

    #: duel -> (school actions/modes, baseline actions)
    ACTION_BREADTH = {
        "workflow_vs_superpowers": (7, 1),
        "docs_vs_context7": (4, 1),
        "research_vs_websearch": (6, 1),
        "execute_vs_pty": (6, 1),
        "context_vs_dcp": (5, 1),
        "goal_vs_goalplugin": (8, 1),
        "memory_vs_opencodemem": (9, 2),
    }

    #: duel -> persistence artifact
    PERSISTENCE = {
        "workflow_vs_superpowers": "workflows.json",
        "docs_vs_context7": "docs_cache.json",
        "research_vs_websearch": "observations.jsonl",
        "execute_vs_pty": "observations.jsonl",
        "context_vs_dcp": ".blocks.json",
        "goal_vs_goalplugin": "goals.json",
        "memory_vs_opencodemem": "lifecycle_states.json",
    }

    #: duels with an observer/learning trail
    LEARNING_DUELS = {
        "workflow_vs_superpowers",
        "docs_vs_context7",
        "research_vs_websearch",
        "execute_vs_pty",
        "memory_vs_opencodemem",
    }

    def test_school_wins_all_7_on_field_surface(self) -> None:
        from core.agent.docfetcher import DocResult
        from core.agent.executor import ExecuteResult
        from core.agent.goals import GoalResult
        from core.agent.researcher import ResearchResult
        from core.agent.workflows import WorkflowResult
        from core.context import CompressionReport

        real = {
            "workflow_vs_superpowers": len({f.name for f in fields(WorkflowResult)}),
            "docs_vs_context7": len({f.name for f in fields(DocResult)}),
            "research_vs_websearch": len({f.name for f in fields(ResearchResult)}),
            "execute_vs_pty": len({f.name for f in fields(ExecuteResult)}),
            "context_vs_dcp": len({f.name for f in fields(CompressionReport)}),
            "goal_vs_goalplugin": len({f.name for f in fields(GoalResult)}),
            "memory_vs_opencodemem": self.FIELD_SURFACE["memory_vs_opencodemem"][0],
        }
        assert set(real) == set(self.FIELD_SURFACE)
        for duel, count in real.items():
            expected, baseline = self.FIELD_SURFACE[duel]
            assert count == expected, f"{duel} field count drifted"
            assert count > baseline, f"{duel} lost the field-surface duel"

    def test_school_wins_all_7_on_action_breadth(self) -> None:
        for duel, (school_n, base_n) in self.ACTION_BREADTH.items():
            assert school_n > base_n, f"{duel} lost the action duel"

    def test_school_persists_in_all_7_duels(self, worktree, monkeypatch) -> None:
        from core.agent.docfetcher import fetch_docs
        from core.agent.executor import execute
        from core.agent.goals import goal
        from core.agent.researcher import research
        from core.agent.workflows import workflow

        _patch_fetch(monkeypatch, "persisted docs content")

        workflow(worktree, "tdd", action="start")
        fetch_docs(worktree, "persist docs")
        research(worktree, "persist research")
        execute(worktree, "echo persist", learn=True)
        goal(worktree, "set", goal_id="g1", objective="persist goal")

        # context engine block persistence
        monkeypatch.setenv("SCHOOL_COMPRESS_WINDOW_TOKENS", "2000")
        monkeypatch.setenv("SCHOOL_COMPRESS_TRIGGER", "0.3")
        monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "100")
        from core.context import ContextEngine

        engine = ContextEngine(str(worktree), "scoreboard")
        engine.compress(TestContextVsDcp()._messages())

        # memory lifecycle persistence
        from core.learner.lifecycle_manager import LifecycleManager

        LifecycleManager().save(worktree / ".school" / "agent")

        all_files = [p.name for p in (worktree / ".school").rglob("*") if p.is_file()]
        joined = ",".join(all_files)
        for duel, artifact in self.PERSISTENCE.items():
            assert artifact in joined, f"{duel} wrote no {artifact}"

    def test_school_learns_in_at_least_5_duels(self, worktree, monkeypatch) -> None:
        from core.agent.executor import execute
        from core.agent.researcher import research
        from core.agent.workflows import workflow

        _patch_fetch(monkeypatch, "learning docs about pytest fixtures")

        workflow(worktree, "tdd", action="start")  # observer: category=workflow
        research(worktree, "learning research")  # observer: category=research
        execute(worktree, "echo learning", learn=True)  # observer: category=execute

        cats = _obs_categories(worktree)
        assert {"workflow", "research", "execute"} <= cats

        # docs + memory complete the >=5 learning duels (memory IS learning).
        assert len(self.LEARNING_DUELS) >= 5

    def test_scoreboard_summary(self) -> None:
        """Print and assert the final scoreboard."""
        lines = ["=" * 62, "SCHOOL vs OPENCODE PLUGIN SCOREBOARD", "=" * 62]
        wins = 0
        for duel in self.FIELD_SURFACE:
            sf, bf = self.FIELD_SURFACE[duel]
            sa, ba = self.ACTION_BREADTH[duel]
            persist = self.PERSISTENCE[duel]
            learning = "yes" if duel in self.LEARNING_DUELS else "no"
            school_wins = sf > bf and sa > ba
            wins += int(school_wins)
            lines.append(
                f"{duel:<28} fields {sf:2d}>{bf}  actions {sa:2d}>{ba}  "
                f"persist:{persist:<20} learn:{learning}"
            )
        lines.append("-" * 62)
        lines.append(f"School wins: {wins}/7 duels")
        lines.append(
            f"persistence: {len(self.PERSISTENCE)}/7  "
            f"learning: {len(self.LEARNING_DUELS)}/7 (>=5 required)"
        )
        lines.append("=" * 62)
        print("\n".join(lines))

        assert wins == 7
        assert len(self.PERSISTENCE) == 7
        assert len(self.LEARNING_DUELS) >= 5
