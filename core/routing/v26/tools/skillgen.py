"""1A-2Z skill generation tools (school_skill_*).

Thin adapters over core.skillgen: each tool reads its worktree, builds a
SkillPipeline on the scoped registry, and returns the pipeline report.
Fail-open: every execute() coerces hostile arguments safely and catches any
residual error, so the tools NEVER raise at the boundary.
"""

from __future__ import annotations

import functools
from typing import Any

from core.routing.v26.tools.base import Tool, ToolResult
from core.skillgen.pipeline import SkillPipeline
from core.skillgen.registry import registry_for
from core.skillgen.types import safe_int, safe_str


def _worktree_of(kwargs: dict) -> str:
    """Worktree for this call: str values pass through, junk falls back."""
    wt = kwargs.get("worktree")
    return wt if isinstance(wt, str) and wt else "."


def _pipeline(kwargs: dict) -> SkillPipeline:
    return SkillPipeline(registry_for(_worktree_of(kwargs)))


def _result(tool: str, data: Any) -> ToolResult:
    if not isinstance(data, dict):
        data = {"ok": False, "reason": "invalid_report", "detail": safe_str(data, 200)}
    ok = bool(data.get("ok", True))
    errors = [] if ok else [str(data.get("reason") or data.get("action") or "failed")]
    return ToolResult(success=ok, data=data, errors=errors, metadata={"tool": tool})


def _text_of(value: Any, limit: int = 200) -> str:
    """Optional text param: None/falsy -> '', hostile values -> safe str."""
    if value is None:
        return ""
    try:
        truthy = bool(value)
    except Exception:  # noqa: BLE001 - hostile __bool__
        return safe_str(value, limit)
    return safe_str(value, limit) if truthy else ""


def _bool_of(value: Any, default: bool = False) -> bool:
    """Safe truthiness coercion (hostile __bool__ included)."""
    if isinstance(value, bool):
        return value
    try:
        return bool(value)
    except Exception:  # noqa: BLE001 - hostile __bool__
        return default


def _fail_result(tool: str, exc: Exception) -> ToolResult:
    return ToolResult(
        success=False,
        data={"ok": False, "reason": f"internal_error:{type(exc).__name__}",
              "detail": safe_str(exc, 200)},
        errors=[f"internal error: {type(exc).__name__}"],
        metadata={"tool": tool},
    )


def _fail_open(fn):  # noqa: ANN001, ANN201 - decorator over Tool.execute
    """Boundary guard: a tool must return a result, never raise."""

    @functools.wraps(fn)
    def wrapper(self, **kwargs):  # noqa: ANN001, ANN201
        try:
            return fn(self, **kwargs)
        except Exception as exc:  # noqa: BLE001 - last-resort fail-open
            return _fail_result(safe_str(getattr(self, "name", "tool"), 100), exc)

    return wrapper


_SCOPE_PROPS = {
    "agent_id": {
        "type": "string",
        "description": "Agent identity for scope isolation.",
        "default": "opencode",
    },
    "project": {
        "type": "string",
        "description": "Project id for scope isolation.",
        "default": "",
    },
    "session": {
        "type": "string",
        "description": "Session id for scope isolation.",
        "default": "",
    },
}


class SkillListTool(Tool):
    """List skills in the 1A-2Z registry (state/scope/confidence)."""

    @property
    def name(self) -> str:
        return "school_skill_list"

    @property
    def description(self) -> str:
        return (
            "Use school_skill_list to list skills in the 1A-2Z registry with "
            "state, scope, confidence, and counters. Use after school_status "
            "when you need the full inventory rather than ranked matches."
        )

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "state": {
                    "type": "string",
                    "description": "Filter by lifecycle state.",
                    "default": "",
                },
                "scope": {
                    "type": "string",
                    "description": "Filter by scope.",
                    "default": "",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum skills returned.",
                    "default": 50,
                },
            },
            "required": [],
        }

    @_fail_open
    def execute(self, **kwargs) -> ToolResult:
        state = _text_of(kwargs.get("state"), 64)
        scope = _text_of(kwargs.get("scope"), 64)
        limit = safe_int(kwargs.get("limit"), 50)
        skills = []
        for s in _pipeline(kwargs).registry.all():
            if state and s.state.value != state:
                continue
            if scope and s.scope.value != scope:
                continue
            skills.append(
                {
                    "name": s.name,
                    "description": s.description,
                    "state": s.state.value,
                    "scope": s.scope.value,
                    "confidence": s.confidence,
                    "version": s.version,
                    "success_count": s.success_count,
                    "failure_count": s.failure_count,
                    "use_count": s.use_count,
                }
            )
        skills.sort(key=lambda d: (-d["confidence"], d["name"]))
        return _result(
            self.name, {"ok": True, "skills": skills[: max(1, limit)],
                        "count": len(skills)}
        )


class SkillSearchTool(Tool):
    """Scope-aware ranked skill retrieval for a task query."""

    @property
    def name(self) -> str:
        return "school_skill_search"

    @property
    def description(self) -> str:
        return (
            "Use school_skill_search to find reusable skills for a task query "
            "with scope-aware ranked matches. Use before solving a problem so "
            "proven techniques are reused first."
        )

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Task text to match against skills.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum matches returned.",
                    "default": 5,
                },
                "include_unusable": {
                    "type": "boolean",
                    "description": "Also include non-retrievable states.",
                    "default": False,
                },
                **_SCOPE_PROPS,
            },
            "required": ["query"],
        }

    @_fail_open
    def execute(self, **kwargs) -> ToolResult:
        query = _text_of(kwargs.get("query"), 20_000)
        if not query:
            return _result(self.name, {"ok": False, "reason": "query required"})
        from core.skillgen.matcher import match

        hits = match(
            _pipeline(kwargs).registry,
            query,
            agent_id=_text_of(kwargs.get("agent_id"), 200) or "opencode",
            project_id=_text_of(kwargs.get("project"), 200),
            session_id=_text_of(kwargs.get("session"), 200),
            include_unusable=_bool_of(kwargs.get("include_unusable")),
            limit=safe_int(kwargs.get("limit"), 5),
        )
        return _result(
            self.name, {"ok": True, "query": query, "matches": hits,
                        "count": len(hits)}
        )


class SkillCreateTool(Tool):
    """Agent-authored skill creation (validated, duplicate-checked, tested)."""

    @property
    def name(self) -> str:
        return "school_skill_create"

    @property
    def description(self) -> str:
        return (
            "Use school_skill_create to save a validated agent-authored skill: "
            "it is duplicate-checked, security-validated, and self-tested "
            "before activation. Use only when 1A-2Z has not already created a "
            "skill for this pattern."
        )

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "kebab-case skill name.",
                },
                "description": {
                    "type": "string",
                    "description": "One-line capability summary.",
                },
                "purpose": {"type": "string", "description": "Why it exists."},
                "triggers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "When to use the skill.",
                    "default": [],
                },
                "inputs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Expected inputs.",
                    "default": [],
                },
                "procedure": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ordered steps (plain instructions).",
                    "default": [],
                },
                "expected_output": {
                    "type": "string",
                    "description": "What success looks like.",
                    "default": "",
                },
                "constraints": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Safety/scope limits.",
                    "default": [],
                },
                "examples": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Usage examples.",
                    "default": [],
                },
                "scope": {
                    "type": "string",
                    "description": "GLOBAL|AGENT|PROJECT|SESSION.",
                    "default": "",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Searchable tags.",
                    "default": [],
                },
                **_SCOPE_PROPS,
            },
            "required": ["name", "description", "purpose", "procedure"],
        }

    @_fail_open
    def execute(self, **kwargs) -> ToolResult:
        payload = {
            k: kwargs.get(k)
            for k in (
                "name", "description", "purpose", "triggers", "inputs",
                "procedure", "expected_output", "constraints", "examples",
                "scope", "tags",
            )
            if kwargs.get(k) is not None
        }
        report = _pipeline(kwargs).create_manual(
            payload,
            agent_id=_text_of(kwargs.get("agent_id"), 200) or "opencode",
            project_id=_text_of(kwargs.get("project"), 200),
            session_id=_text_of(kwargs.get("session"), 200),
        )
        return _result(self.name, report)


class SkillUseTool(Tool):
    """Retrieve a skill for reuse (scope-checked) and record the use."""

    @property
    def name(self) -> str:
        return "school_skill_use"

    @property
    def description(self) -> str:
        return (
            "Use school_skill_use to retrieve one skill by name (or search by "
            "query) and record the reuse. Returns scope-checked SKILL.md "
            "content ready to follow."
        )

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Exact skill name.",
                    "default": "",
                },
                "query": {
                    "type": "string",
                    "description": "Task query when name is unknown.",
                    "default": "",
                },
                **_SCOPE_PROPS,
            },
            "required": [],
        }

    @_fail_open
    def execute(self, **kwargs) -> ToolResult:
        name = _text_of(kwargs.get("name"), 200)
        query = _text_of(kwargs.get("query"), 20_000)
        if not name and not query:
            return _result(self.name, {"ok": False, "reason": "name or query required"})
        report = _pipeline(kwargs).use(
            name=name,
            query=query,
            agent_id=_text_of(kwargs.get("agent_id"), 200) or "opencode",
            project_id=_text_of(kwargs.get("project"), 200),
            session_id=_text_of(kwargs.get("session"), 200),
        )
        return _result(self.name, report)


class SkillFeedbackTool(Tool):
    """Record a reuse outcome; updates confidence and lifecycle."""

    @property
    def name(self) -> str:
        return "school_skill_feedback"

    @property
    def description(self) -> str:
        return (
            "Use school_skill_feedback to report whether reusing a skill "
            "succeeded or failed, updating confidence and lifecycle. Call "
            "after applying a skill so it evolves."
        )

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Skill name."},
                "success": {
                    "type": "boolean",
                    "description": "Did the reuse work?",
                },
                "note": {
                    "type": "string",
                    "description": "Optional context.",
                    "default": "",
                },
                "agent_id": _SCOPE_PROPS["agent_id"],
            },
            "required": ["name", "success"],
        }

    @_fail_open
    def execute(self, **kwargs) -> ToolResult:
        name = _text_of(kwargs.get("name"), 200)
        success = kwargs.get("success")
        if not name:
            return _result(self.name, {"ok": False, "reason": "name required"})
        if not isinstance(success, bool):
            return _result(self.name, {"ok": False, "reason": "success (bool) required"})
        report = _pipeline(kwargs).feedback(
            name,
            success,
            note=_text_of(kwargs.get("note"), 500),
            agent_id=_text_of(kwargs.get("agent_id"), 200) or "opencode",
        )
        return _result(self.name, report)


class SkillStatusTool(Tool):
    """1A-2Z registry + model-budget observability."""

    @property
    def name(self) -> str:
        return "school_skill_status"

    @property
    def description(self) -> str:
        return (
            "Use school_skill_status for 1A-2Z counters: skills by state, "
            "model calls used versus budget, recent events, and registry "
            "health. Use when auditing the self-growing loop."
        )

    @property
    def schema(self) -> dict:
        return {"type": "object", "properties": {}, "required": []}

    @_fail_open
    def execute(self, **kwargs) -> ToolResult:
        return _result(self.name, _pipeline(kwargs).status())


class SkillEvolveTool(Tool):
    """Explicit evolution: consolidate duplicates or revise a skill."""

    @property
    def name(self) -> str:
        return "school_skill_evolve"

    @property
    def description(self) -> str:
        return (
            "Use school_skill_evolve to consolidate duplicate skills, revise a "
            "skill's fields with versioning, or recompute lifecycle states. "
            "Use for maintenance instead of creating near-duplicates."
        )

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "consolidate | revise | recompute.",
                    "default": "consolidate",
                },
                "name": {
                    "type": "string",
                    "description": "Skill to revise.",
                    "default": "",
                },
                "changes": {
                    "type": "object",
                    "description": "Field updates for revise.",
                    "default": {},
                },
                "agent_id": _SCOPE_PROPS["agent_id"],
            },
            "required": [],
        }

    @_fail_open
    def execute(self, **kwargs) -> ToolResult:
        changes = kwargs.get("changes")
        report = _pipeline(kwargs).evolve(
            action=_text_of(kwargs.get("action"), 32) or "consolidate",
            name=_text_of(kwargs.get("name"), 200),
            changes=changes if isinstance(changes, dict) else None,
            agent_id=_text_of(kwargs.get("agent_id"), 200) or "opencode",
        )
        return _result(self.name, report)


def create_skillgen_tools() -> list[Tool]:
    """The seven 1A-2Z surface tools, in approved order."""
    return [
        SkillListTool(),
        SkillSearchTool(),
        SkillCreateTool(),
        SkillUseTool(),
        SkillFeedbackTool(),
        SkillStatusTool(),
        SkillEvolveTool(),
    ]


__all__ = [
    "SkillListTool",
    "SkillSearchTool",
    "SkillCreateTool",
    "SkillUseTool",
    "SkillFeedbackTool",
    "SkillStatusTool",
    "SkillEvolveTool",
    "create_skillgen_tools",
]
