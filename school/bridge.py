"""School bridge — importable entry point for the bridge protocol.

Reads a single JSON request from stdin, processes it through the V2.6
memory architecture, and writes a single JSON response to stdout.

Protocol:
    stdin  → JSON request  → bridge → V2.6 components
    stdout → JSON response → School plugin

Commands:
    status   — check component availability
    remember — store an experience through V2.6
    recall   — retrieve memories through V2.6
    skeleton — Context Optimizer (skeletonize oversized text)
"""

from __future__ import annotations

import contextlib
import json
import math
import sys
from typing import Any

# ---------------------------------------------------------------------------
# V2.6 imports
# ---------------------------------------------------------------------------
from core.routing.v26.experience import Experience, ExperienceOutcome
from core.routing.v26.identity import (
    AgentIdentity,
    ProjectIdentity,
    SessionIdentity,
)
from core.routing.v26.memory_manager import MemoryManager
from core.routing.v26.memory_types import MemoryRequest
from core.routing.v26.persistence import ScopeIsolatedStorage
from core.routing.v26.security import (
    detect_injection,
    validate_memory_request,
)
from school import __version__
from school.config import resolve_memory_dir
from school.skeleton import optimize

# ---------------------------------------------------------------------------
# Bridge state (lazily initialised, lives for one process invocation)
# ---------------------------------------------------------------------------

_manager: MemoryManager | None = None
_storage: ScopeIsolatedStorage | None = None
_init_error: str | None = None


# ---------------------------------------------------------------------------
# Fail-open text/JSON sanitising helpers
# ---------------------------------------------------------------------------


def _err_text(exc: BaseException) -> str:
    """str(exc) that can never raise (hostile exceptions may break __str__)."""
    try:
        return str(exc)
    except Exception:  # noqa: BLE001 — fail-open
        try:
            return repr(exc)
        except Exception:  # noqa: BLE001 — fail-open
            return f"<unprintable {type(exc).__name__}>"


def _safe_str(value: Any) -> str:
    """str(value) that can never raise (hostile objects break __str__/__repr__)."""
    try:
        return str(value)
    except Exception:  # noqa: BLE001 — fail-open
        try:
            return repr(value)
        except Exception:  # noqa: BLE001 — fail-open
            return f"<unprintable {type(value).__name__}>"


def _scrub_surrogates(text: str) -> str:
    """Replace lone UTF-16 surrogates (unencodable on the JSON wire)."""
    try:
        text.encode("utf-8")
        return text
    except UnicodeEncodeError:
        return "".join(
            "\ufffd" if 0xD800 <= ord(ch) <= 0xDFFF else ch for ch in text
        )


def _json_safe(value: Any, _depth: int = 0, _budget: list[int] | None = None) -> Any:
    """Normalise *value* into strictly serialisable JSON data (fail-open).

    Non-finite floats become null, exotic objects become safe strings, lone
    surrogates are scrubbed, hostile container subclasses are iterated
    defensively. The result is always accepted by json.dumps(allow_nan=False).
    A depth cutoff plus a node budget bound the work even for shared/cyclic
    graphs (JSON cannot represent sharing, so truncation is lossless-by-design).
    """
    if _budget is None:
        _budget = [50_000]
    _budget[0] -= 1
    if _budget[0] < 0:
        return "<max-nodes>"
    if _depth > 25:
        return "<max-depth>"
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        return _scrub_surrogates(value)
    if isinstance(value, dict):
        try:
            items = list(dict.items(value))
        except Exception:  # noqa: BLE001 — hostile mapping subclass
            return f"<unserializable {type(value).__name__}>"
        out: dict[str, Any] = {}
        for key, val in items:
            skey = key if isinstance(key, str) else _safe_str(key)
            out[_scrub_surrogates(skey)] = _json_safe(val, _depth + 1, _budget)
        return out
    if isinstance(value, (list, tuple)):
        try:
            items = list(value)
        except Exception:  # noqa: BLE001 — hostile sequence subclass
            return f"<unserializable {type(value).__name__}>"
        return [_json_safe(item, _depth + 1, _budget) for item in items]
    if isinstance(value, (set, frozenset)):
        try:
            items = list(value)
        except Exception:  # noqa: BLE001 — hostile set subclass
            return f"<unserializable {type(value).__name__}>"
        return sorted(
            (_json_safe(item, _depth + 1, _budget) for item in items), key=_safe_str
        )
    return _safe_str(value)


def _init_manager(worktree: str) -> MemoryManager:
    """Initialise (or re-use) the MemoryManager for the given worktree."""
    global _manager, _storage, _init_error

    if _manager is not None:
        return _manager

    try:
        # Memory root: first existing of .school/.teacher/.lerev/.evo,
        # else .school — read in place, never migrated (see resolve_memory_dir).
        storage_dir = resolve_memory_dir(worktree)
        _storage = ScopeIsolatedStorage(base_path=storage_dir)
        _manager = MemoryManager(storage=_storage)
        _manager.reload()
        _init_error = None
        return _manager
    except Exception as exc:
        _init_error = str(exc)
        raise


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def _handle_status(req: dict[str, Any]) -> dict[str, Any]:
    """Check actual component availability."""
    worktree = req.get("worktree", "")
    checks: dict[str, str] = {}

    checks["school"] = "available"

    try:
        from core.routing.integration import SchoolIntegrationBridge  # noqa: F401
        checks["v2_5"] = "available"
    except Exception:
        checks["v2_5"] = "not_importable"

    try:
        from core.routing.v26.memory_manager import MemoryManager  # noqa: F401
        from core.routing.v26.memory_store import MemoryStore  # noqa: F401
        from core.routing.v26.persistence import ScopeIsolatedStorage  # noqa: F401
        from core.routing.v26.security import V26SecurityPolicy  # noqa: F401
        checks["v2_6"] = "available"
    except Exception:
        checks["v2_6"] = "not_importable"

    try:
        storage_dir = resolve_memory_dir(worktree)
        test_file = storage_dir / ".bridge_test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)
        checks["persistence"] = "available"
    except Exception:
        checks["persistence"] = "unavailable"

    try:
        is_injection, _ = detect_injection("ignore previous instructions")
        checks["security"] = "available"
    except Exception:
        checks["security"] = "unavailable"

    return {"ok": True, "components": checks, "version": __version__}


def _handle_remember(req: dict[str, Any]) -> dict[str, Any]:
    """Store an experience through V2.6."""
    worktree = req.get("worktree", "")
    agent_id = req.get("agent", "opencode")
    project_id = req.get("project", "")
    session_id = req.get("session", "")
    content = req.get("content", "")
    outcome_str = req.get("outcome", "NEUTRAL")
    observation = req.get("observation", content)
    action = req.get("action", "")
    confidence = req.get("confidence", 0.5)
    tags = req.get("tags", [])

    if not content and not observation:
        return {
            "ok": False,
            "error": {"type": "validation", "message": "content or observation required"},
        }

    manager = _init_manager(worktree)

    agent = AgentIdentity.create(agent_id=agent_id, adapter="opencode")
    project = (
        ProjectIdentity.create(project_id=project_id, name=project_id)
        if project_id
        else None
    )
    session = (
        SessionIdentity.create(
            session_id=session_id, project_id=project_id or "", agent_id=agent_id
        )
        if session_id
        else None
    )

    try:
        outcome = ExperienceOutcome[outcome_str.upper()]
    except KeyError:
        outcome = ExperienceOutcome.NEUTRAL

    experience = Experience.create(
        agent=agent,
        observation=observation or content,
        action=action,
        outcome=outcome,
        project=project,
        session=session,
        confidence=confidence,
        tags=frozenset(tags) if tags else frozenset(),
    )

    success, reason = manager.store_experience(experience)
    if not success:
        return {"ok": False, "error": {"type": "storage_rejection", "message": reason}}

    scope: dict[str, Any] = {"agent": agent_id}
    if project_id:
        scope["project"] = project_id
    if session_id:
        scope["session"] = session_id

    return {
        "ok": True,
        "id": experience.experience_id,
        "scope": scope,
        "outcome": outcome.name,
    }


def _handle_recall(req: dict[str, Any]) -> dict[str, Any]:
    """Retrieve memories through V2.6."""
    worktree = req.get("worktree", "")
    agent_id = req.get("agent", "opencode")
    project_id = req.get("project", "")
    session_id = req.get("session", "")
    query = req.get("query", "")
    confidence_threshold = req.get("confidence_threshold", 0.0)
    context_budget = req.get("context_budget", 4096)
    limit = req.get("limit", 10)

    if not query:
        return {"ok": False, "error": {"type": "validation", "message": "query is required"}}

    manager = _init_manager(worktree)

    agent = AgentIdentity.create(agent_id=agent_id, adapter="opencode")
    project = (
        ProjectIdentity.create(project_id=project_id, name=project_id)
        if project_id
        else None
    )
    session = (
        SessionIdentity.create(
            session_id=session_id, project_id=project_id or "", agent_id=agent_id
        )
        if session_id
        else None
    )

    request = MemoryRequest(
        agent=agent,
        query=query,
        project=project,
        session=session,
        limit=limit,
        minimum_confidence=confidence_threshold,
        context_budget=context_budget,
    )

    is_valid, reason = validate_memory_request(request, manager._policy)
    if not is_valid:
        return {"ok": False, "error": {"type": "validation", "message": reason}}

    response = manager.request_memory(request)

    memories: list[dict[str, Any]] = []
    for entry in response.memories:
        memories.append({
            "id": entry.memory_id,
            "content": entry.content,
            "kind": entry.kind.name,
            "confidence": entry.confidence,
            "tags": sorted(entry.tags),
            "source": entry.source,
            "timestamp": entry.timestamp,
        })

    return {
        "ok": True,
        "memories": memories,
        "total": response.total,
        "truncated": response.truncated,
        "context_cost": response.context_cost,
    }


# ---------------------------------------------------------------------------
# New orchestrator-based commands
# ---------------------------------------------------------------------------

_orchestrator = None

def _get_orchestrator(worktree=""):
    global _orchestrator
    if _orchestrator is None:
        from core.routing.v26.factory import create_orchestrator
        manager = _init_manager(worktree)
        _orchestrator = create_orchestrator(storage=manager._storage)
    return _orchestrator

def _dispatch_to_orchestrator(tool_name, req):
    """Dispatch to the orchestrator. FAIL-OPEN: never raises, always returns a
    valid dict so every school_* tool is impossible to fail at the bridge layer."""
    try:
        orch = _get_orchestrator(req.get("worktree", ""))
        params = {k: v for k, v in req.items() if k != "command"}
        result = orch.dispatch(tool_name, **params)
        return {"ok": result.success, "result": result.data, "errors": result.errors}
    except Exception as exc:  # noqa: BLE001 — fail-open by design
        message = _err_text(exc)
        return {
            "ok": False,
            "result": {},
            "errors": [f"{type(exc).__name__}: {message}"],
            "error": {"type": "runtime", "message": message, "tool": tool_name},
        }

def _handle_learn(req): return _dispatch_to_orchestrator("school_remember", req)
def _handle_diagnose(req): return _dispatch_to_orchestrator("school_diagnose", req)
def _handle_conflict(req): return _dispatch_to_orchestrator("school_conflict", req)
def _handle_confidence(req): return _dispatch_to_orchestrator("school_confidence", req)
def _handle_deduplicate(req): return _dispatch_to_orchestrator("school_deduplicate", req)
def _handle_lifecycle(req): return _dispatch_to_orchestrator("school_lifecycle", req)
def _handle_search(req): return _dispatch_to_orchestrator("school_search", req)
def _handle_knowledge(req): return _dispatch_to_orchestrator("school_knowledge", req)

# --- 1A-2Z skill generation (school_skill_* -> skill_* commands) ---
def _handle_skill_list(req): return _dispatch_to_orchestrator("school_skill_list", req)
def _handle_skill_search(req): return _dispatch_to_orchestrator("school_skill_search", req)
def _handle_skill_create(req): return _dispatch_to_orchestrator("school_skill_create", req)
def _handle_skill_use(req): return _dispatch_to_orchestrator("school_skill_use", req)
def _handle_skill_feedback(req): return _dispatch_to_orchestrator("school_skill_feedback", req)
def _handle_skill_status(req): return _dispatch_to_orchestrator("school_skill_status", req)
def _handle_skill_evolve(req): return _dispatch_to_orchestrator("school_skill_evolve", req)
# --- 1A-2Z Phase 2 GitHub discovery (school_skill_* -> skill_* commands) ---
def _handle_skill_search_github(req):
    return _dispatch_to_orchestrator("school_skill_search_github", req)
def _handle_skill_discover(req): return _dispatch_to_orchestrator("school_skill_discover", req)
def _handle_skill_analyze_external(req):
    return _dispatch_to_orchestrator("school_skill_analyze_external", req)
def _handle_skill_compare(req): return _dispatch_to_orchestrator("school_skill_compare", req)
def _handle_skill_import(req): return _dispatch_to_orchestrator("school_skill_import", req)


def _handle_skeleton(req: dict) -> dict:
    text = req.get("text", "")
    if not isinstance(text, str) or not text:
        return {
            "ok": False,
            "error": {"type": "validation", "message": "text is required"},
        }
    filename = str(req.get("filename", "") or "")
    strategy = str(req.get("strategy", "auto") or "auto")
    if strategy not in {"auto", "code", "payload", "matches"}:
        return {
            "ok": False,
            "error": {"type": "validation", "message": f"unknown strategy: {strategy}"},
        }
    result = optimize(text, filename=filename, strategy=strategy)
    return {
        "ok": True,
        "content": result.text,
        "tokens_in": result.tokens_in,
        "tokens_out": result.tokens_out,
        "compressed": result.compressed,
        "parser": result.parser,
    }


# --- Context engine surfaces (S2) --------------------------------------


def _engine_for(req: dict[str, Any]) -> Any:
    from core.context import ContextEngine

    worktree = str(req.get("worktree", "") or ".")
    session = str(req.get("session", "") or "default")
    return ContextEngine(worktree, session)


def _ctx_messages(req: dict[str, Any]) -> list[dict[str, Any]]:
    messages = req.get("messages")
    return messages if isinstance(messages, list) else []


def _handle_context_status(req: dict[str, Any]) -> dict[str, Any]:
    from core.context import build_chip
    from core.context.coexist import detect_dcp, load_state, view_mode

    worktree = str(req.get("worktree", "") or ".")
    from core.context.coexist import ctx_enabled

    if not ctx_enabled():
        return {"ok": True, "mode": "off", "disabled": True, "chip": ""}
    engine = _engine_for(req)
    blocks = engine.store.load()
    restores = sum(b.restores for b in blocks)
    saved = sum(max(0, b.tokens_original - b.tokens_summary) for b in blocks)
    chip = build_chip(blocks_added=len(blocks), restores=restores) if blocks else ""
    return {
        "ok": True,
        "mode": view_mode(worktree),
        "dcp": detect_dcp(worktree),
        "decision": load_state(worktree)["decision"],
        "offer_shown": load_state(worktree)["offer_shown"],
        "session": engine.session_id,
        "blocks": len(blocks),
        "restores": restores,
        "tokens_saved": saved,
        "chip": chip,
    }


def _handle_context_view(req: dict[str, Any]) -> dict[str, Any]:
    from core.context import build_chip
    from core.context.coexist import ctx_enabled, view_mode
    from core.context.layer0 import total_tokens
    from core.context.view import build_view, view_segments

    worktree = str(req.get("worktree", "") or ".")
    if not ctx_enabled():
        return {"ok": True, "mode": "off", "segments": [], "chip": ""}
    mode = view_mode(worktree, dcp_hint=bool(req.get("dcp")))
    messages = _ctx_messages(req)
    if mode != "school" or not messages:
        return {"ok": True, "mode": mode, "segments": [], "chip": ""}
    engine = _engine_for(req)
    blocks = engine.store.load()
    segments = view_segments(messages, blocks)
    if not segments:
        return {"ok": True, "mode": mode, "segments": [], "chip": ""}
    before = total_tokens(messages)
    after = total_tokens(build_view(messages, blocks).messages)
    ratio = after / engine.window if engine.window > 0 else None
    chip = build_chip(used_ratio=ratio, saved_tokens=max(0, before - after))
    return {"ok": True, "mode": mode, "segments": segments, "chip": chip}


def _handle_context_compress(req: dict[str, Any]) -> dict[str, Any]:
    from core.context import build_chip
    from core.context.coexist import ctx_enabled, view_mode

    worktree = str(req.get("worktree", "") or ".")
    if not ctx_enabled():
        return {"ok": True, "disabled": True, "chip": ""}
    engine = _engine_for(req)
    report = engine.compress(_ctx_messages(req))
    chip = ""
    if report.triggered and report.blocks_added > 0:
        chip = build_chip(
            blocks_added=report.blocks_added,
            saved_tokens=max(0, report.tokens_before - report.tokens_after),
        )
    return {
        "ok": True,
        "mode": view_mode(worktree),
        "triggered": report.triggered,
        "skipped": report.skipped,
        "layer_used": report.layer_used,
        "blocks_added": report.blocks_added,
        "tokens_before": report.tokens_before,
        "tokens_after": report.tokens_after,
        "tokens_saved": max(0, report.tokens_before - report.tokens_after),
        "chip": chip,
    }


def _handle_context_restore(req: dict[str, Any]) -> dict[str, Any]:
    from core.context import build_chip
    from core.context.coexist import ctx_enabled, view_mode

    worktree = str(req.get("worktree", "") or ".")
    if not ctx_enabled():
        return {"ok": True, "disabled": True, "chip": ""}
    engine = _engine_for(req)
    payload = engine.restore(str(req.get("block_id", "") or ""))
    chip = ""
    if payload.get("ok"):
        blocks = engine.store.load()
        chip = build_chip(
            blocks_added=len(blocks), restores=int(payload.get("restores", 0))
        )
    return {**payload, "mode": view_mode(worktree), "chip": chip}


def _handle_context_coexist(req: dict[str, Any]) -> dict[str, Any]:
    from core.context.coexist import (
        OFFER_TEXT,
        detect_dcp,
        load_state,
        save_state,
        view_mode,
    )

    worktree = str(req.get("worktree", "") or ".")
    hint = bool(req.get("dcp"))
    action = str(req.get("action", "get") or "get")
    if action == "get":
        if hint:
            save_state(worktree, {"dcp_seen": True})
        state = load_state(worktree)
        return {
            "ok": True,
            "dcp": detect_dcp(worktree) or hint,
            "decision": state["decision"],
            "offer_shown": state["offer_shown"],
            "mode": view_mode(worktree, dcp_hint=hint),
            "offer": OFFER_TEXT,
        }
    if action == "set_offer":
        save_state(worktree, {"offer_shown": True})
        return {"ok": True, "offer_shown": True}
    if action == "set_decision":
        decision = str(req.get("decision", "") or "")
        if decision not in {"switch", "keep"}:
            return {
                "ok": False,
                "error": {
                    "type": "validation",
                    "message": "decision must be switch or keep",
                },
            }
        save_state(worktree, {"decision": decision})
        return {
            "ok": True,
            "decision": decision,
            "mode": view_mode(worktree, dcp_hint=hint),
        }
    return {
        "ok": False,
        "error": {"type": "validation", "message": f"unknown action: {action}"},
    }


# ---------------------------------------------------------------------------
# Command dispatch
# ---------------------------------------------------------------------------

def _handle_observe(req: dict[str, Any]) -> dict[str, Any]:
    from core.agent.observer import observe

    r = observe(
        worktree=str(req.get("worktree", "") or "."),
        observation=str(req.get("observation", "") or ""),
        category=str(req.get("category", "pattern") or "pattern"),
        evidence=req.get("evidence"),
    )
    return {
        "ok": r.ok,
        "observation_id": r.observation_id,
        "pattern": r.pattern,
        "learning": r.learning,
        "total": r.total,
        **({"error": r.error} if r.error else {}),
    }


def _handle_goal(req: dict[str, Any]) -> dict[str, Any]:
    from core.agent.goals import goal

    r = goal(
        worktree=str(req.get("worktree", "") or "."),
        action=str(req.get("action", "status") or "status"),
        goal_id=str(req.get("goal_id", "") or ""),
        objective=str(req.get("objective", "") or ""),
        success_criteria=str(req.get("success_criteria", "") or ""),
        max_turns=int(req.get("max_turns", 0) or 0),
        constraints=str(req.get("constraints", "") or ""),
    )
    return {
        "ok": r.ok,
        "action": r.action,
        "goal_id": r.goal_id,
        "state": r.state,
        "objective": r.objective,
        "progress": r.progress,
        "goals": r.goals,
        **({"error": r.error} if r.error else {}),
    }


def _handle_research(req: dict[str, Any]) -> dict[str, Any]:
    from core.agent.researcher import research

    r = research(
        worktree=str(req.get("worktree", "") or "."),
        query=str(req.get("query", "") or ""),
        depth=str(req.get("depth", "standard") or "standard"),
        fmt=str(req.get("format", "summary") or "summary"),
        cite=bool(req.get("cite", True)),
    )
    return {
        "ok": r.ok,
        "query": r.query,
        "depth": r.depth,
        "format": r.fmt,
        "findings": r.findings,
        "citations": r.citations,
        "learnings": r.learnings,
        "source": r.source,
        **({"error": r.error} if r.error else {}),
    }


def _handle_explore(req: dict[str, Any]) -> dict[str, Any]:
    from core.agent.explorer import explore

    r = explore(
        worktree=str(req.get("worktree", "") or "."),
        target=str(req.get("target", ".") or "."),
        depth=str(req.get("depth", "file") or "file"),
        focus=str(req.get("focus", "structure") or "structure"),
    )
    return {
        "ok": r.ok,
        "target": r.target,
        "structure": r.structure,
        "patterns": r.patterns,
        "conventions": r.conventions,
        **({"error": r.error} if r.error else {}),
    }


def _handle_progress(req: dict[str, Any]) -> dict[str, Any]:
    from core.agent.progress import progress

    r = progress(
        worktree=str(req.get("worktree", "") or "."),
        action=str(req.get("action", "read") or "read"),
        items=req.get("items"),
        context=str(req.get("context", "") or ""),
    )
    return {
        "ok": r.ok,
        "action": r.action,
        "items": r.items,
        "bars": r.bars,
        **({"error": r.error} if r.error else {}),
    }


def _handle_session(req: dict[str, Any]) -> dict[str, Any]:
    from core.agent.sessions import session

    r = session(
        worktree=str(req.get("worktree", "") or "."),
        action=str(req.get("action", "list") or "list"),
        session_id=str(req.get("session_id", "") or ""),
        focus=str(req.get("focus", "") or ""),
    )
    return {
        "ok": r.ok,
        "action": r.action,
        "session_id": r.session_id,
        "focus": r.focus,
        "summary": r.summary,
        "sessions": r.sessions,
        "data": r.data,
        **({"error": r.error} if r.error else {}),
    }


def _handle_execute(req: dict[str, Any]) -> dict[str, Any]:
    from core.agent.executor import execute

    env = req.get("env")
    r = execute(
        worktree=str(req.get("worktree", "") or "."),
        command=str(req.get("cmd", "") or req.get("command", "") or ""),
        learn=bool(req.get("learn", True)),
        context=str(req.get("context", "") or ""),
        timeout_ms=int(req.get("timeout_ms", 30000) or 30000),
        cwd=(str(req.get("cwd")) if req.get("cwd") else None),
        env={str(k): str(v) for k, v in env.items()} if isinstance(env, dict) else None,
        max_output=int(req.get("max_output", 10000) or 10000),
    )
    return {
        "ok": r.ok,
        "command": r.command,
        "exit_code": r.exit_code,
        "stdout": r.stdout[:2000],
        "stderr": r.stderr[:2000],
        "learned": r.learned,
        "duration_ms": r.duration_ms,
        "pid": r.pid,
        "cwd": r.cwd,
        "env_overrides": r.env_overrides,
        "truncated": r.truncated,
        **({"error": r.error} if r.error else {}),
    }


def _handle_navigate(req: dict[str, Any]) -> dict[str, Any]:
    from core.agent.navigator import navigate

    r = navigate(
        worktree=str(req.get("worktree", "") or "."),
        action=str(req.get("action", "list") or "list"),
        path=str(req.get("path", "") or ""),
        pattern=str(req.get("pattern", "") or ""),
        depth=int(req.get("depth", 3) or 3),
    )
    return {
        "ok": r.ok,
        "action": r.action,
        "path": r.path,
        "content": r.content[:4000],
        "entries": r.entries[:100],
        "matches": r.matches[:50],
        "tree": r.tree[:4000],
        **({"error": r.error} if r.error else {}),
    }


def _handle_workflow(req: dict[str, Any]) -> dict[str, Any]:
    from core.agent.workflows import workflow

    r = workflow(
        worktree=str(req.get("worktree", "") or "."),
        name=str(req.get("name", "") or ""),
        action=str(req.get("action", "start") or "start"),
        phase=req.get("phase"),
        notes=req.get("notes"),
    )
    return {
        "ok": r.ok,
        "workflow": r.workflow,
        "phase": r.phase,
        "phases": r.phases,
        "guidance": r.guidance,
        "state": r.state,
        **({"error": r.error} if r.error else {}),
    }


def _handle_docs(req: dict[str, Any]) -> dict[str, Any]:
    from core.agent.docfetcher import fetch_docs

    r = fetch_docs(
        worktree=str(req.get("worktree", "") or "."),
        query=str(req.get("query", "") or ""),
        library=req.get("library"),
        version=req.get("version"),
        use_cache=bool(req.get("use_cache", True)),
    )
    return {
        "ok": r.ok,
        "query": r.query,
        "source": r.source,
        "content": r.content[:8000],
        "cached": r.cached,
        "tokens_saved": r.tokens_saved,
        "learnings": r.learnings,
        **({"error": r.error} if r.error else {}),
    }


def _handle_visualize(req: dict[str, Any]) -> dict[str, Any]:
    """Render any School visual type. Works in CLI, OpenCode, and any agent."""
    from core.context.visual_dispatch import render_visual

    viz_type = str(req.get("type", "") or "dashboard")
    label = str(req.get("label", "") or "")
    data = req.get("data") or {}
    width = int(req.get("width", 20) or 20)

    try:
        output = render_visual(viz_type, data=data, label=label, width=width)
        return {"ok": True, "type": viz_type, "output": output}
    except ValueError as exc:
        return {"ok": False, "error": _err_text(exc)}
    except Exception as exc:
        return {"ok": False, "error": f"visualize error: {_err_text(exc)}"}


# ---------------------------------------------------------------------------
# Forge — Universal Idea→Artifact (clarion / blueprint / edict / weave /
# compass / prism). Universal by design: every artifact works for ANY kind of
# work — software, writing, research, business, planning, creative, life.
# State (Interview / BrainstormSession) round-trips via to_dict/from_dict so
# the stateless one-shot wire keeps state across calls. FAIL-OPEN everywhere:
# every handler catches broadly and returns a plain dict.
# ---------------------------------------------------------------------------


def _forge_interview(req: dict[str, Any]) -> Any:
    """Rebuild an Interview from ``req["interview"]``. Never raises."""
    from core.forge.models import Interview

    raw = req.get("interview")
    return Interview.from_dict(raw if isinstance(raw, dict) else {})


def _forge_session(req: dict[str, Any]) -> Any:
    """Rebuild a BrainstormSession from ``req["session"]``. Never raises."""
    from core.forge.models import BrainstormSession

    raw = req.get("session")
    return BrainstormSession.from_dict(raw if isinstance(raw, dict) else {})


def _forge_commands(req: dict[str, Any]) -> list[Any] | None:
    """Rebuild Command objects from ``req["commands"]``. Never raises."""
    from core.forge.models import Command

    raw = req.get("commands")
    if not isinstance(raw, list):
        return None
    return [Command.from_dict(c) for c in raw if isinstance(c, dict)]


def _forge_blueprint(req: dict[str, Any]) -> Any:
    """Rebuild a Blueprint from ``req["blueprint"]`` (None when absent)."""
    from core.forge.models import Blueprint

    raw = req.get("blueprint")
    return Blueprint.from_dict(raw) if isinstance(raw, dict) else None


def _handle_clarion(req: dict[str, Any]) -> dict[str, Any]:
    """clarion — adaptive requirements discovery interview (any domain).

    Actions: start | next | answer | auto | import | batch | summary.
    """
    from core.forge import clarion as forge_clarion
    from core.forge.models import Domain, InterviewMode

    action = str(req.get("action", "summary") or "summary").lower().strip()
    try:
        if action == "start":
            mode_raw = str(req.get("mode", "") or "").lower().strip()
            mode = (
                InterviewMode(mode_raw)
                if mode_raw in {m.value for m in InterviewMode}
                else InterviewMode.INTERVIEW
            )
            interview = forge_clarion.start_interview(
                title=str(req.get("title", "") or ""),
                domain=Domain.coerce(req.get("domain")),
                mode=mode,
                seed_questions=req.get("seed_questions"),
                existing_doc=req.get("existing_doc"),
            )
        else:
            interview = _forge_interview(req)
            if action == "next":
                question = forge_clarion.next_question(interview)
                return {
                    "ok": True,
                    "action": "next",
                    "interview": interview.to_dict(),
                    "question": question.to_dict() if question is not None else None,
                }
            if action == "answer":
                interview = forge_clarion.submit_answer(
                    interview,
                    req.get("question_id"),
                    req.get("value"),
                    is_custom=bool(req.get("is_custom", False)),
                    confidence=req.get("confidence", 1.0),
                )
            elif action == "auto":
                interview = forge_clarion.auto_answer(interview)
            elif action == "import":
                interview = forge_clarion.import_answers(
                    interview, req.get("doc_text")
                )
            elif action == "batch":
                interview = forge_clarion.batch_answer(
                    interview, req.get("answers")
                )
        out: dict[str, Any] = {
            "ok": True,
            "action": action,
            "interview": interview.to_dict(),
            "summary": forge_clarion.interview_summary(interview),
        }
        question = forge_clarion.next_question(interview)
        if question is not None:
            out["question"] = question.to_dict()
        return out
    except Exception as exc:  # noqa: BLE001 — fail-open
        return {"ok": False, "error": _err_text(exc)}


def _handle_blueprint(req: dict[str, Any]) -> dict[str, Any]:
    """blueprint — the design-spec artifact from a discovery interview."""
    try:
        from core.forge.blueprint import build_blueprint
        from core.forge.render import render_artifact

        interview = _forge_interview(req)
        title = req.get("title")
        r = build_blueprint(interview, title=str(title) if title else None)
        art = render_artifact("blueprint", r, interview)
        return {
            "ok": True,
            "blueprint": r.to_dict(),
            "title": art.title,
            "markdown": art.markdown,
            "visual": art.visual,
            "path": art.path,
            **({"error": r.error} if getattr(r, "error", None) else {}),
        }
    except Exception as exc:  # noqa: BLE001 — fail-open
        return {"ok": False, "error": _err_text(exc)}


def _handle_edict(req: dict[str, Any]) -> dict[str, Any]:
    """edict — ordered commands + always/never directives from an interview."""
    try:
        from core.forge.edict import build_edict
        from core.forge.render import render_artifact

        interview = _forge_interview(req)
        r = build_edict(interview, _forge_blueprint(req))
        art = render_artifact("edict", r, interview)
        return {
            "ok": True,
            "commands": [c.to_dict() for c in r.commands],
            "directives": [d.to_dict() for d in r.directives],
            "title": art.title,
            "markdown": art.markdown,
            "visual": art.visual,
            "path": art.path,
            **({"error": r.error} if getattr(r, "error", None) else {}),
        }
    except Exception as exc:  # noqa: BLE001 — fail-open
        return {"ok": False, "error": _err_text(exc)}


def _handle_weave(req: dict[str, Any]) -> dict[str, Any]:
    """weave — roadmap formation (phases/lanes/deps/critical path + timeline)."""
    try:
        from core.forge.render import render_artifact
        from core.forge.weave import build_weave

        interview = _forge_interview(req)
        r = build_weave(interview, _forge_commands(req), _forge_blueprint(req))
        art = render_artifact("weave", r, interview)
        return {
            "ok": True,
            "formation": r.to_dict(),
            "title": art.title,
            "markdown": art.markdown,
            "visual": art.visual,
            "timeline": art.visual,
            "path": art.path,
            **({"error": r.error} if getattr(r, "error", None) else {}),
        }
    except Exception as exc:  # noqa: BLE001 — fail-open
        return {"ok": False, "error": _err_text(exc)}


def _handle_compass(req: dict[str, Any]) -> dict[str, Any]:
    """compass — acceptance scenarios + checklist + success metrics."""
    try:
        from core.forge.compass import build_compass
        from core.forge.render import render_artifact

        interview = _forge_interview(req)
        r = build_compass(interview, _forge_blueprint(req), _forge_commands(req))
        art = render_artifact("compass", r, interview)
        return {
            "ok": True,
            "acceptance": r.to_dict(),
            "title": art.title,
            "markdown": art.markdown,
            "visual": art.visual,
            "path": art.path,
            **({"error": r.error} if getattr(r, "error", None) else {}),
        }
    except Exception as exc:  # noqa: BLE001 — fail-open
        return {"ok": False, "error": _err_text(exc)}


def _handle_prism(req: dict[str, Any]) -> dict[str, Any]:
    """prism — divergent→convergent brainstorming (any topic, any domain).

    Actions: brainstorm | score | select | cluster | summary.
    """
    from core.forge import prism as forge_prism
    from core.forge.models import Domain

    action = str(req.get("action", "brainstorm") or "brainstorm").lower().strip()
    try:
        if action == "brainstorm":
            session = forge_prism.brainstorm(
                req.get("topic"),
                domain=Domain.coerce(req.get("domain")),
                techniques=req.get("techniques"),
                count=req.get("count", 12),
                seed=req.get("seed"),
            )
        else:
            session = _forge_session(req)
            if action == "score":
                session = forge_prism.score_ideas(session, req.get("weights"))
            elif action == "select":
                session = forge_prism.select_top(session, req.get("n", 3))
            elif action == "cluster":
                return {
                    "ok": True,
                    "action": "cluster",
                    "session": session.to_dict(),
                    "clusters": forge_prism.cluster_ideas(session),
                    "summary": forge_prism.brainstorm_summary(session),
                }
        return {
            "ok": True,
            "action": action,
            "session": session.to_dict(),
            "ideas": [i.to_dict() for i in session.ideas],
            "selected": list(session.selected),
            "summary": forge_prism.brainstorm_summary(session),
        }
    except Exception as exc:  # noqa: BLE001 — fail-open
        return {"ok": False, "error": _err_text(exc)}


_COMMANDS = {
    "status": _handle_status,
    "remember": _handle_remember,
    "recall": _handle_recall,
    "learn": _handle_learn,
    "diagnose": _handle_diagnose,
    "conflict": _handle_conflict,
    "confidence": _handle_confidence,
    "deduplicate": _handle_deduplicate,
    "lifecycle": _handle_lifecycle,
    "search": _handle_search,
    "knowledge": _handle_knowledge,
    "skill_list": _handle_skill_list,
    "skill_search": _handle_skill_search,
    "skill_create": _handle_skill_create,
    "skill_use": _handle_skill_use,
    "skill_feedback": _handle_skill_feedback,
    "skill_status": _handle_skill_status,
    "skill_evolve": _handle_skill_evolve,
    "skill_search_github": _handle_skill_search_github,
    "skill_discover": _handle_skill_discover,
    "skill_analyze_external": _handle_skill_analyze_external,
    "skill_compare": _handle_skill_compare,
    "skill_import": _handle_skill_import,
    "skeleton": _handle_skeleton,
    "context_status": _handle_context_status,
    "context_compress": _handle_context_compress,
    "context_restore": _handle_context_restore,
    "context_view": _handle_context_view,
    "context_coexist": _handle_context_coexist,
    "observe": _handle_observe,
    "goal": _handle_goal,
    "research": _handle_research,
    "explore": _handle_explore,
    "progress": _handle_progress,
    "session": _handle_session,
    "execute": _handle_execute,
    "navigate": _handle_navigate,
    "workflow": _handle_workflow,
    "docs": _handle_docs,
    "visualize": _handle_visualize,
    "clarion": _handle_clarion,
    "blueprint": _handle_blueprint,
    "edict": _handle_edict,
    "weave": _handle_weave,
    "compass": _handle_compass,
    "prism": _handle_prism,
}


def main() -> None:
    """Read JSON from stdin, dispatch command, write JSON to stdout.

    FAIL-OPEN: every code path emits valid JSON and never raises. The bridge
    is the single wire for all tools — it must be impossible to fail.
    """
    resp: dict[str, Any]
    try:
        raw = sys.stdin.read()
        req = json.loads(raw)
    except json.JSONDecodeError as exc:
        resp = {
            "ok": False,
            "error": {"type": "protocol", "message": f"malformed JSON: {exc}"},
            "result": {},
        }
        _safe_dump(resp)
        return
    except Exception as exc:  # noqa: BLE001 — fail-open
        resp = {
            "ok": False,
            "error": {"type": "protocol", "message": f"stdin read error: {exc}"},
            "result": {},
        }
        _safe_dump(resp)
        return

    # Coerce req to a dict no matter what JSON arrived.
    if not isinstance(req, dict):
        resp = {
            "ok": False,
            "error": {"type": "protocol", "message": "request must be a JSON object"},
            "result": {},
        }
        _safe_dump(resp)
        return

    command = req.get("command", "")
    # FAIL-OPEN: a non-string (e.g. list/dict) command is unhashable — it must
    # degrade to the "unknown command" response, never a TypeError escape.
    handler = _COMMANDS.get(command) if isinstance(command, str) else None
    if handler is None:
        resp = {
            "ok": False,
            "error": {"type": "protocol", "message": f"unknown command: {_safe_str(command)}"},
            "result": {"commands": sorted(_COMMANDS.keys())},
        }
        _safe_dump(resp)
        return

    try:
        resp = handler(req)
    except Exception as exc:  # noqa: BLE001 — fail-open: handler crash is not fatal
        resp = {
            "ok": False,
            "error": {"type": "runtime", "message": _err_text(exc)},
            "result": {},
            "errors": [f"{type(exc).__name__}: {_err_text(exc)}"],
        }

    # Guarantee a well-formed response dict.
    if not isinstance(resp, dict):
        resp = {"ok": True, "result": resp}

    try:
        from core.context.visual_footer import add_visual_footer
        resp = add_visual_footer(resp, command, req)
    except Exception:  # noqa: BLE001 — fail-open: visuals never break a response
        pass  # fail-open: visuals never break a response

    _safe_dump(resp)


def _safe_dump(resp: dict[str, Any]) -> None:
    """Emit JSON to stdout, guaranteed to be valid strict JSON.

    Serialisation happens fully in memory before anything is written, so a
    failure can never leave partial output on the wire (the old streaming
    json.dump corrupted stdout with half a response followed by the fallback
    stub). Non-finite floats, lone surrogates and non-serialisable values are
    sanitised first (see _json_safe) so the emitted document is RFC 8259
    strict — the TypeScript plugin parses it with JSON.parse.
    """
    text: str | None = None
    try:
        text = json.dumps(_json_safe(resp), ensure_ascii=True, allow_nan=False)
    except Exception:  # noqa: BLE001 — fall back to the minimal stub
        text = None
    if text is None:
        try:
            text = json.dumps(
                {"ok": False, "error": {"type": "serialize"}}, allow_nan=False
            )
        except Exception:  # noqa: BLE001 — last-resort literal
            text = '{"ok": false, "error": {"type": "serialize"}}'
    with contextlib.suppress(Exception):
        sys.stdout.write(text)
    with contextlib.suppress(Exception):
        sys.stdout.flush()


if __name__ == "__main__":
    main()
