"""1A-2Z Phase 2 tools: GitHub skill discovery (school_skill_*).

Thin adapters over core.skillgen.github: each tool is opt-in, network-bound
discovery only (no Phase 1 tool ever performs network I/O). Failures return
structured errors; local skillgen keeps working offline.
"""

from __future__ import annotations

from core.routing.v26.tools.base import Tool, ToolResult
from core.routing.v26.tools.skillgen import _SCOPE_PROPS, _result
from core.skillgen.github import discovery
from core.skillgen.registry import registry_for

_GAP_PROPS = {
    "task": {
        "type": "string",
        "description": "Current task driving the capability gap.",
        "default": "",
    },
    "capability_gap": {
        "type": "string",
        "description": "Missing capability to search for (preferred over task).",
        "default": "",
    },
    "keywords": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Extra focused keywords (no conversation content).",
        "default": [],
    },
    "skill_name": {
        "type": "string",
        "description": "Known skill name to find equivalents for.",
        "default": "",
    },
}

_REPO_PROPS = {
    "owner": {"type": "string", "description": "GitHub repository owner."},
    "repo": {"type": "string", "description": "GitHub repository name."},
    "file_path": {
        "type": "string",
        "description": "Specific skill file path inside the repository.",
        "default": "",
    },
}


class SkillSearchGithubTool(Tool):
    """Bounded GitHub repository search for a capability gap (read-only)."""

    @property
    def name(self) -> str:
        return "school_skill_search_github"

    @property
    def description(self) -> str:
        return (
            "Use school_skill_search_github to run bounded GitHub repository "
            "searches for a capability gap and return candidate skill sources. "
            "Read-only; network required. Use only when local skills are "
            "insufficient."
        )

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {**_GAP_PROPS},
            "required": [],
        }

    def execute(self, **kwargs) -> ToolResult:
        report = discovery.search_github(
            task=str(kwargs.get("task") or ""),
            capability_gap=str(kwargs.get("capability_gap") or ""),
            keywords=[str(k) for k in (kwargs.get("keywords") or [])][:8],
            skill_name=str(kwargs.get("skill_name") or ""),
        )
        return _result(self.name, report)


class SkillDiscoverTool(Tool):
    """Deterministic GitHub discovery pass: filter + classify, no model."""

    @property
    def name(self) -> str:
        return "school_skill_discover"

    @property
    def description(self) -> str:
        return (
            "Use school_skill_discover to scan GitHub search results for "
            "skill-like files with deterministic filtering and security "
            "classification. Returns candidates for analysis; never downloads "
            "repositories or executes code."
        )

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {**_GAP_PROPS},
            "required": [],
        }

    def execute(self, **kwargs) -> ToolResult:
        report = discovery.discover(
            task=str(kwargs.get("task") or ""),
            capability_gap=str(kwargs.get("capability_gap") or ""),
            keywords=[str(k) for k in (kwargs.get("keywords") or [])][:8],
            skill_name=str(kwargs.get("skill_name") or ""),
        )
        return _result(self.name, report)


class SkillAnalyzeExternalTool(Tool):
    """Budgeted model analysis of one GitHub candidate (fail closed)."""

    @property
    def name(self) -> str:
        return "school_skill_analyze_external"

    @property
    def description(self) -> str:
        return (
            "Use school_skill_analyze_external to run budgeted model analysis "
            "on one GitHub candidate: relevance, quality, security, and local "
            "duplication. Read-only and fail-closed; malformed model output "
            "rejects the candidate."
        )

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                **_REPO_PROPS,
                "task": _GAP_PROPS["task"],
            },
            "required": ["owner", "repo"],
        }

    def execute(self, **kwargs) -> ToolResult:
        owner = str(kwargs.get("owner") or "")
        repo = str(kwargs.get("repo") or "")
        if not owner or not repo:
            return _result(self.name, {"ok": False, "reason": "owner and repo required"})
        report = discovery.analyze_external(
            owner,
            repo,
            file_path=str(kwargs.get("file_path") or ""),
            task=str(kwargs.get("task") or ""),
            registry=registry_for(kwargs.get("worktree") or "."),
        )
        return _result(self.name, report)


class SkillCompareTool(Tool):
    """Duplicate/improvement comparison of a GitHub candidate vs local skills."""

    @property
    def name(self) -> str:
        return "school_skill_compare"

    @property
    def description(self) -> str:
        return (
            "Use school_skill_compare to compare a GitHub candidate against "
            "local skills for duplicates or improvement. Read-only; any local "
            "skill change still requires explicit approval via "
            "school_skill_evolve."
        )

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {**_REPO_PROPS},
            "required": ["owner", "repo"],
        }

    def execute(self, **kwargs) -> ToolResult:
        owner = str(kwargs.get("owner") or "")
        repo = str(kwargs.get("repo") or "")
        if not owner or not repo:
            return _result(self.name, {"ok": False, "reason": "owner and repo required"})
        report = discovery.compare(
            owner,
            repo,
            file_path=str(kwargs.get("file_path") or ""),
            registry=registry_for(kwargs.get("worktree") or "."),
        )
        return _result(self.name, report)


class SkillImportTool(Tool):
    """Explicit-approval import of a reviewed GitHub candidate (mutating)."""

    @property
    def name(self) -> str:
        return "school_skill_import"

    @property
    def description(self) -> str:
        return (
            "Use school_skill_import to import an approved GitHub candidate "
            "into the local registry after user review. Requires approve=true; "
            "imported skills enter the Phase 1 lifecycle as CANDIDATE, never "
            "auto-PROVEN."
        )

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                **_REPO_PROPS,
                "approve": {
                    "type": "boolean",
                    "description": "Explicit user approval to import (required).",
                },
                "scope": {
                    "type": "string",
                    "description": "GLOBAL|AGENT|PROJECT|SESSION (default agent).",
                    "default": "agent",
                },
                "acknowledge_license": {
                    "type": "boolean",
                    "description": "User acknowledged UNKNOWN license review.",
                    "default": False,
                },
                "agent_id": _SCOPE_PROPS["agent_id"],
                "project": _SCOPE_PROPS["project"],
                "session": _SCOPE_PROPS["session"],
            },
            "required": ["owner", "repo", "approve"],
        }

    def execute(self, **kwargs) -> ToolResult:
        owner = str(kwargs.get("owner") or "")
        repo = str(kwargs.get("repo") or "")
        if not owner or not repo:
            return _result(self.name, {"ok": False, "reason": "owner and repo required"})
        report = discovery.import_external(
            owner,
            repo,
            file_path=str(kwargs.get("file_path") or ""),
            approve=bool(kwargs.get("approve")),
            scope=str(kwargs.get("scope") or "agent"),
            acknowledge_license=bool(kwargs.get("acknowledge_license")),
            registry=registry_for(kwargs.get("worktree") or "."),
            agent_id=str(kwargs.get("agent_id") or "opencode"),
            project_id=str(kwargs.get("project") or ""),
            session_id=str(kwargs.get("session") or ""),
        )
        return _result(self.name, report)


def create_skillgen_github_tools() -> list[Tool]:
    """The five Phase 2 discovery tools, in approved order."""
    return [
        SkillSearchGithubTool(),
        SkillDiscoverTool(),
        SkillAnalyzeExternalTool(),
        SkillCompareTool(),
        SkillImportTool(),
    ]


__all__ = [
    "SkillAnalyzeExternalTool",
    "SkillCompareTool",
    "SkillDiscoverTool",
    "SkillImportTool",
    "SkillSearchGithubTool",
    "create_skillgen_github_tools",
]
