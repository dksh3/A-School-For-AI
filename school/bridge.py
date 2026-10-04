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

import json
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
    orch = _get_orchestrator(req.get("worktree", ""))
    params = {k: v for k, v in req.items() if k != "command"}
    result = orch.dispatch(tool_name, **params)
    return {"ok": result.success, "result": result.data, "errors": result.errors}

def _handle_learn(req): return _dispatch_to_orchestrator("school_remember", req)
def _handle_diagnose(req): return _dispatch_to_orchestrator("school_diagnose", req)
def _handle_conflict(req): return _dispatch_to_orchestrator("school_conflict", req)
def _handle_confidence(req): return _dispatch_to_orchestrator("school_confidence", req)
def _handle_deduplicate(req): return _dispatch_to_orchestrator("school_deduplicate", req)
def _handle_lifecycle(req): return _dispatch_to_orchestrator("school_lifecycle", req)
def _handle_search(req): return _dispatch_to_orchestrator("school_search", req)
def _handle_knowledge(req): return _dispatch_to_orchestrator("school_knowledge", req)


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


# ---------------------------------------------------------------------------
# Command dispatch
# ---------------------------------------------------------------------------

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
    "skeleton": _handle_skeleton,
}


def main() -> None:
    """Read JSON from stdin, dispatch command, write JSON to stdout."""
    try:
        raw = sys.stdin.read()
        req = json.loads(raw)
    except json.JSONDecodeError as exc:
        resp = {"ok": False, "error": {"type": "protocol", "message": f"malformed JSON: {exc}"}}
        json.dump(resp, sys.stdout)
        return
    except Exception as exc:
        resp = {"ok": False, "error": {"type": "protocol", "message": f"stdin read error: {exc}"}}
        json.dump(resp, sys.stdout)
        return

    command = req.get("command", "")
    handler = _COMMANDS.get(command)
    if handler is None:
        resp = {
            "ok": False,
            "error": {"type": "protocol", "message": f"unknown command: {command}"},
        }
        json.dump(resp, sys.stdout)
        return

    try:
        resp = handler(req)
    except Exception as exc:
        resp = {"ok": False, "error": {"type": "runtime", "message": str(exc)}}

    json.dump(resp, sys.stdout)


if __name__ == "__main__":
    main()
