"""Adversarial fuzz campaign: School memory + routing tool suite.

Exercises EVERY tool and feature 2000 times each with failure-seeking inputs
(wrong types for every parameter, NUL bytes, huge payloads, unicode, cyclic
structures, NaN/inf, path traversal, corrupt JSONL state) against the
FAIL-OPEN invariant: tool boundaries return a result object and NEVER raise.

Ownership: crashes in core/routing/v26/** (owned) are fixed in place.
Crashes that trace to NON-OWNED files (school/mcp/server.py, core/learner,
core/skillgen, core/routing/v26/memory_*.py internals) are recorded in
NON_OWNED_FINDINGS and allowed only via KNOWN_NON_OWNED signatures; any NEW
signature fails the run.

Ledger: tests/stress/fuzz_harness.py accumulates per-label iteration counts;
test_zz_ledger_summary prints and enforces 2000 iterations per feature.
"""

from __future__ import annotations

import atexit
import json
import pathlib
import shutil
import sys
import tempfile
import traceback
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from fuzz_harness import (  # noqa: E402
    HOSTILE,
    fuzz_fail_open,
    gen_json_safe,
    gen_value,
    ledger_summary,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.learner.feature_extractor import FeatureExtractor  # noqa: E402
from core.routing.v26.experience import Experience, ExperienceOutcome  # noqa: E402
from core.routing.v26.identity import (  # noqa: E402
    AgentIdentity,
    MemoryScope,
    ProjectIdentity,
    SessionIdentity,
    coerce_float,
    coerce_int,
    coerce_mapping,
    coerce_tag_set,
    coerce_text,
)
from core.routing.v26.memory_manager import MemoryManager  # noqa: E402
from core.routing.v26.memory_store import MemoryStore  # noqa: E402
from core.routing.v26.memory_types import (  # noqa: E402
    MemoryEntry,
    MemoryKind,
    MemoryRequest,
    MemoryResponse,
)
from core.routing.v26.orchestrator import Orchestrator  # noqa: E402
from core.routing.v26.persistence import PersistenceError, ScopeIsolatedStorage  # noqa: E402
from core.routing.v26.security import (  # noqa: E402
    detect_injection,
    enforce_instruction_boundary,
    validate_memory_content,
    validate_memory_request,
    validate_scope_access,
)
from core.routing.v26.semantic_retrieval import scored_query  # noqa: E402
from core.routing.v26.tools.base import ToolRegistry, ToolResult  # noqa: E402
from core.routing.v26.tools.confidence import ConfidenceTool  # noqa: E402
from core.routing.v26.tools.conflict import ConflictDetectionTool  # noqa: E402
from core.routing.v26.tools.deduplicate import DeduplicateTool  # noqa: E402
from core.routing.v26.tools.diagnose import DiagnoseTool  # noqa: E402
from core.routing.v26.tools.knowledge import KnowledgeExtractionTool  # noqa: E402
from core.routing.v26.tools.lifecycle import LifecycleTool  # noqa: E402
from core.routing.v26.tools.recall import RecallTool  # noqa: E402
from core.routing.v26.tools.remember import RememberTool  # noqa: E402
from core.routing.v26.tools.semantic_search import SemanticSearchTool  # noqa: E402
from core.routing.v26.tools.status import StatusTool  # noqa: E402

N = 2000  # iterations per tool.feature label

# ---------------------------------------------------------------------------
# Non-owned finding registry (bugs we may record but must not edit away)
# ---------------------------------------------------------------------------

#: signature -> hit count (raised inside files we do not own)
NON_OWNED_FINDINGS: dict[str, int] = {}

#: Signatures confirmed as non-owned bugs and reported upstream. A NEW
#: signature (not in this set) raises and fails the campaign.
KNOWN_NON_OWNED: set[str] = {
    # school/mcp/server.py:_call_route line ~1473 — `arguments.get("outcome")
    # in {"helpful", "useless", "neutral"}` raises TypeError for JSON list/
    # dict outcomes (unhashable). Reachable from valid MCP JSON input
    # (school_route mode=report, outcome: []). NON-OWNED: recorded only.
    "TypeError:school/mcp/server.py:_call_route",
    # core/routing/v26/memory_types.py MemoryEntry.to_dict — `sorted(self.tags)`
    # raises TypeError for mixed-type tags left by corrupt persistence state.
    # NON-OWNED: defensively wrapped at owned tool boundaries (safe_memory_dict).
    "TypeError:core/routing/v26/memory_types.py:to_dict",
}

_LEDGER_PATH = pathlib.Path(tempfile.gettempdir()) / "opencode" / "fuzz_ledger.txt"


def _finding_signature(exc: BaseException) -> str:
    """Signature of the deepest project-code frame (outside tests) that raised."""
    frames = traceback.extract_tb(exc.__traceback__)
    project = []
    for f in frames:
        try:
            rel = pathlib.Path(f.filename).resolve().relative_to(REPO_ROOT)
        except ValueError:
            continue  # stdlib / site-packages
        parts = rel.parts
        if parts and parts[0] == "tests":
            continue
        project.append((rel, f.name))
    if project:
        rel, name = project[-1]
        where = f"{rel.as_posix()}:{name}"
    else:
        where = f"{type(exc).__name__}:external"
    return f"{type(exc).__name__}:{where}"


def _record_finding(exc: BaseException) -> str:
    sig = _finding_signature(exc)
    if sig not in KNOWN_NON_OWNED:
        raise AssertionError(f"NEW non-owned crash signature: {sig}") from exc
    NON_OWNED_FINDINGS[sig] = NON_OWNED_FINDINGS.get(sig, 0) + 1
    return sig


def _mcp_call(fn, *args, **kwargs) -> dict:
    """Call a NON-OWNED school/mcp helper fail-open.

    The MCP route tools have a documented ValueError contract (missing
    situation/severity/lesson) which is a graceful outcome. Any other raise
    is a bug in a non-owned file: record known signatures, fail on new ones.
    """
    try:
        result = fn(*args, **kwargs)
    except ValueError as exc:  # documented contract for school_route
        return {"documented_error": f"{type(exc).__name__}: {str(exc)[:80]}"}
    except Exception as exc:  # noqa: BLE001 - record non-owned bugs
        return {"recorded_non_owned_bug": _record_finding(exc)}
    return {"ok": True, "kind": type(result).__name__}


def _mcp_call_strict(fn, *args, **kwargs) -> dict:
    """Like _mcp_call but with NO documented-exception allowance."""
    try:
        result = fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - record non-owned bugs
        return {"recorded_non_owned_bug": _record_finding(exc)}
    return {"ok": True, "kind": type(result).__name__}


# ---------------------------------------------------------------------------
# Temp worktrees (OneDrive-safe: tempfile.mkdtemp + atexit shutil.rmtree)
# ---------------------------------------------------------------------------

_WORKTREES: list[str] = []


def _make_worktree() -> str:
    wt = tempfile.mkdtemp(prefix="school-fuzz-")
    _WORKTREES.append(wt)
    return wt


def _cleanup_worktrees() -> None:
    for wt in _WORKTREES:
        shutil.rmtree(wt, ignore_errors=True)


atexit.register(_cleanup_worktrees)

WT_A = _make_worktree()
WT_B = _make_worktree()
WT_POOL = [WT_A, WT_B]

# ---------------------------------------------------------------------------
# Adversarial value pools (deterministic pick per iteration)
# ---------------------------------------------------------------------------


def _v(pool, i: int, salt: int = 0) -> Any:
    return pool[(i * 3 + salt) % len(pool)]


_TEXT_POOL: list[Any] = [
    "hello world",
    "python is dynamically typed",
    "quick brown fox and the lazy dog",
    "a b c d e f g h",
    "répétition ünïcödé \U0001f4a9",
    "null\x00byte",
    "line\nbreaks\ttabbed",
    "",
] + [h for h in HOSTILE]

_ID_POOL: list[Any] = [
    "agent1", "proj1", "sess1", "default", "a" * 300, "id\x00x", "ünïcödé", "", "0",
] + HOSTILE

_NUM_POOL: list[Any] = [
    0, -1, 1, 0.5, -0.5, 0.8, 2, 0.0, 1.0, -0.0, 99999, -99999, 10**50, -(10**50),
    float("nan"), float("inf"), float("-inf"), 2**63, 3.14, -3.14,
    "5", "x", "", None, True, False, [1], {"a": 1}, complex(1, 2), slice(1, 2),
]

_TAGS_POOL: list[Any] = [
    [], ["a"], ["python", "bugfix"], [1, "a"], [""] , "notalist", None,
    (1, 2), {1: 2}, {"a": 1}, set(), [None], gen_value(depth=3),
]

_OUTCOME_POOL: list[Any] = [
    "SUCCESS", "FAILURE", "NEUTRAL", "MIXED", "success", "INVALID", "", None,
    123, ["SUCCESS"], {"a": 1}, b"SUCCESS", gen_value(depth=3),
] + HOSTILE

_ACTION_POOL: list[Any] = [
    "score", "decay", "promote", "archive", "SCORE", "invalid", "", None,
    0, ["score"], {"a": 1}, gen_value(depth=3),
] + HOSTILE

# ---------------------------------------------------------------------------
# Shared toolset (in-memory, seeded with valid + adversarial entries)
# ---------------------------------------------------------------------------


def _seed_entries(store: MemoryStore, manager: MemoryManager) -> None:
    agent = AgentIdentity.create(agent_id="agent1")
    scope = MemoryScope(agent=agent)
    for i in range(4):
        entry = MemoryEntry.create(
            content=f"memory {i} about python and testing",
            kind=MemoryKind.EPISODIC,
            scope=scope,
            confidence=0.5 + 0.1 * i,
        )
        manager.store_memory(entry)
    # Adversarial-but-stored entries (corrupt state simulation): these must
    # never break the read path (to_dict may degrade to a stub).
    store.store(WEIRD_TAGS_ENTRY)
    store.store(WEIRD_CONTENT_ENTRY)


WEIRD_TAGS_ENTRY = MemoryEntry(
    memory_id="weird-tags",
    content="weird tags entry with several shared words",
    kind=MemoryKind.EPISODIC,
    scope=MemoryScope(agent=AgentIdentity.create(agent_id="agent1")),
    timestamp=1000.0,
    tags=frozenset({1, "a", 2.0}),
    confidence=0.4,
)
WEIRD_CONTENT_ENTRY = MemoryEntry(
    memory_id="weird-content",
    content=12345,
    kind=MemoryKind.EPISODIC,
    scope=MemoryScope(agent=AgentIdentity.create(agent_id="agent1")),
    timestamp=float("nan"),
    confidence=0.6,
)


STORE = MemoryStore()
MANAGER = MemoryManager(store=STORE)
_seed_entries(STORE, MANAGER)
EXTRACTOR = FeatureExtractor()

REMEMBER = RememberTool(MANAGER)
RECALL = RecallTool(MANAGER)
SEARCH = SemanticSearchTool(STORE, EXTRACTOR)
CONFLICT = ConflictDetectionTool(MANAGER)
CONFIDENCE = ConfidenceTool()
DEDUP = DeduplicateTool(STORE, EXTRACTOR)
KNOWLEDGE = KnowledgeExtractionTool(MANAGER)
LIFECYCLE = LifecycleTool(MANAGER)
STATUS = StatusTool()
DIAGNOSE = DiagnoseTool(MANAGER)

REGISTRY = ToolRegistry()
for _tool in (
    STATUS, REMEMBER, RECALL, SEARCH, CONFLICT, CONFIDENCE,
    DEDUP, KNOWLEDGE, LIFECYCLE, DIAGNOSE,
):
    REGISTRY.register(_tool)
ORCH = Orchestrator(REGISTRY)

VALID_ENTRY = MemoryEntry.create(
    content="a perfectly valid memory entry",
    kind=MemoryKind.EPISODIC,
    scope=MemoryScope(agent=AgentIdentity.create(agent_id="agent1")),
)
VALID_EXPERIENCE = Experience.create(
    agent=AgentIdentity.create(agent_id="agent1"),
    observation="observed something",
    action="did something",
    outcome=ExperienceOutcome.SUCCESS,
)


# ---------------------------------------------------------------------------
# Invariant checks
# ---------------------------------------------------------------------------


def _check_tool_result(result: Any) -> None:
    assert isinstance(result, ToolResult), f"not ToolResult: {type(result).__name__}"
    assert isinstance(result.success, bool)
    assert isinstance(result.data, dict)
    assert isinstance(result.errors, list)
    assert all(isinstance(e, str) for e in result.errors)
    assert isinstance(result.metadata, dict)
    result.to_dict()


def _check_conf_result(result: Any) -> None:
    _check_tool_result(result)
    if result.success:
        band = result.data.get("band")
        assert band in {"high", "moderate", "low", "weak", "minimal"}, f"band={band!r}"
        conf = result.data.get("confidence")
        assert isinstance(conf, float) and 0.0 <= conf <= 1.0, f"confidence={conf!r}"


def _check_bool_str(result: Any) -> None:
    ok, reason = result
    assert isinstance(ok, bool), f"not (bool, str): {result!r}"
    assert isinstance(reason, str), f"not (bool, str): {result!r}"


def _check_response(result: Any) -> None:
    assert isinstance(result, MemoryResponse), f"not MemoryResponse: {type(result).__name__}"


def _check_dict(result: Any) -> None:
    assert isinstance(result, dict), f"not dict: {type(result).__name__}"


def _check_pipeline(result: Any) -> None:
    assert result.__class__.__name__ == "PipelineResult", f"got {type(result).__name__}"
    assert isinstance(result.success, bool)
    result.to_dict()


# ---------------------------------------------------------------------------
# 1-2. school_remember: content / outcome-type / tags+scope
# ---------------------------------------------------------------------------


def test_fuzz_remember_content() -> None:
    report = fuzz_fail_open(
        REMEMBER.execute,
        n=N,
        make_args=lambda i: ((), {"content": _v(_TEXT_POOL, i, 1)}),
        label="school_remember.content",
        check=_check_tool_result,
    )
    assert report.ok, report.summary()


def test_fuzz_remember_outcome_type() -> None:
    def args(i: int):
        return ((), {
            "content": f"remember outcome probe {i}",
            "outcome": _v(_OUTCOME_POOL, i, 2),
        })

    report = fuzz_fail_open(
        REMEMBER.execute,
        n=N,
        make_args=args,
        label="school_remember.outcome_type",
        check=_check_tool_result,
    )
    assert report.ok, report.summary()


def test_fuzz_remember_tags_scope() -> None:
    def args(i: int):
        return ((), {
            "content": f"remember scope probe {i}",
            "observation": _v(_TEXT_POOL, i, 3),
            "action": _v(_TEXT_POOL, i, 4),
            "agent_id": _v(_ID_POOL, i, 5),
            "project": _v(_ID_POOL, i, 6),
            "session": _v(_ID_POOL, i, 7),
            "source": _v(_TEXT_POOL, i, 8),
            "tags": _v(_TAGS_POOL, i, 9),
            "confidence": _v(_NUM_POOL, i, 10),
        })

    report = fuzz_fail_open(
        REMEMBER.execute,
        n=N,
        make_args=args,
        label="school_remember.tags_scope",
        check=_check_tool_result,
    )
    assert report.ok, report.summary()


# ---------------------------------------------------------------------------
# 2. school_recall: query / scope+session params
# ---------------------------------------------------------------------------


def test_fuzz_recall_query() -> None:
    report = fuzz_fail_open(
        RECALL.execute,
        n=N,
        make_args=lambda i: ((), {"query": _v(_TEXT_POOL, i, 11)}),
        label="school_recall.query",
        check=_check_tool_result,
    )
    assert report.ok, report.summary()


def test_fuzz_recall_scope_session() -> None:
    def args(i: int):
        return ((), {
            "query": "python",
            "agent_id": _v(_ID_POOL, i, 12),
            "limit": _v(_NUM_POOL, i, 13),
            "minimum_confidence": _v(_NUM_POOL, i, 14),
            "context_budget": _v(_NUM_POOL, i, 15),
            "tags": _v(_TAGS_POOL, i, 16),
        })

    report = fuzz_fail_open(
        RECALL.execute,
        n=N,
        make_args=args,
        label="school_recall.scope_session",
        check=_check_tool_result,
    )
    assert report.ok, report.summary()


# ---------------------------------------------------------------------------
# 3. school_learn / school_search: semantic query + TF-IDF + rank params
# ---------------------------------------------------------------------------


def test_fuzz_learn_semantic_query() -> None:
    """End-to-end learn path: remember hostile content, then rank with TF-IDF."""
    def call(content: Any, query: Any, limit: Any) -> dict:
        REMEMBER.execute(content=content)
        entries = STORE.query(
            scope=MemoryScope(agent=AgentIdentity.create(agent_id="agent1")), limit=200
        )
        ranked = scored_query(entries, query, EXTRACTOR, limit=limit)
        return {"ranked": len(ranked)}

    report = fuzz_fail_open(
        call,
        n=N,
        make_args=lambda i: (
            (_v(_TEXT_POOL, i, 17), _v(_TEXT_POOL, i, 18), _v(_NUM_POOL, i, 19)), {}
        ),
        label="school_learn.semantic_query",
        check=_check_dict,
    )
    assert report.ok, report.summary()


def test_fuzz_search_rank_params() -> None:
    def args(i: int):
        return ((), {
            "query": _v(_TEXT_POOL, i, 20),
            "limit": _v(_NUM_POOL, i, 21),
            "agent_id": _v(_ID_POOL, i, 22),
        })

    report = fuzz_fail_open(
        SEARCH.execute,
        n=N,
        make_args=args,
        label="school_search.rank_params",
        check=_check_tool_result,
    )
    assert report.ok, report.summary()


# ---------------------------------------------------------------------------
# 4. school_conflict: incoming vs stored, similarity edge cases
# ---------------------------------------------------------------------------


def test_fuzz_conflict_similarity_edges() -> None:
    def args(i: int):
        return ((), {
            "content": "python is statically typed and the sky is green today",
            "similarity_threshold": _v(_NUM_POOL, i, 23),
            "limit": _v(_NUM_POOL, i, 24),
            "agent_id": _v(_ID_POOL, i, 25),
        })

    report = fuzz_fail_open(
        CONFLICT.execute,
        n=N,
        make_args=args,
        label="school_conflict.similarity_edges",
        check=_check_tool_result,
    )
    assert report.ok, report.summary()


# ---------------------------------------------------------------------------
# 5. school_confidence: claim scoring + band thresholds
# ---------------------------------------------------------------------------


def test_fuzz_confidence_claim_scoring() -> None:
    def args(i: int):
        return ((), {
            "similarity": _v(_NUM_POOL, i, 26),
            "success_count": _v(_NUM_POOL, i, 27),
            "failure_count": _v(_NUM_POOL, i, 28),
            "supporting_weight": _v(_NUM_POOL, i, 29),
            "total_weight": _v(_NUM_POOL, i, 30),
            "supporting_count": _v(_NUM_POOL, i, 31),
            "total_count": _v(_NUM_POOL, i, 32),
            "outputs": _v(_TAGS_POOL, i, 33),
        })

    report = fuzz_fail_open(
        CONFIDENCE.execute,
        n=N,
        make_args=args,
        label="school_confidence.claim_scoring",
        check=_check_conf_result,
    )
    assert report.ok, report.summary()


def test_fuzz_confidence_band_thresholds() -> None:
    bands = [0.0, 0.5, 1.0, -1.0, 0.4999, 0.8001, 0.2, 0.6, float("nan"), float("inf")]

    def args(i: int):
        return ((), {
            "similarity": bands[i % len(bands)],
            "success_count": i % 5,
            "failure_count": i % 3,
            "supporting_weight": 0.5,
            "total_weight": 1.0,
            "supporting_count": 2,
            "total_count": 4,
            "outputs": ["out-a", "out-b", "out-c"],
        })

    report = fuzz_fail_open(
        CONFIDENCE.execute,
        n=N,
        make_args=args,
        label="school_confidence.band_thresholds",
        check=_check_conf_result,
    )
    assert report.ok, report.summary()


# ---------------------------------------------------------------------------
# 6. school_deduplicate: merge flag + limit extremes
# ---------------------------------------------------------------------------


def test_fuzz_deduplicate_merge_limit() -> None:
    def args(i: int):
        return ((), {
            "content": "memory 0 about python and testing",
            "merge": _v([True, False, "yes", 0, None, {"a": 1}], i, 34),
            "limit": _v([0, -1, 99999, 20, 10**50, float("nan"), "x", None], i, 35),
            "similarity_threshold": _v(_NUM_POOL, i, 36),
            "agent_id": _v(_ID_POOL, i, 37),
        })

    report = fuzz_fail_open(
        DEDUP.execute,
        n=N,
        make_args=args,
        label="school_deduplicate.merge_limit",
        check=_check_tool_result,
    )
    assert report.ok, report.summary()


# ---------------------------------------------------------------------------
# 7. school_knowledge: pattern extraction over hostile memory sets
# ---------------------------------------------------------------------------


def test_fuzz_knowledge_pattern_extraction() -> None:
    def call(agent_id: Any, seed: Any) -> dict:
        # Keep the store populated with hostile-shaped experiences/entries.
        STORE.store(
            MemoryEntry(
                memory_id=f"hostile-{coerce_text(seed, '?'):.20}",
                content=seed,
                kind=MemoryKind.EPISODIC,
                scope=MemoryScope(agent=AgentIdentity.create(agent_id="agent1")),
                timestamp=1.0,
                tags=coerce_tag_set(seed),
                confidence=0.5,
            )
        )
        result = KNOWLEDGE.execute(agent_id=agent_id)
        assert isinstance(result, ToolResult)
        return {"promoted": result.data.get("promoted_count", -1)}

    report = fuzz_fail_open(
        call,
        n=N,
        make_args=lambda i: ((_v(_ID_POOL, i, 38), _v(_TEXT_POOL, i, 39)), {}),
        label="school_knowledge.pattern_extraction",
        check=_check_dict,
    )
    assert report.ok, report.summary()


# ---------------------------------------------------------------------------
# 8. school_lifecycle: score/decay/promote/archive + hostile ids/amounts
# ---------------------------------------------------------------------------


def test_fuzz_lifecycle_actions() -> None:
    def args(i: int):
        return ((), {
            "action": _v(_ACTION_POOL, i, 40),
            "memory_id": _v(_ID_POOL, i, 41),
            "amount": _v(_NUM_POOL, i, 42),
        })

    report = fuzz_fail_open(
        LIFECYCLE.execute,
        n=N,
        make_args=args,
        label="school_lifecycle.actions",
        check=_check_tool_result,
    )
    assert report.ok, report.summary()


# ---------------------------------------------------------------------------
# 9. school_status / school_dashboard / school_diagnose: read-only status
# ---------------------------------------------------------------------------


def test_fuzz_status_readonly() -> None:
    report = fuzz_fail_open(
        STATUS.execute,
        n=N,
        make_args=lambda i: ((), {"probe": gen_value(depth=3)}),
        label="school_status.readonly",
        check=_check_tool_result,
    )
    assert report.ok, report.summary()


def test_fuzz_diagnose_readonly() -> None:
    report = fuzz_fail_open(
        DIAGNOSE.execute,
        n=N,
        make_args=lambda i: ((), {"probe": gen_value(depth=3)}),
        label="school_diagnose.readonly",
        check=_check_tool_result,
    )
    assert report.ok, report.summary()


# ---------------------------------------------------------------------------
# 10-11. Orchestrator dispatch + ToolRegistry (hostile tool names/args)
# ---------------------------------------------------------------------------


def test_fuzz_orchestrator_dispatch() -> None:
    def args(i: int):
        names = ["school_remember", "school_recall", "nope", "", None, 123, ["x"], {"a": 1}]
        return (
            (_v(names, i, 43),),
            {"content": _v(_TEXT_POOL, i, 44), "query": _v(_TEXT_POOL, i, 45),
             "action": _v(_ACTION_POOL, i, 46)},
        )

    report = fuzz_fail_open(
        ORCH.dispatch,
        n=N,
        make_args=args,
        label="orchestrator.dispatch",
        check=_check_tool_result,
    )
    assert report.ok, report.summary()


def test_fuzz_orchestrator_pipeline() -> None:
    def steps_for(i: int) -> Any:
        kind = i % 5
        if kind == 0:
            return [("school_remember", {"content": f"pipe {i}"}),
                    ("school_conflict", {"content": f"pipe {i}"})]
        if kind == 1:
            return [("school_remember", "not-a-dict")]
        if kind == 2:
            return [("unknown-tool", {"content": "x"}), ("school_status", {})]
        if kind == 3:
            return gen_value(depth=3)
        return "not-steps"

    report = fuzz_fail_open(
        ORCH.pipeline,
        n=N,
        make_args=lambda i: ((steps_for(i),), {}),
        label="orchestrator.pipeline",
        check=_check_pipeline,
    )
    assert report.ok, report.summary()


def test_fuzz_orchestrator_parallel() -> None:
    def calls_for(i: int) -> Any:
        kind = i % 4
        if kind == 0:
            return [("school_status", {}), ("school_diagnose", {})]
        if kind == 1:
            return [("unknown", {"probe": gen_value(depth=2)})]
        if kind == 2:
            return [(gen_value(depth=2), {"a": 1})]
        return "not-calls"

    report = fuzz_fail_open(
        ORCH.parallel,
        n=N,
        make_args=lambda i: ((calls_for(i),), {}),
        label="orchestrator.parallel",
        check=_check_pipeline,
    )
    assert report.ok, report.summary()


def test_fuzz_registry_dispatch() -> None:
    def str_keys(params: Any) -> bool:
        try:
            return bool(params) and all(isinstance(k, str) for k in params)
        except Exception:  # noqa: BLE001 - hostile mapping
            return False

    def call(name: Any, params: Any) -> Any:
        probe = params if isinstance(params, dict) and str_keys(params) else {"probe": params}
        return REGISTRY.execute(name, **probe)

    def args(i: int):
        return (
            (_v(["school_remember", "school_status", "zzz", "", None, 123, [1], {"a": 1}], i, 47),
             _v([None, {"query": "python"}, {"content": "c"}, gen_value(depth=2)], i, 48)),
            {},
        )

    report = fuzz_fail_open(
        call,
        n=N,
        make_args=args,
        label="tool_registry.dispatch",
        check=_check_tool_result,
    )
    assert report.ok, report.summary()


# ---------------------------------------------------------------------------
# 12. memory_manager: store / request / lifecycle / corrupt load
# ---------------------------------------------------------------------------


def _hostile_entry(i: int) -> Any:
    kind = i % 6
    if kind == 0:
        return VALID_ENTRY
    if kind == 1:
        return MemoryEntry(
            memory_id=f"h-{i}",
            content=_v(_TEXT_POOL, i, 49),
            kind=MemoryKind.EPISODIC,
            scope=MemoryScope(agent=AgentIdentity.create(agent_id="agent1")),
            timestamp=_v(_NUM_POOL, i, 50),
            tags=coerce_tag_set(_v(_TAGS_POOL, i, 51)),
            confidence=_v(_NUM_POOL, i, 52),
        )
    return _v(HOSTILE, i, 53)


def test_fuzz_manager_store_memory() -> None:
    def args(i: int):
        agent_id = _v(_ID_POOL, i, 54)
        try:
            agent = AgentIdentity.create(agent_id=coerce_text(agent_id, "a") or "a")
        except Exception:  # noqa: BLE001
            agent = None
        return ((_hostile_entry(i),), {"agent": _v([None, agent], i, 55)})

    report = fuzz_fail_open(
        MANAGER.store_memory,
        n=N,
        make_args=args,
        label="memory_manager.store_memory",
        check=_check_bool_str,
    )
    assert report.ok, report.summary()


def test_fuzz_manager_store_experience() -> None:
    hostile_exp = Experience.create(
        agent=AgentIdentity.create(agent_id="agent1"),
        observation="obs",
        action="act",
        outcome=ExperienceOutcome.SUCCESS,
    )

    def experience_for(i: int) -> Any:
        kind = i % 5
        if kind == 0:
            return VALID_EXPERIENCE
        if kind == 1:
            return hostile_exp
        return _v(HOSTILE, i, 56)

    report = fuzz_fail_open(
        MANAGER.store_experience,
        n=N,
        make_args=lambda i: ((experience_for(i),), {}),
        label="memory_manager.store_experience",
        check=_check_bool_str,
    )
    assert report.ok, report.summary()


def test_fuzz_manager_request_memory() -> None:
    def request_for(i: int) -> Any:
        kind = i % 6
        if kind == 0:
            return MemoryRequest(
                agent=AgentIdentity.create(agent_id="agent1"), query="python"
            )
        if kind == 1:
            return MemoryRequest(
                agent=AgentIdentity.create(agent_id="agent1"),
                query=_v(_TEXT_POOL, i, 57),
                limit=_v(_NUM_POOL, i, 58),
                minimum_confidence=_v(_NUM_POOL, i, 59),
                context_budget=_v(_NUM_POOL, i, 60),
                tags=coerce_tag_set(_v(_TAGS_POOL, i, 61)),
            )
        return _v(HOSTILE, i, 62)

    def call(request: Any) -> dict:
        response = MANAGER.request_memory(request)
        # to_dict on responses/entries with adversarial stored state is a
        # NON-OWNED (memory_types) surface: record known crashes only.
        try:
            response.to_dict()
        except Exception as exc:  # noqa: BLE001
            _record_finding(exc)
        for entry in (WEIRD_TAGS_ENTRY, WEIRD_CONTENT_ENTRY):
            try:
                entry.to_dict()
            except Exception as exc:  # noqa: BLE001
                _record_finding(exc)
        return {"count": response.count}

    report = fuzz_fail_open(
        call,
        n=N,
        make_args=lambda i: ((request_for(i),), {}),
        label="memory_manager.request_memory",
        check=_check_dict,
    )
    assert report.ok, report.summary()


def test_fuzz_manager_lifecycle_ops() -> None:
    def call(op: str, arg: Any) -> Any:
        if op == "get":
            return MANAGER.get_memory(arg) is not None
        if op == "remove":
            return MANAGER.remove_memory(arg)
        if op == "clear":
            return MANAGER.clear(scope=arg)
        if op == "list":
            return len(MANAGER.list_memories(scope=arg, limit=arg))
        if op == "count":
            return MANAGER.count_memories(scope=arg)
        if op == "promote":
            ok, _reason, _entry = MANAGER.promote_experience(arg)
            return ok
        if op == "check":
            ok, _reason = MANAGER.check_promotion(arg)
            return ok
        if op == "consolidate":
            return MANAGER.consolidate(arg, scope=None).promoted_count
        return MANAGER.stats()["store_size"]

    def args(i: int):
        return ((_v(["get", "remove", "clear", "list", "count", "promote",
                     "check", "consolidate", "stats"], i, 63),
                 _v([VALID_EXPERIENCE, "mem-1", "", None, [1], {"a": 1}, 123,
                     gen_value(depth=3), VALID_ENTRY], i, 64)), {})

    report = fuzz_fail_open(
        call,
        n=N,
        make_args=args,
        label="memory_manager.lifecycle_ops",
        check=lambda r: None,
    )
    assert report.ok, report.summary()


def test_fuzz_manager_load_corrupt() -> None:
    store_dir = pathlib.Path(WT_B) / ".school" / "memory"
    store_dir.mkdir(parents=True, exist_ok=True)
    store_file = store_dir / "v26_memory.json"

    nan_entry = '{"memory_id": "n1", "content": "nan conf", "kind": "EPISODIC", ' \
                '"scope": {"agent": {"agent_id": "a1"}}, "timestamp": 1.0, ' \
                '"confidence": NaN, "tags": []}'
    null_project = '{"memory_id": "n2", "content": "null project", "kind": "EPISODIC", ' \
                   '"scope": {"agent": {"agent_id": "a1"}, "project": null}, ' \
                   '"timestamp": 1.0, "confidence": 0.5, "tags": []}'
    hostile_raw = '{"memory_id": 3, "content": [1], "kind": [], ' \
                  '"scope": {"agent": {"agent_id": ""}}, "timestamp": "x", ' \
                  '"tags": {"a": 1}, "confidence": [], "metadata": 5}'

    def set_state(i: int) -> None:
        state = i % 9
        if state == 0:
            if store_file.exists():
                store_file.unlink()
            return
        if state == 1:
            payload = ""
        elif state == 2:
            payload = '{"version": "2.6.0", "entr'
        elif state == 3:
            payload = "[1, 2, 3]"
        elif state == 4:
            payload = '{"version": "2.6.0", "entries": "not-a-list"}'
        elif state == 5:
            payload = f'{{"version": "2.6.0", "entries": [{nan_entry}]}}'
        elif state == 6:
            payload = f'{{"version": "2.6.0", "entries": [{null_project}]}}'
        elif state == 7:
            payload = (
                '{"version": "2.6.0", "entries": ['
                + ",".join([hostile_raw] * 5)
                + "]}"
            )
        else:
            payload = json.dumps({
                "version": "2.6.0",
                "entries": [
                    {
                        "memory_id": f"m{j}",
                        "content": f"bulk memory {j}",
                        "kind": "EPISODIC",
                        "scope": {"agent": {"agent_id": "a1"}},
                        "timestamp": float(j),
                        "confidence": 0.5,
                    }
                    for j in range(50)
                ],
            })
        store_file.write_text(payload, encoding="utf-8")

    def call(i: int) -> dict:
        set_state(i)
        storage = ScopeIsolatedStorage(base_path=store_dir)
        manager = MemoryManager(storage=storage)
        try:
            count = manager.reload()
        except PersistenceError as exc:
            return {"corrupt": coerce_text(exc, "?")[:60]}
        memories = manager.list_memories()
        for entry in memories[:3]:
            manager.get_memory(entry.memory_id)
        stats = manager.stats()
        assert isinstance(stats, dict)
        return {"loaded": count}

    report = fuzz_fail_open(
        call,
        n=N,
        make_args=lambda i: ((i,), {}),
        label="memory_manager.load_corrupt",
        check=_check_dict,
    )
    assert report.ok, report.summary()


# ---------------------------------------------------------------------------
# 13. semantic_retrieval.scored_query (hostile entries/query/weights/encoder)
# ---------------------------------------------------------------------------


class _HostileEncoder:
    def encode_single(self, text: Any) -> Any:
        raise RuntimeError("hostile encoder")


def test_fuzz_scored_query() -> None:
    valid_entries = STORE.query(limit=50)

    def entries_for(i: int) -> Any:
        kind = i % 5
        if kind == 0:
            return valid_entries
        if kind == 1:
            return [_hostile_entry(i), VALID_ENTRY]
        if kind == 2:
            return []
        return _v(HOSTILE, i, 65)

    def args(i: int):
        return (
            (entries_for(i), _v(_TEXT_POOL, i, 66), EXTRACTOR),
            {
                "encoder": _v([None, _HostileEncoder()], i, 67),
                "limit": _v(_NUM_POOL, i, 68),
                "lexical_weight": _v(_NUM_POOL, i, 69),
                "semantic_weight": _v(_NUM_POOL, i, 70),
            },
        )

    def check_list(result: Any) -> None:
        assert isinstance(result, list), f"not list: {type(result).__name__}"

    report = fuzz_fail_open(
        scored_query,
        n=N,
        make_args=args,
        label="semantic_retrieval.scored_query",
        check=check_list,
    )
    assert report.ok, report.summary()


# ---------------------------------------------------------------------------
# 14. identity: constructors / from_dict / to_dict / includes / coerce helpers
# ---------------------------------------------------------------------------


def test_fuzz_identity_construct_roundtrip() -> None:
    def call(raw_id: Any, raw_data: Any, raw_other: Any) -> dict:
        out: dict[str, Any] = {}

        def construct(factory, value, key):
            try:
                obj = factory(value)
            except ValueError as exc:
                out[key] = f"invalid: {coerce_text(exc, '?')[:40]}"
                return None
            obj.to_dict()
            obj.scope_key()
            return obj

        agent = construct(AgentIdentity, raw_id, "agent")
        project = construct(ProjectIdentity, raw_id, "project")
        session = construct(SessionIdentity, raw_id, "session")

        # AgentIdentity.from_dict is documented lenient: must never raise.
        out["agent_from_dict"] = AgentIdentity.from_dict(raw_data).agent_id
        # Project/Session/MemoryScope.from_dict raise ValueError only.
        try:
            out["project_from_dict"] = ProjectIdentity.from_dict(raw_data).project_id
        except ValueError:
            out["project_from_dict"] = "invalid"
        try:
            out["session_from_dict"] = SessionIdentity.from_dict(raw_data).session_id
        except ValueError:
            out["session_from_dict"] = "invalid"
        try:
            out["scope_from_dict"] = MemoryScope.from_dict(raw_data).scope_key()
        except ValueError:
            out["scope_from_dict"] = "invalid"

        # includes must always return bool (hostile others degrade to False).
        probe = MemoryScope(agent=AgentIdentity.create(agent_id="probe"))
        for other in (raw_other, probe, agent, project, session):
            result = probe.includes(other) if other is not None else False
            assert isinstance(result, bool), f"includes -> {type(result).__name__}"

        # Coercion helpers are strict fail-open: never raise.
        coerce_text(raw_id)
        coerce_float(raw_id)
        coerce_int(raw_id)
        coerce_tag_set(raw_data)
        coerce_mapping(raw_data)
        return out

    def args(i: int):
        return (
            (_v(_ID_POOL, i, 71), _v([{}, {"agent_id": "a"}, {"agent": {"agent_id": "x"}},
                                     gen_value(depth=3), None, "str", 123], i, 72),
             _v(HOSTILE, i, 73)),
            {},
        )

    report = fuzz_fail_open(
        call,
        n=N,
        make_args=args,
        label="identity.construct_roundtrip",
        check=_check_dict,
    )
    assert report.ok, report.summary()


# ---------------------------------------------------------------------------
# 15. security: request/content/scope validation + injection detection
# ---------------------------------------------------------------------------


def test_fuzz_security_validate_detect() -> None:
    valid_request = MemoryRequest(
        agent=AgentIdentity.create(agent_id="agent1"), query="hello"
    )
    valid_scope = MemoryScope(agent=AgentIdentity.create(agent_id="agent1"))

    def call(payload: Any, request: Any, entry: Any) -> dict:
        is_inj, pattern = detect_injection(payload)
        assert isinstance(is_inj, bool), f"detect_injection -> {type(is_inj).__name__}"
        assert isinstance(pattern, str), f"detect_injection -> {type(pattern).__name__}"

        for result in (
            validate_memory_request(request),
            validate_memory_content(entry),
            validate_scope_access(valid_scope, entry),
            enforce_instruction_boundary(entry),
        ):
            assert isinstance(result, tuple) and len(result) == 2, f"bad tuple: {result!r}"
            ok, reason = result
            assert isinstance(ok, bool), f"not bool: {ok!r}"
            assert isinstance(reason, str), f"not str: {reason!r}"
        return {"injection": is_inj}

    def args(i: int):
        return (
            (_v(_TEXT_POOL, i, 74),
             _v([valid_request, MemoryRequest(
                 agent=AgentIdentity.create(agent_id="agent1"),
                 query=_v(_TEXT_POOL, i, 75),
                 limit=_v(_NUM_POOL, i, 76),
                 minimum_confidence=_v(_NUM_POOL, i, 77),
                 context_budget=_v(_NUM_POOL, i, 78),
                 tags=coerce_tag_set(_v(_TAGS_POOL, i, 79)),
             ), HOSTILE[i % len(HOSTILE)]], i, 80),
             _v([VALID_ENTRY, _hostile_entry(i), HOSTILE[i % len(HOSTILE)]], i, 81)),
            {},
        )

    report = fuzz_fail_open(
        call,
        n=N,
        make_args=args,
        label="security.validate_detect",
        check=_check_dict,
    )
    assert report.ok, report.summary()


# ---------------------------------------------------------------------------
# 16-18. school_route (MCP, NON-OWNED): assess / report / knobs
#
# The MCP route tools document a ValueError contract for missing
# situation/severity/lesson (tests/unit/test_mcp_server.py). Anything else
# that escapes is a non-owned bug -> recorded via NON_OWNED_FINDINGS.
# ---------------------------------------------------------------------------


def _mcp_server():
    from school.mcp import server as mcp_server  # noqa: PLC0415

    return mcp_server


_JSON_TEXTS = [
    "hello situation", "light task", "x" * 5000, "unicode ünïcödé \U0001f4a9",
    "nul\x00byte", "", "   ", "a" * 501,
]
_JSON_VALUES = [
    None, 0, -1, 1, 2, 3.14, True, False, "", "text", "light", "medium", "high",
    [], ["a"], [1, 2], {"a": 1}, {"nested": {"deep": 1}},
]


def test_fuzz_school_route_assess() -> None:
    mcp = _mcp_server()

    def args(i: int):
        arguments = dict(gen_json_safe())
        arguments["mode"] = "assess"
        arguments["situation"] = _v(_JSON_TEXTS, i, 82)
        arguments["severity"] = _v(_JSON_VALUES + _JSON_TEXTS, i, 83)
        return ((WT_POOL[i % len(WT_POOL)], arguments), {})

    report = fuzz_fail_open(
        lambda worktree, arguments: _mcp_call(mcp._call_route, worktree, arguments),
        n=N,
        make_args=args,
        label="school_route.assess",
        check=_check_dict,
    )
    assert report.ok, report.summary()


def test_fuzz_school_route_report() -> None:
    mcp = _mcp_server()

    def args(i: int):
        arguments = dict(gen_json_safe())
        arguments["mode"] = "report"
        arguments["situation"] = _v(_JSON_TEXTS, i, 84)
        arguments["lesson"] = _v(_JSON_TEXTS, i, 85)
        arguments["outcome"] = _v(_JSON_VALUES + _JSON_TEXTS, i, 86)
        return ((WT_POOL[i % len(WT_POOL)], arguments), {})

    report = fuzz_fail_open(
        lambda worktree, arguments: _mcp_call(mcp._call_route, worktree, arguments),
        n=N,
        make_args=args,
        label="school_route.report",
        check=_check_dict,
    )
    assert report.ok, report.summary()


def test_fuzz_school_route_knobs() -> None:
    mcp = _mcp_server()
    knobs_dir = pathlib.Path(WT_A) / ".school" / "memory"
    knobs_dir.mkdir(parents=True, exist_ok=True)
    knobs_file = knobs_dir / "routing.json"

    def set_state(i: int) -> None:
        state = i % 7
        if state == 0:
            if knobs_file.exists():
                knobs_file.unlink()
            return
        payloads = {
            1: "{}",
            2: '{"recall_threshold": 0.5, "hook_limit": 3}',
            3: '{"recall_threshold": "x", "skip_tools": "not-a-list", '
               '"force_tools": {"a": 1}, "hook_limit": [1]}',
            4: '{"recall_threshold": NaN, "hook_budget": Infinity}',
            5: "{" + '"a": 1, ' * 200 + '"b": 2}',
            6: "not json at all {{{",
        }
        knobs_file.write_text(payloads[state], encoding="utf-8")

    def call(i: int) -> dict:
        set_state(i)
        worktree = _v([WT_A, WT_B, "..\\..\\nonexistent-fuzz", "\x00nul", "Z" * 4000], i, 87)
        knobs = mcp._read_knobs(worktree)
        assert isinstance(knobs, dict), f"knobs -> {type(knobs).__name__}"
        stats = _mcp_call_strict(mcp._read_stats, worktree, i % 30)
        return {"knobs": sorted(knobs)[:3], "stats": stats}

    report = fuzz_fail_open(
        call,
        n=N,
        make_args=lambda i: ((i,), {}),
        label="school_route.knobs",
        check=_check_dict,
    )
    assert report.ok, report.summary()


# ---------------------------------------------------------------------------
# 19. school_route_stats (MCP, NON-OWNED): aggregation over hostile histories
# ---------------------------------------------------------------------------


def _write_stats_state(wt: str, i: int) -> None:
    root = pathlib.Path(wt) / ".school" / "memory"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "routing-stats.jsonl"
    state = i % 6
    if state == 0:
        if path.exists():
            path.unlink()
    elif state == 1:
        path.write_text('{"ts": "t", "kind": "exec", "tool": "t", "ms": 5}\n', encoding="utf-8")
    elif state == 2:
        path.write_text(
            '{"kind": "exec", "tool": "t", "ms": "oops"}\n123\n"str"\n[1, 2]\n{"bad\n',
            encoding="utf-8",
        )
    elif state == 3:
        path.write_text('{"kind": "assess", "severity": "light"}\nnot json\n', encoding="utf-8")
    elif state == 4:
        lines = [
            json.dumps({"ts": f"t{j}", "kind": "exec", "tool": f"tool{j % 3}", "ms": j})
            for j in range(1500)
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        path.write_text(
            '{"kind": "exec", "tool": "\u0000x", "ms": null, "hits": 3}\n', encoding="utf-8"
        )


def test_fuzz_school_route_stats_aggregation() -> None:
    mcp = _mcp_server()

    def call(i: int) -> dict:
        wt = WT_POOL[i % len(WT_POOL)]
        _write_stats_state(wt, i)
        arguments = {"limit": _v([0, -1, 99999, 20, "x", None, [1], {"a": 1}], i, 88)}
        result = _mcp_call_strict(mcp._call_route_stats, wt, arguments)
        return result

    report = fuzz_fail_open(
        call,
        n=N,
        make_args=lambda i: ((i,), {}),
        label="school_route_stats.aggregation",
        check=_check_dict,
    )
    assert report.ok, report.summary()


# ---------------------------------------------------------------------------
# 20. school_dashboard (MCP, NON-OWNED): read-only status object
# ---------------------------------------------------------------------------


def test_fuzz_school_dashboard_readonly() -> None:
    mcp = _mcp_server()

    def call(i: int) -> dict:
        wt = WT_POOL[i % len(WT_POOL)]
        _write_stats_state(wt, i)
        arguments = dict(gen_json_safe())
        return _mcp_call_strict(mcp._call_dashboard, wt, arguments)

    report = fuzz_fail_open(
        call,
        n=N,
        make_args=lambda i: ((i,), {}),
        label="school_dashboard.readonly",
        check=_check_dict,
    )
    assert report.ok, report.summary()


# ---------------------------------------------------------------------------
# Ledger: proof that every tool.feature ran exactly 2000 iterations
# ---------------------------------------------------------------------------

EXPECTED_LABELS = {
    "school_remember.content": N,
    "school_remember.outcome_type": N,
    "school_remember.tags_scope": N,
    "school_recall.query": N,
    "school_recall.scope_session": N,
    "school_learn.semantic_query": N,
    "school_search.rank_params": N,
    "school_conflict.similarity_edges": N,
    "school_confidence.claim_scoring": N,
    "school_confidence.band_thresholds": N,
    "school_deduplicate.merge_limit": N,
    "school_knowledge.pattern_extraction": N,
    "school_lifecycle.actions": N,
    "school_status.readonly": N,
    "school_diagnose.readonly": N,
    "orchestrator.dispatch": N,
    "orchestrator.pipeline": N,
    "orchestrator.parallel": N,
    "tool_registry.dispatch": N,
    "memory_manager.store_memory": N,
    "memory_manager.store_experience": N,
    "memory_manager.request_memory": N,
    "memory_manager.lifecycle_ops": N,
    "memory_manager.load_corrupt": N,
    "semantic_retrieval.scored_query": N,
    "identity.construct_roundtrip": N,
    "security.validate_detect": N,
    "school_route.assess": N,
    "school_route.report": N,
    "school_route.knobs": N,
    "school_route_stats.aggregation": N,
    "school_dashboard.readonly": N,
}


def test_zz_ledger_summary() -> None:
    from fuzz_harness import FUZZ_FAILURES, FUZZ_LEDGER

    for label, expected in EXPECTED_LABELS.items():
        actual = FUZZ_LEDGER.get(label)
        assert actual == expected, f"{label}: {actual} iterations != {expected}"
        failures = FUZZ_FAILURES.get(label) or []
        assert not failures, f"{label}: {len(failures)} failures: {failures[0]}"
    unexpected = set(FUZZ_LEDGER) - set(EXPECTED_LABELS)
    assert not unexpected, f"unexpected labels: {unexpected}"

    text = ledger_summary()
    text += "\n\n[non-owned findings] " + json.dumps(NON_OWNED_FINDINGS, indent=2)
    print(text)
    _LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    _LEDGER_PATH.write_text(text, encoding="utf-8")
