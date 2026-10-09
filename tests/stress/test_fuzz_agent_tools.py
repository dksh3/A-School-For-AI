"""Adversarial fail-open fuzz campaign for the School agent tool suite.

Invariant under test: every tool returns a result object for ANY input and
never raises out of the tool boundary. Each tool feature runs 2000 iterations
of failure-seeking inputs (wrong types, cyclic refs, NUL bytes, huge payloads,
hostile dunders). Per-label counts land in the fuzz harness ledger and are
printed/written at module teardown as proof of coverage.

Worktrees are ``tempfile.mkdtemp`` based (OneDrive-safe, never ``tmp_path``)
and the process CWD is chdir'd into a deep scratch chain so hostile relative
paths (``../`` traversal) cannot escape the sandbox before cleanup.
"""

from __future__ import annotations

import contextlib
import os
import pathlib
import random
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import fields
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from fuzz_harness import (  # noqa: E402
    HOSTILE,
    _BadDict,
    _BadList,
    _Evil,
    _Throws,
    fuzz_fail_open,
    gen_value,
    ledger_summary,
)

from core.agent.docfetcher import DocResult, fetch_docs  # noqa: E402
from core.agent.executor import ExecuteResult, execute  # noqa: E402
from core.agent.explorer import ExploreResult, explore  # noqa: E402
from core.agent.goals import GoalResult, goal  # noqa: E402
from core.agent.navigator import NavigateResult, navigate  # noqa: E402
from core.agent.observer import ObserveResult, observe  # noqa: E402
from core.agent.progress import ProgressResult, progress  # noqa: E402
from core.agent.researcher import ResearchResult, research  # noqa: E402
from core.agent.sessions import SessionResult, session  # noqa: E402
from core.agent.workflows import WorkflowResult, register_workflow, workflow  # noqa: E402

N = 2000
LEDGER_FILE = Path(tempfile.gettempdir()) / "opencode" / "school_fuzz_ledger.txt"

# --------------------------------------------------------------------------
# shared hostile fixtures (pre-built so make_args can never raise)
# --------------------------------------------------------------------------
EVIL = _Evil()
THROWS = _Throws()
BAD_DICT = _BadDict()
BAD_LIST = _BadList()
CYCLE_DICT: dict[str, Any] = {"self": None}
CYCLE_DICT["self"] = CYCLE_DICT
CYCLE_LIST: list[Any] = []
CYCLE_LIST.append(CYCLE_LIST)

OBS_POOL: list[Any] = [
    "hello world", "", None, 123, 3.14, EVIL, "x" * 5000, "\x00", "null\x00byte",
    "\ud800surrogate", "unicode ünïcödé \U0001f4a9", "line\nbreak", "\t", " " * 500,
    "{}{x}", BAD_LIST, THROWS, b"bytes", ["nested"], "obs " * 300,
]
CAT_POOL: list[Any] = [
    "tool_call", "error", "pattern", "research", "execute", "", "bogus", "x" * 1000,
    None, 3.14, EVIL, BAD_DICT, 0, "\x00", "Category",
]
EV_POOL: list[Any] = [
    None, {}, {"k": "v"}, {"nested": {"deep": [1, 2, {"x": None}]}}, {"set": {1, 2}},
    CYCLE_DICT, CYCLE_LIST, EVIL, BAD_DICT, BAD_LIST, "stringy", 42, float("nan"),
    {1: 2, None: 3}, {"b": b"\xff\xfe"}, {"e": Exception("x")}, gen_value(rng=random.Random(7)),
]
GID_POOL: list[Any] = ["g1", "g2", "", None, 123, EVIL, "X" * 500, "\x00", "ünï", THROWS]
OBJ_POOL: list[Any] = [
    "learn routing", "", None, EVIL, "x" * 5000, {"a": 1}, float("nan"), CYCLE_DICT, BAD_LIST,
]
SC_POOL: list[Any] = ["done when green", "", None, EVIL, [1, 2], "x" * 3000, "\ud800"]
MT_POOL: list[Any] = [
    0, -1, 5, 10**9, "x", None, float("nan"), float("inf"), EVIL, 2**63, 3.7, True,
]
CON_POOL: list[Any] = ["need docs", "", None, EVIL, "x" * 5000, [1, 2], THROWS]
QUERY_POOL: list[Any] = [
    "how does routing work", "", "   ", None, 123, EVIL, "x" * 50000, "\x00",
    "ünïcödé \U0001f4a9", "{}{x}", "widget factory output", BAD_LIST,
    "a b c d e f g h i j " * 200, "\ud800", "production line setup",
]
DEPTH_R_POOL: list[Any] = ["quick", "standard", "deep", "", "bogus", None, 123, EVIL, "d" * 1000]
FMT_POOL: list[Any] = ["summary", "detailed", "raw", "", "bullets", None, 42, EVIL, "f" * 500]
CITE_POOL: list[Any] = [True, False, None, 0, 1, "yes", EVIL, [], {}, THROWS]
TARGET_POOL: list[Any] = [
    ".", "sub", "missing", "", None, 123, EVIL, "a\x00b", "..", "X" * 5000,
    "file.txt", b"x", ["a"], "\U0001f4a9", "sub/inner.txt", THROWS,
]
DEPTH_E_POOL: list[Any] = [0, 1, 3, 99, -1, "file", "3", "", None, EVIL, float("nan"), 2**63]
FOCUS_POOL: list[Any] = [
    "structure", "patterns", "conventions", "", "bogus", None, EVIL, "x" * 5000, 123,
]
ITEMS_POOL: list[Any] = [
    None, [], [{"content": "a", "status": "completed"}], [{"content": 5}],
    [{"status": "in_progress"}], [{"content": "x", "status": "completed", "extra": 1}],
    EVIL, BAD_LIST, BAD_DICT, "string", 123, [{"a": {1, 2}}], [[1, 2]],
    [{"content": EVIL}], [{"content": "c", "status": float("nan")}],
    gen_value(rng=random.Random(11)), CYCLE_LIST,
]
CONTEXT_POOL: list[Any] = [None, "", "ctx", EVIL, {"a": 1}, "x" * 5000, b"\xff", THROWS]
SID_POOL: list[Any] = ["s1", "s2", "", None, 123, EVIL, "\x00", "X" * 1000, "ünï", THROWS]
FOCUS_S_POOL: list[Any] = ["routing", "", None, EVIL, {"a": 1}, "x" * 5000, 3.14, "\ud800"]
# Commands are injection-shaped but strictly harmless on cmd.exe (no writes/deletes).
COMMAND_POOL: list[Any] = [
    "rem", "echo fuzz", "ver", "", "   ", None, 123,
    "echo a & echo b", "echo (injection) && rem", "$(id) `id` | rem",
    '"unbalanced quote', "echo hi\x00nul", "X" * 5000,
    "\U0001f4a9 echo unicode", "echo ünïcödé", "echo %PATH%", "echo ^& literal",
    b"bytes", EVIL, "echo . | rem",
]
TIMEOUT_POOL: list[Any] = [
    30000, 5000, 0, -1, 10**9, float("inf"), float("nan"), "x", None,
    EVIL, 2**63, -0.5, complex(1, 2), THROWS, True,
]
LEARN_POOL: list[Any] = [True, False, None, 0, 1, "yes", EVIL, [], {}, THROWS]
MAXOUT_POOL: list[Any] = [10000, 0, -5, 10**9, "x", None, float("nan"), EVIL, True, 3.7]
ENV_POOL: list[Any] = [
    None, {}, {"A": "B"}, {"MY_VAR": "hello"}, {"N": 123}, {"a\x00b": "c"},
    {"k" * 200: "v" * 200}, BAD_DICT, EVIL, "notadict", 42,
    {"nested": {"x": 1}}, {1: 2}, {"E": EVIL},
]
PATH_POOL: list[Any] = [
    "", ".", "hello.txt", "sub", "missing.txt", "a\x00b", "../..", "X" * 3000,
    None, 123, EVIL, b"x", "sub/inner.txt", "C:\\absolute\\weird", THROWS, "\U0001f4a9",
]
PATTERN_POOL: list[Any] = [
    "hello", "", "(", "[", "*", "(?P<", "a{2,1}", "\\", "\U0001f4a9", "x" * 5000,
    None, 123, EVIL, ".", "HELLO", "\x00", [1], "inner",
]
DEPTH_N_POOL: list[Any] = [
    0, 1, 3, 99, -1, 2, "5", "x", None, float("nan"), float("inf"), 10**50, EVIL, True,
]
WF_NAME_POOL: list[Any] = [
    "tdd", "debug", "brainstorm", "review", "bogus", "", "deploy", "X" * 1000,
    None, 123, EVIL, "tdd\x00", "ünïcödé", "release", THROWS,
]
PHASE_POOL: list[Any] = [
    None, "", "red", "build,test", ",", "x" * 5000, 123, EVIL, "\x00",
    ["a"], "green", "reproduce", "refactor,commit", THROWS,
]
NOTES_POOL: list[Any] = [
    None, "", "note", "x" * 5000, 123, EVIL, {"a": 1}, "failing test written", b"\xff",
]
REG_PHASES_POOL: list[Any] = [
    ["a", "b"], [], None, EVIL, "phases", [1, 2], ["x", EVIL], BAD_LIST, [" build ", ""], 42,
]
LIB_POOL: list[Any] = [None, "requests", "lib" * 100, 123, EVIL, "", "ünï", THROWS]
VER_POOL: list[Any] = [None, "2.31.0", "v" * 100, 123, EVIL, "", "latest", float("nan")]
USE_CACHE_POOL: list[Any] = [True, False, None, 0, 1, "yes", EVIL, [], {}, THROWS]


# --------------------------------------------------------------------------
# result-shape invariants
# --------------------------------------------------------------------------


def _is_str(v: Any) -> bool:
    return isinstance(v, str)


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_float(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _is_bool(v: Any) -> bool:
    return isinstance(v, bool)


def _is_list(v: Any) -> bool:
    return isinstance(v, list)


def _is_dict(v: Any) -> bool:
    return isinstance(v, dict)


def _str_or_none(v: Any) -> bool:
    return v is None or isinstance(v, str)


def _int_or_none(v: Any) -> bool:
    return v is None or (isinstance(v, int) and not isinstance(v, bool))


def _dict_or_none(v: Any) -> bool:
    return v is None or isinstance(v, dict)


def _typed(
    cls: type,
    spec: dict[str, Callable[[Any], bool]],
    needs_error: bool = True,
) -> Callable[[Any], None]:
    def check(result: Any) -> None:
        assert isinstance(result, cls), f"expected {cls.__name__}, got {type(result).__name__}"
        for name, pred in spec.items():
            value = getattr(result, name)
            assert pred(value), f"{name} has bad type {type(value).__name__}"
        if needs_error:
            assert result.ok or result.error, "ok=False must carry an error message"

    return check


_check_observe = _typed(
    ObserveResult,
    {
        "ok": _is_bool, "observation_id": _is_str, "pattern": _is_str,
        "learning": _is_str, "total": _is_int, "error": _is_str, "extra": _is_dict,
    },
)
_check_goal = _typed(
    GoalResult,
    {
        "ok": _is_bool, "action": _is_str, "goal_id": _is_str, "state": _is_str,
        "objective": _is_str, "progress": _is_float, "goals": _is_list,
        "error": _is_str, "extra": _is_dict,
    },
)
_check_research = _typed(
    ResearchResult,
    {
        "ok": _is_bool, "query": _is_str, "depth": _is_str, "fmt": _is_str,
        "learnings": _is_str, "findings": _is_list, "source": _is_str,
        "citations": _is_list, "error": _str_or_none,
    },
)


def _check_research_shape(result: Any) -> None:
    _check_research(result)
    assert result.depth in {"quick", "standard", "deep"}, result.depth
    assert result.fmt in {"summary", "detailed", "raw"}, result.fmt
    for finding in result.findings:
        assert isinstance(finding, dict)
        assert set(finding) == {"claim", "confidence", "source"}
        assert isinstance(finding["claim"], str)
        assert 0.0 <= float(finding["confidence"]) <= 1.0
    for citation in result.citations:
        assert isinstance(citation, dict)
        assert set(citation) == {"id", "title", "url", "relevance"}
        assert isinstance(citation["url"], str)


_check_explore = _typed(
    ExploreResult,
    {
        "ok": _is_bool, "target": _is_str, "structure": _is_str,
        "patterns": _is_list, "conventions": _is_list, "error": _is_str,
    },
)


def _check_explore_shape(result: Any) -> None:
    _check_explore(result)
    assert all(isinstance(p, str) for p in result.patterns)
    assert all(isinstance(c, str) for c in result.conventions)


_check_progress = _typed(
    ProgressResult,
    {"ok": _is_bool, "action": _is_str, "items": _is_list, "bars": _is_str, "error": _is_str},
)


def _check_progress_shape(result: Any) -> None:
    _check_progress(result)
    assert all(isinstance(i, dict) for i in result.items)
    assert isinstance(result.bars, str)


_check_session = _typed(
    SessionResult,
    {
        "ok": _is_bool, "action": _is_str, "session_id": _is_str, "focus": _is_str,
        "summary": _is_str, "sessions": _is_list, "data": _is_str, "error": _is_str,
    },
)
_check_execute = _typed(
    ExecuteResult,
    {
        "ok": _is_bool, "command": _is_str, "exit_code": _is_int, "stdout": _is_str,
        "stderr": _is_str, "duration_ms": _is_int, "learned": _str_or_none,
        "cwd": _str_or_none, "env_overrides": _dict_or_none, "pid": _int_or_none,
        "truncated": _is_bool, "error": _str_or_none,
    },
    needs_error=False,
)
_check_navigate = _typed(
    NavigateResult,
    {
        "ok": _is_bool, "action": _is_str, "path": _is_str, "content": _is_str,
        "entries": _is_list, "matches": _is_list, "tree": _is_str, "error": _is_str,
    },
)


def _check_navigate_shape(result: Any) -> None:
    _check_navigate(result)
    assert all(isinstance(e, str) for e in result.entries)
    assert all(isinstance(m, dict) for m in result.matches)


_check_workflow = _typed(
    WorkflowResult,
    {
        "ok": _is_bool, "workflow": _is_str, "phase": _is_str, "phases": _is_list,
        "guidance": _is_str, "state": _is_str, "error": _str_or_none,
    },
)


def _check_workflow_shape(result: Any) -> None:
    _check_workflow(result)
    assert all(isinstance(p, dict) for p in result.phases)


_check_doc = _typed(
    DocResult,
    {
        "ok": _is_bool, "query": _is_str, "source": _is_str, "content": _is_str,
        "cached": _is_bool, "tokens_saved": _is_int, "learnings": _str_or_none,
        "error": _str_or_none,
    },
)


def _check_register(result: Any) -> None:
    assert isinstance(result, bool), f"register_workflow returned {type(result).__name__}"


# --------------------------------------------------------------------------
# sandbox + pool helpers
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def sandbox() -> Iterator[Path]:
    """Deep scratch chain in the system temp dir (OneDrive-safe, no tmp_path).

    The CWD moves into the deepest level so hostile relative worktree paths
    (including ``../`` traversal) resolve inside the chain and get rmtree'd.
    """
    root = Path(tempfile.mkdtemp(prefix="fuzz_agent_"))
    deep = root.joinpath(*[f"l{i}" for i in range(8)])
    deep.mkdir(parents=True)
    (deep / "hello.txt").write_text("hello world\nfoo bar\nhello again\n", encoding="utf-8")
    sub = deep / "sub"
    sub.mkdir()
    (sub / "inner.txt").write_text("inner data\n", encoding="utf-8")
    prev = Path.cwd()
    os.chdir(deep)
    try:
        yield root
    finally:
        os.chdir(prev)
        shutil.rmtree(root, ignore_errors=True)


@pytest.fixture(scope="module", autouse=True)
def _ledger() -> Iterator[None]:
    yield
    summary = ledger_summary()
    print("\n" + summary)
    try:
        LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
        LEDGER_FILE.write_text(summary, encoding="utf-8")
    except OSError:
        pass


def _wt_valid(root: Path) -> list[str]:
    pool = [str(root / f"wt{i}") for i in range(4)]
    for wt in pool[:2]:
        Path(wt).mkdir(exist_ok=True)
    return pool


def _wt_hostile(root: Path) -> list[Any]:
    return [
        "", ".", "..", "../..", "..\\..\\..\\fuzzleaf", "a\x00b", "null\x00byte",
        "unicode_\u00fc_\U0001f4a9", "X" * 5000, " " * 300,
        str(root / "missing" / "deep"), None, 123, b"bytes", EVIL, THROWS,
    ]


def _mixed_wt(root: Path) -> list[Any]:
    valid = _wt_valid(root)
    return valid * 3 + _wt_hostile(root)


def _fail(report: Any) -> None:
    assert report.iterations == N, f"{report.label}: {report.iterations} != {N}"
    assert report.ok, report.summary()


def _corrupt(wt: Any, filename: str) -> None:
    """Occasionally poison on-disk state to fuzz the load paths."""
    with contextlib.suppress(Exception):
        target = Path(wt) / ".school" / "agent"
        target.mkdir(parents=True, exist_ok=True)
        garbage = ["{not json", "[1, 2,", '{"a": ', "\x00\xff", "null", "123"][len(filename) % 6]
        (target / filename).write_text(garbage, encoding="utf-8", errors="replace")


# --------------------------------------------------------------------------
# 1) school_observe
# --------------------------------------------------------------------------


class TestObserveFuzz:
    def test_observe(self, sandbox: Path) -> None:
        wt = _mixed_wt(sandbox)

        def make_args(i: int) -> tuple[tuple, dict]:
            return (
                (wt[i % len(wt)], OBS_POOL[i % len(OBS_POOL)]),
                {
                    "category": CAT_POOL[(i // 2) % len(CAT_POOL)],
                    "evidence": EV_POOL[(i // 3) % len(EV_POOL)],
                },
            )

        _fail(fuzz_fail_open(observe, N, make_args, "school_observe", _check_observe))

    def test_observe_category(self, sandbox: Path) -> None:
        wt = _wt_valid(sandbox)

        def make_args(i: int) -> tuple[tuple, dict]:
            return (
                (wt[i % len(wt)], f"observation {i}"),
                {"category": CAT_POOL[i % len(CAT_POOL)], "evidence": {"i": i}},
            )

        _fail(fuzz_fail_open(observe, N, make_args, "school_observe.category", _check_observe))

    def test_observe_evidence(self, sandbox: Path) -> None:
        wt = _wt_valid(sandbox)

        def make_args(i: int) -> tuple[tuple, dict]:
            evidence = (
                gen_value(rng=random.Random(i))
                if i % 3 == 0
                else EV_POOL[i % len(EV_POOL)]
            )
            return (
                (wt[i % len(wt)], f"evidence probe {i}"),
                {"category": "pattern", "evidence": evidence},
            )

        _fail(fuzz_fail_open(observe, N, make_args, "school_observe.evidence", _check_observe))

    def test_observe_worktree(self, sandbox: Path) -> None:
        wt = _wt_hostile(sandbox)

        def make_args(i: int) -> tuple[tuple, dict]:
            return ((wt[i % len(wt)], "worktree probe"), {"category": "pattern"})

        _fail(fuzz_fail_open(observe, N, make_args, "school_observe.worktree", _check_observe))


# --------------------------------------------------------------------------
# 2) school_goal — 8 actions + hostile params
# --------------------------------------------------------------------------


class TestGoalFuzz:
    def _run(
        self,
        sandbox: Path,
        action: Any,
        label: str,
        seed: bool = False,
    ) -> None:
        wt = _mixed_wt(sandbox)

        def make_args(i: int) -> tuple[tuple, dict]:
            if seed and i % 5 == 0:
                with contextlib.suppress(Exception):
                    goal(wt[i % len(wt)], "set", goal_id="g1", objective="seeded")
            return (
                (wt[i % len(wt)], action),
                {
                    "goal_id": GID_POOL[i % len(GID_POOL)],
                    "objective": OBJ_POOL[(i // 2) % len(OBJ_POOL)],
                    "success_criteria": SC_POOL[(i // 3) % len(SC_POOL)],
                    "max_turns": MT_POOL[(i // 5) % len(MT_POOL)],
                    "constraints": CON_POOL[(i // 7) % len(CON_POOL)],
                },
            )

        _fail(fuzz_fail_open(goal, N, make_args, label, _check_goal))

    def test_goal_set(self, sandbox: Path) -> None:
        self._run(sandbox, "set", "school_goal.set")

    def test_goal_status(self, sandbox: Path) -> None:
        self._run(sandbox, "status", "school_goal.status")

    def test_goal_complete(self, sandbox: Path) -> None:
        self._run(sandbox, "complete", "school_goal.complete", seed=True)

    def test_goal_block(self, sandbox: Path) -> None:
        self._run(sandbox, "block", "school_goal.block", seed=True)

    def test_goal_pause(self, sandbox: Path) -> None:
        self._run(sandbox, "pause", "school_goal.pause", seed=True)

    def test_goal_resume(self, sandbox: Path) -> None:
        self._run(sandbox, "resume", "school_goal.resume", seed=True)

    def test_goal_clear(self, sandbox: Path) -> None:
        self._run(sandbox, "clear", "school_goal.clear")

    def test_goal_history(self, sandbox: Path) -> None:
        self._run(sandbox, "history", "school_goal.history")

    def test_goal_params(self, sandbox: Path) -> None:
        wt = _mixed_wt(sandbox)
        actions = ["set", "status", "complete", "bogus", None, 123, EVIL, ["set"], "", "clear"]

        def make_args(i: int) -> tuple[tuple, dict]:
            worktree = wt[i % len(wt)]
            if i % 7 == 0:
                _corrupt(worktree, "goals.json")
            objective = (
                gen_value(rng=random.Random(i))
                if i % 4 == 0
                else OBJ_POOL[(i // 3) % len(OBJ_POOL)]
            )
            return (
                (worktree, actions[i % len(actions)]),
                {
                    "goal_id": GID_POOL[(i // 2) % len(GID_POOL)],
                    "objective": objective,
                    "success_criteria": SC_POOL[(i // 5) % len(SC_POOL)],
                    "max_turns": MT_POOL[i % len(MT_POOL)],
                    "constraints": CON_POOL[(i // 2) % len(CON_POOL)],
                },
            )

        _fail(fuzz_fail_open(goal, N, make_args, "school_goal.params", _check_goal))


# --------------------------------------------------------------------------
# 3) school_research
# --------------------------------------------------------------------------


class TestResearchFuzz:
    def test_research(self, sandbox: Path) -> None:
        wt = _mixed_wt(sandbox)

        def make_args(i: int) -> tuple[tuple, dict]:
            return (
                (wt[i % len(wt)], QUERY_POOL[i % len(QUERY_POOL)]),
                {
                    "depth": ["quick", "standard", "deep"][i % 3],
                    "fmt": ["summary", "detailed", "raw"][i % 3],
                    "cite": i % 2 == 0,
                },
            )

        _fail(fuzz_fail_open(research, N, make_args, "school_research", _check_research_shape))

    def test_research_depth(self, sandbox: Path) -> None:
        wt = _wt_valid(sandbox)

        def make_args(i: int) -> tuple[tuple, dict]:
            return (
                (wt[i % len(wt)], QUERY_POOL[(i // 2) % len(QUERY_POOL)]),
                {"depth": DEPTH_R_POOL[i % len(DEPTH_R_POOL)], "fmt": "summary", "cite": True},
            )

        _fail(
            fuzz_fail_open(
                research, N, make_args, "school_research.depth", _check_research_shape
            )
        )

    def test_research_fmt(self, sandbox: Path) -> None:
        wt = _wt_valid(sandbox)

        def make_args(i: int) -> tuple[tuple, dict]:
            return (
                (wt[i % len(wt)], QUERY_POOL[(i // 3) % len(QUERY_POOL)]),
                {"depth": "standard", "fmt": FMT_POOL[i % len(FMT_POOL)], "cite": True},
            )

        _fail(
            fuzz_fail_open(research, N, make_args, "school_research.fmt", _check_research_shape)
        )

    def test_research_cite(self, sandbox: Path) -> None:
        wt = _wt_valid(sandbox)

        def make_args(i: int) -> tuple[tuple, dict]:
            return (
                (wt[i % len(wt)], QUERY_POOL[(i // 5) % len(QUERY_POOL)]),
                {"depth": "quick", "fmt": "raw", "cite": CITE_POOL[i % len(CITE_POOL)]},
            )

        _fail(
            fuzz_fail_open(research, N, make_args, "school_research.cite", _check_research_shape)
        )


# --------------------------------------------------------------------------
# 4) school_explore
# --------------------------------------------------------------------------


class TestExploreFuzz:
    def test_explore(self, sandbox: Path) -> None:
        wt = _mixed_wt(sandbox)

        def make_args(i: int) -> tuple[tuple, dict]:
            return (
                (wt[i % len(wt)], TARGET_POOL[i % len(TARGET_POOL)]),
                {"depth": DEPTH_E_POOL[(i // 2) % len(DEPTH_E_POOL)],
                 "focus": FOCUS_POOL[(i // 3) % len(FOCUS_POOL)]},
            )

        _fail(fuzz_fail_open(explore, N, make_args, "school_explore", _check_explore_shape))

    def test_explore_depth(self, sandbox: Path) -> None:
        wt = _wt_valid(sandbox)

        def make_args(i: int) -> tuple[tuple, dict]:
            return (
                (wt[i % len(wt)], "." if i % 2 else "sub"),
                {"depth": DEPTH_E_POOL[i % len(DEPTH_E_POOL)], "focus": "structure"},
            )

        _fail(fuzz_fail_open(explore, N, make_args, "school_explore.depth", _check_explore_shape))

    def test_explore_focus(self, sandbox: Path) -> None:
        wt = _wt_valid(sandbox)

        def make_args(i: int) -> tuple[tuple, dict]:
            return (
                (wt[i % len(wt)], "." if i % 2 else "hello.txt"),
                {"depth": "file", "focus": FOCUS_POOL[i % len(FOCUS_POOL)]},
            )

        _fail(fuzz_fail_open(explore, N, make_args, "school_explore.focus", _check_explore_shape))

    def test_explore_missing_target(self, sandbox: Path) -> None:
        wt = _wt_valid(sandbox)
        missing = [
            "does-not-exist", "missing/deep/nested", "a\x00b", "", None, 123,
            EVIL, "X" * 5000, "..\\..\\..\\nowhere", b"x", "\U0001f4a9" * 50, THROWS,
        ]

        def make_args(i: int) -> tuple[tuple, dict]:
            return ((wt[i % len(wt)], missing[i % len(missing)]), {"depth": "file"})

        _fail(
            fuzz_fail_open(
                explore, N, make_args, "school_explore.missing_target", _check_explore_shape
            )
        )


# --------------------------------------------------------------------------
# 5) school_progress
# --------------------------------------------------------------------------


class TestProgressFuzz:
    def test_progress_write(self, sandbox: Path) -> None:
        wt = _mixed_wt(sandbox)
        good = [
            [{"content": "a", "status": "completed"}],
            [{"content": "b", "status": "in_progress"}],
            [{"content": "c", "status": "pending"}],
            [{"content": "d", "status": "completed"}, {"content": "e"}],
        ]

        def make_args(i: int) -> tuple[tuple, dict]:
            return (
                (wt[i % len(wt)], "write"),
                {
                    "items": good[i % len(good)],
                    "context": CONTEXT_POOL[(i // 2) % len(CONTEXT_POOL)],
                },
            )

        report = fuzz_fail_open(
            progress, N, make_args, "school_progress.write", _check_progress_shape
        )
        _fail(report)

    def test_progress_read(self, sandbox: Path) -> None:
        wt = _mixed_wt(sandbox)

        def make_args(i: int) -> tuple[tuple, dict]:
            if i % 3 == 0:
                with contextlib.suppress(Exception):
                    progress(
                        wt[i % len(wt)], "write", items=[{"content": "seed", "status": "done"}]
                    )
            return ((wt[i % len(wt)], "read"), {"context": CONTEXT_POOL[i % len(CONTEXT_POOL)]})

        _fail(fuzz_fail_open(progress, N, make_args, "school_progress.read", _check_progress_shape))

    def test_progress_items(self, sandbox: Path) -> None:
        wt = _wt_valid(sandbox)

        def make_args(i: int) -> tuple[tuple, dict]:
            action = "write" if i % 2 else "read"
            items = (
                gen_value(rng=random.Random(i))
                if i % 3 == 0
                else ITEMS_POOL[i % len(ITEMS_POOL)]
            )
            return ((wt[i % len(wt)], action), {"items": items, "context": ""})

        report = fuzz_fail_open(
            progress, N, make_args, "school_progress.items", _check_progress_shape
        )
        _fail(report)


# --------------------------------------------------------------------------
# 6) school_session
# --------------------------------------------------------------------------


class TestSessionFuzz:
    def _run(
        self,
        sandbox: Path,
        action: str,
        label: str,
        seed: bool = False,
    ) -> None:
        wt = _mixed_wt(sandbox)

        def make_args(i: int) -> tuple[tuple, dict]:
            if seed and i % 4 == 0:
                with contextlib.suppress(Exception):
                    session(wt[i % len(wt)], "create", session_id="s1", focus="seeded")
            return (
                (wt[i % len(wt)], action),
                {
                    "session_id": SID_POOL[i % len(SID_POOL)],
                    "focus": FOCUS_S_POOL[(i // 2) % len(FOCUS_S_POOL)],
                },
            )

        _fail(fuzz_fail_open(session, N, make_args, label, _check_session))

    def test_session_create(self, sandbox: Path) -> None:
        self._run(sandbox, "create", "school_session.create")

    def test_session_resume(self, sandbox: Path) -> None:
        self._run(sandbox, "resume", "school_session.resume", seed=True)

    def test_session_summarize(self, sandbox: Path) -> None:
        self._run(sandbox, "summarize", "school_session.summarize", seed=True)

    def test_session_export(self, sandbox: Path) -> None:
        self._run(sandbox, "export", "school_session.export", seed=True)

    def test_session_list(self, sandbox: Path) -> None:
        self._run(sandbox, "list", "school_session.list")

    def test_session_params(self, sandbox: Path) -> None:
        wt = _mixed_wt(sandbox)
        actions = ["create", "list", "resume", "teleport", None, 123, EVIL, ["list"], "", "export"]

        def make_args(i: int) -> tuple[tuple, dict]:
            return (
                (wt[i % len(wt)], actions[i % len(actions)]),
                {
                    "session_id": SID_POOL[(i // 2) % len(SID_POOL)],
                    "focus": FOCUS_S_POOL[(i // 3) % len(FOCUS_S_POOL)],
                },
            )

        _fail(fuzz_fail_open(session, N, make_args, "school_session.params", _check_session))


# --------------------------------------------------------------------------
# 7) school_execute
# --------------------------------------------------------------------------


class TestExecuteFuzz:
    def test_execute(self, sandbox: Path) -> None:
        wt = _wt_valid(sandbox)

        def make_args(i: int) -> tuple[tuple, dict]:
            return (
                (wt[i % len(wt)], COMMAND_POOL[i % len(COMMAND_POOL)]),
                {"timeout_ms": 5000, "learn": i % 2 == 0, "max_output": 500},
            )

        _fail(fuzz_fail_open(execute, N, make_args, "school_execute", _check_execute))

    def test_execute_cwd(self, sandbox: Path) -> None:
        wt = _wt_valid(sandbox)
        cwd_pool: list[Any] = [
            None, wt[0], str(sandbox), str(Path.cwd() / "sub"), str(sandbox / "nope"),
            "a\x00b", "", ".", "..", 123, b"x", EVIL, "X" * 3000, THROWS,
        ]

        def make_args(i: int) -> tuple[tuple, dict]:
            return (
                (wt[i % len(wt)], "rem" if i % 4 else "echo cwd"),
                {"cwd": cwd_pool[i % len(cwd_pool)], "timeout_ms": 5000, "learn": False},
            )

        _fail(fuzz_fail_open(execute, N, make_args, "school_execute.cwd", _check_execute))

    def test_execute_env(self, sandbox: Path) -> None:
        wt = _wt_valid(sandbox)

        def make_args(i: int) -> tuple[tuple, dict]:
            return (
                (wt[i % len(wt)], "rem" if i % 4 else "echo %PATH%"),
                {"env": ENV_POOL[i % len(ENV_POOL)], "timeout_ms": 5000, "learn": False},
            )

        _fail(fuzz_fail_open(execute, N, make_args, "school_execute.env", _check_execute))

    def test_execute_timeout_ms(self, sandbox: Path) -> None:
        wt = _wt_valid(sandbox)
        cmds = ["rem", "rem", "", "echo t"]

        def make_args(i: int) -> tuple[tuple, dict]:
            return (
                (wt[i % len(wt)], cmds[i % len(cmds)]),
                {"timeout_ms": TIMEOUT_POOL[i % len(TIMEOUT_POOL)], "learn": False},
            )

        _fail(fuzz_fail_open(execute, N, make_args, "school_execute.timeout_ms", _check_execute))

    def test_execute_learn(self, sandbox: Path) -> None:
        wt = _wt_valid(sandbox)
        cmds = ["rem", "echo learn", "", "rem"]

        def make_args(i: int) -> tuple[tuple, dict]:
            return (
                (wt[i % len(wt)], cmds[i % len(cmds)]),
                {"learn": LEARN_POOL[i % len(LEARN_POOL)], "timeout_ms": 5000},
            )

        _fail(fuzz_fail_open(execute, N, make_args, "school_execute.learn", _check_execute))

    def test_execute_context(self, sandbox: Path) -> None:
        wt = _wt_valid(sandbox)
        cmds = ["rem", "echo ctx", "", "rem"]

        def make_args(i: int) -> tuple[tuple, dict]:
            return (
                (wt[i % len(wt)], cmds[i % len(cmds)]),
                {"context": CONTEXT_POOL[i % len(CONTEXT_POOL)], "timeout_ms": 5000, "learn": True},
            )

        _fail(fuzz_fail_open(execute, N, make_args, "school_execute.context", _check_execute))

    def test_execute_max_output(self, sandbox: Path) -> None:
        wt = _wt_valid(sandbox)
        cmds = ["echo " + "y" * 400, "rem", "", "echo short"]

        def make_args(i: int) -> tuple[tuple, dict]:
            return (
                (wt[i % len(wt)], cmds[i % len(cmds)]),
                {
                    "max_output": MAXOUT_POOL[i % len(MAXOUT_POOL)],
                    "timeout_ms": 5000,
                    "learn": False,
                },
            )

        _fail(fuzz_fail_open(execute, N, make_args, "school_execute.max_output", _check_execute))


# --------------------------------------------------------------------------
# 8) school_navigate
# --------------------------------------------------------------------------


class TestNavigateFuzz:
    def test_navigate_read(self, sandbox: Path) -> None:
        wt = _mixed_wt(sandbox)

        def make_args(i: int) -> tuple[tuple, dict]:
            return ((wt[i % len(wt)], "read", PATH_POOL[i % len(PATH_POOL)]), {})

        _fail(fuzz_fail_open(navigate, N, make_args, "school_navigate.read", _check_navigate_shape))

    def test_navigate_list(self, sandbox: Path) -> None:
        wt = _mixed_wt(sandbox)

        def make_args(i: int) -> tuple[tuple, dict]:
            return ((wt[i % len(wt)], "list", PATH_POOL[i % len(PATH_POOL)]), {})

        _fail(fuzz_fail_open(navigate, N, make_args, "school_navigate.list", _check_navigate_shape))

    def test_navigate_search(self, sandbox: Path) -> None:
        wt = _mixed_wt(sandbox)

        def make_args(i: int) -> tuple[tuple, dict]:
            return (
                (wt[i % len(wt)], "search", "." if i % 2 else ""),
                {"pattern": PATTERN_POOL[i % len(PATTERN_POOL)], "depth": 2},
            )

        report = fuzz_fail_open(
            navigate, N, make_args, "school_navigate.search", _check_navigate_shape
        )
        _fail(report)

    def test_navigate_map(self, sandbox: Path) -> None:
        wt = _mixed_wt(sandbox)

        def make_args(i: int) -> tuple[tuple, dict]:
            return (
                (wt[i % len(wt)], "map", PATH_POOL[(i // 2) % len(PATH_POOL)]),
                {"depth": DEPTH_N_POOL[i % len(DEPTH_N_POOL)]},
            )

        _fail(fuzz_fail_open(navigate, N, make_args, "school_navigate.map", _check_navigate_shape))

    def test_navigate_pattern(self, sandbox: Path) -> None:
        wt = _wt_valid(sandbox)

        def make_args(i: int) -> tuple[tuple, dict]:
            return (
                (wt[i % len(wt)], "search", "."),
                {"pattern": PATTERN_POOL[i % len(PATTERN_POOL)], "depth": 1},
            )

        _fail(
            fuzz_fail_open(navigate, N, make_args, "school_navigate.pattern", _check_navigate_shape)
        )

    def test_navigate_depth(self, sandbox: Path) -> None:
        wt = _wt_valid(sandbox)
        actions = ["map", "map", "list", "search", "map"]

        def make_args(i: int) -> tuple[tuple, dict]:
            return (
                (wt[i % len(wt)], actions[i % len(actions)], "."),
                {"depth": DEPTH_N_POOL[i % len(DEPTH_N_POOL)], "pattern": "x"},
            )

        _fail(
            fuzz_fail_open(navigate, N, make_args, "school_navigate.depth", _check_navigate_shape)
        )

    def test_navigate_path(self, sandbox: Path) -> None:
        wt = _mixed_wt(sandbox)
        actions = ["read", "list", "search", "map"]

        def make_args(i: int) -> tuple[tuple, dict]:
            return (
                (wt[i % len(wt)], actions[i % len(actions)], PATH_POOL[(i // 2) % len(PATH_POOL)]),
                {"pattern": PATTERN_POOL[(i // 3) % len(PATTERN_POOL)], "depth": 2},
            )

        _fail(fuzz_fail_open(navigate, N, make_args, "school_navigate.path", _check_navigate_shape))


# --------------------------------------------------------------------------
# 9) school_workflow
# --------------------------------------------------------------------------


class TestWorkflowFuzz:
    def _run(self, sandbox: Path, action: str, label: str, seed: bool = False) -> None:
        wt = _mixed_wt(sandbox)
        names = ["tdd", "debug", "brainstorm", "review", "deploy", "bogus"]

        def make_args(i: int) -> tuple[tuple, dict]:
            name = names[i % len(names)]
            if seed and i % 4 == 0:
                with contextlib.suppress(Exception):
                    workflow(wt[i % len(wt)], name, action="start")
            return (
                (wt[i % len(wt)], name, action),
                {
                    "phase": PHASE_POOL[(i // 2) % len(PHASE_POOL)],
                    "notes": NOTES_POOL[(i // 3) % len(NOTES_POOL)],
                },
            )

        _fail(fuzz_fail_open(workflow, N, make_args, label, _check_workflow_shape))

    def test_workflow_start(self, sandbox: Path) -> None:
        self._run(sandbox, "start", "school_workflow.start")

    def test_workflow_advance(self, sandbox: Path) -> None:
        self._run(sandbox, "advance", "school_workflow.advance", seed=True)

    def test_workflow_status(self, sandbox: Path) -> None:
        self._run(sandbox, "status", "school_workflow.status")

    def test_workflow_abort(self, sandbox: Path) -> None:
        self._run(sandbox, "abort", "school_workflow.abort", seed=True)

    def test_workflow_list(self, sandbox: Path) -> None:
        self._run(sandbox, "list", "school_workflow.list")

    def test_workflow_define(self, sandbox: Path) -> None:
        self._run(sandbox, "define", "school_workflow.define")

    def test_workflow_block(self, sandbox: Path) -> None:
        self._run(sandbox, "block", "school_workflow.block", seed=True)

    def test_workflow_name(self, sandbox: Path) -> None:
        wt = _mixed_wt(sandbox)
        actions = ["start", "status", "advance", "abort", "list", "define", "block", "bogus"]

        def make_args(i: int) -> tuple[tuple, dict]:
            return (
                (wt[i % len(wt)], WF_NAME_POOL[i % len(WF_NAME_POOL)], actions[i % len(actions)]),
                {"phase": "one,two", "notes": "n"},
            )

        _fail(fuzz_fail_open(workflow, N, make_args, "school_workflow.name", _check_workflow_shape))

    def test_workflow_params(self, sandbox: Path) -> None:
        wt = _mixed_wt(sandbox)
        actions = ["start", "advance", "define", "status"]

        def make_args(i: int) -> tuple[tuple, dict]:
            worktree = wt[i % len(wt)]
            if i % 6 == 0:
                _corrupt(worktree, "workflows.json")
            if i % 11 == 0:
                _corrupt(worktree, "workflow_defs.json")
            notes = (
                gen_value(rng=random.Random(i))
                if i % 5 == 0
                else NOTES_POOL[(i // 2) % len(NOTES_POOL)]
            )
            return (
                (worktree, ["tdd", "debug", "deploy"][i % 3], actions[i % len(actions)]),
                {
                    "phase": PHASE_POOL[i % len(PHASE_POOL)],
                    "notes": notes,
                },
            )

        _fail(
            fuzz_fail_open(workflow, N, make_args, "school_workflow.params", _check_workflow_shape)
        )

    def test_workflow_register(self) -> None:
        def make_args(i: int) -> tuple[tuple, dict]:
            phases = REG_PHASES_POOL[(i // 2) % len(REG_PHASES_POOL)]
            return ((WF_NAME_POOL[i % len(WF_NAME_POOL)], phases), {})

        report = fuzz_fail_open(
            register_workflow, N, make_args, "school_workflow.register", _check_register
        )
        _fail(report)


# --------------------------------------------------------------------------
# 10) school_fetch_docs (network stubbed: deterministic, no real traffic)
# --------------------------------------------------------------------------


class _FakeResp:
    def __init__(self, text: str) -> None:
        self._data = text.encode("utf-8", "replace")

    def read(self) -> bytes:
        return self._data

    def __enter__(self) -> _FakeResp:
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False


def _fake_urlopen(req: Any, timeout: float = 5.0, **_: Any) -> _FakeResp:
    url = getattr(req, "full_url", None) or str(req)
    if "boom" in url or len(url) % 7 == 0:
        raise urllib.error.URLError("fuzz offline")
    return _FakeResp(f"docs {url}" + " body" * (len(url) % 400))


@pytest.fixture()
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)


class TestFetchDocsFuzz:
    def test_fetch_docs(self, sandbox: Path, no_network: None) -> None:
        wt = _mixed_wt(sandbox)

        def make_args(i: int) -> tuple[tuple, dict]:
            return (
                (wt[i % len(wt)], QUERY_POOL[i % len(QUERY_POOL)]),
                {"use_cache": i % 2 == 0},
            )

        _fail(fuzz_fail_open(fetch_docs, N, make_args, "school_fetch_docs", _check_doc))

    def test_fetch_docs_library(self, sandbox: Path, no_network: None) -> None:
        wt = _wt_valid(sandbox)

        def make_args(i: int) -> tuple[tuple, dict]:
            return (
                (wt[i % len(wt)], f"query-{i}"),
                {"library": LIB_POOL[i % len(LIB_POOL)], "use_cache": True},
            )

        _fail(fuzz_fail_open(fetch_docs, N, make_args, "school_fetch_docs.library", _check_doc))

    def test_fetch_docs_version(self, sandbox: Path, no_network: None) -> None:
        wt = _wt_valid(sandbox)

        def make_args(i: int) -> tuple[tuple, dict]:
            return (
                (wt[i % len(wt)], f"query-{i}"),
                {
                    "library": "requests",
                    "version": VER_POOL[i % len(VER_POOL)],
                    "use_cache": True,
                },
            )

        _fail(fuzz_fail_open(fetch_docs, N, make_args, "school_fetch_docs.version", _check_doc))

    def test_fetch_docs_use_cache(self, sandbox: Path, no_network: None) -> None:
        wt = _wt_valid(sandbox)

        def make_args(i: int) -> tuple[tuple, dict]:
            worktree = wt[i % len(wt)]
            if i % 5 == 0:
                _corrupt(worktree, "docs_cache.json")
            use = USE_CACHE_POOL[i % len(USE_CACHE_POOL)]
            return ((worktree, f"cache-q-{i % 40}"), {"use_cache": use})

        _fail(fuzz_fail_open(fetch_docs, N, make_args, "school_fetch_docs.use_cache", _check_doc))


# --------------------------------------------------------------------------
# 11) result dataclass field surfaces
# --------------------------------------------------------------------------


class TestResultFieldSurfaces:
    def _surface(self, cls: type, label: str) -> None:
        field_names = [f.name for f in fields(cls)]

        def make_args(i: int) -> tuple[tuple, dict]:
            kwargs = {name: HOSTILE[(i + j) % len(HOSTILE)] for j, name in enumerate(field_names)}
            return ((cls,), kwargs)

        def check(obj: Any) -> None:
            assert isinstance(obj, cls)
            for name in field_names:
                assert hasattr(obj, name)

        _fail(fuzz_fail_open(lambda c, **kw: c(**kw), N, make_args, label, check))

    def test_workflow_result_fields(self) -> None:
        self._surface(WorkflowResult, "school_result_fields.workflow")

    def test_doc_result_fields(self) -> None:
        self._surface(DocResult, "school_result_fields.doc")

    def test_research_result_fields(self) -> None:
        self._surface(ResearchResult, "school_result_fields.research")

    def test_execute_result_fields(self) -> None:
        self._surface(ExecuteResult, "school_result_fields.execute")
