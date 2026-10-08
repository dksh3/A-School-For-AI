"""1A-2Z skill generation tools (school_skill_*).

Thin adapters over core.skillgen: each tool reads its worktree, builds a
SkillPipeline on the scoped registry, and returns the pipeline report.
"""

from __future__ import annotations

from core.routing.v26.tools.base import Tool, ToolResult
from core.skillgen.pipeline import SkillPipeline
from core.skillgen.registry import registry_for


def _pipeline(kwargs: dict) -> SkillPipeline:
    worktree = kwargs.get("worktree") or "."
    return SkillPipeline(registry_for(worktree))


def _result(tool: str, data: dict) -> ToolResult:
    ok = bool(data.get("ok", True))
    errors = [] if ok else [str(data.get("reason") or data.get("action") or "failed")]
    return ToolResult(success=ok, data=data, errors=errors, metadata={"tool": tool})


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

    def execute(self, **kwargs) -> ToolResult:
        state = str(kwargs.get("state") or "")
        scope = str(kwargs.get("scope") or "")
        limit = int(kwargs.get("limit") or 50)
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

    def execute(self, **kwargs) -> ToolResult:
        query = str(kwargs.get("query") or "")
        if not query:
            return _result(self.name, {"ok": False, "reason": "query required"})
        from core.skillgen.matcher import match

        hits = match(
            _pipeline(kwargs).registry,
            query,
            agent_id=str(kwargs.get("agent_id") or "opencode"),
            project_id=str(kwargs.get("project") or ""),
            session_id=str(kwargs.get("session") or ""),
            include_unusable=bool(kwargs.get("include_unusable") or False),
            limit=int(kwargs.get("limit") or 5),
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
            agent_id=str(kwargs.get("agent_id") or "opencode"),
            project_id=str(kwargs.get("project") or ""),
            session_id=str(kwargs.get("session") or ""),
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

    def execute(self, **kwargs) -> ToolResult:
        name = str(kwargs.get("name") or "")
        query = str(kwargs.get("query") or "")
        if not name and not query:
            return _result(self.name, {"ok": False, "reason": "name or query required"})
        report = _pipeline(kwargs).use(
            name=name,
            query=query,
            agent_id=str(kwargs.get("agent_id") or "opencode"),
            project_id=str(kwargs.get("project") or ""),
            session_id=str(kwargs.get("session") or ""),
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

    def execute(self, **kwargs) -> ToolResult:
        name = str(kwargs.get("name") or "")
        success = kwargs.get("success")
        if not name:
            return _result(self.name, {"ok": False, "reason": "name required"})
        if not isinstance(success, bool):
            return _result(self.name, {"ok": False, "reason": "success (bool) required"})
        report = _pipeline(kwargs).feedback(
            name,
            success,
            note=str(kwargs.get("note") or ""),
            agent_id=str(kwargs.get("agent_id") or "opencode"),
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

    def execute(self, **kwargs) -> ToolResult:
        report = _pipeline(kwargs).evolve(
            action=str(kwargs.get("action") or "consolidate"),
            name=str(kwargs.get("name") or ""),
            changes=kwargs.get("changes") or None,
            agent_id=str(kwargs.get("agent_id") or "opencode"),
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
