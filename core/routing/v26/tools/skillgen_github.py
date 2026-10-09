"""1A-2Z Phase 2 tools: GitHub skill discovery (school_skill_*).

Thin adapters over core.skillgen.github: each tool is opt-in, network-bound
discovery only (no Phase 1 tool ever performs network I/O). Failures return
structured errors; local skillgen keeps working offline. Fail-open: hostile
arguments and any residual discovery error convert to structured errors -
these tools NEVER raise at the boundary.
"""

from __future__ import annotations

from typing import Any

from core.routing.v26.tools.base import Tool, ToolResult
from core.routing.v26.tools.skillgen import (
    _SCOPE_PROPS,
    _bool_of,
    _fail_open,
    _result,
    _text_of,
    _worktree_of,
)
from core.skillgen.github import discovery
from core.skillgen.registry import registry_for
from core.skillgen.types import safe_list_str, safe_str


def _error_report(exc: Exception) -> dict[str, Any]:
    """Convert an unexpected discovery-layer failure to a structured report."""
    return {
        "ok": False,
        "reason": f"internal_error:{type(exc).__name__}",
        "detail": safe_str(exc, 200),
    }


def _keywords_of(value: Any) -> list[str]:
    return safe_list_str(value, 8, 64)

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

    @_fail_open
    def execute(self, **kwargs) -> ToolResult:
        try:
            report = discovery.search_github(
                task=_text_of(kwargs.get("task"), 2000),
                capability_gap=_text_of(kwargs.get("capability_gap"), 2000),
                keywords=_keywords_of(kwargs.get("keywords")),
                skill_name=_text_of(kwargs.get("skill_name"), 200),
            )
        except Exception as exc:  # noqa: BLE001 - discovery layer is untrusted
            report = _error_report(exc)
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

    @_fail_open
    def execute(self, **kwargs) -> ToolResult:
        try:
            report = discovery.discover(
                task=_text_of(kwargs.get("task"), 2000),
                capability_gap=_text_of(kwargs.get("capability_gap"), 2000),
                keywords=_keywords_of(kwargs.get("keywords")),
                skill_name=_text_of(kwargs.get("skill_name"), 200),
            )
        except Exception as exc:  # noqa: BLE001 - discovery layer is untrusted
            report = _error_report(exc)
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

    @_fail_open
    def execute(self, **kwargs) -> ToolResult:
        owner = _text_of(kwargs.get("owner"), 200).strip()
        repo = _text_of(kwargs.get("repo"), 200).strip()
        if not owner or not repo:
            return _result(self.name, {"ok": False, "reason": "owner and repo required"})
        try:
            report = discovery.analyze_external(
                owner,
                repo,
                file_path=_text_of(kwargs.get("file_path"), 500),
                task=_text_of(kwargs.get("task"), 2000),
                registry=registry_for(_worktree_of(kwargs)),
            )
        except Exception as exc:  # noqa: BLE001 - discovery layer is untrusted
            report = _error_report(exc)
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

    @_fail_open
    def execute(self, **kwargs) -> ToolResult:
        owner = _text_of(kwargs.get("owner"), 200).strip()
        repo = _text_of(kwargs.get("repo"), 200).strip()
        if not owner or not repo:
            return _result(self.name, {"ok": False, "reason": "owner and repo required"})
        try:
            report = discovery.compare(
                owner,
                repo,
                file_path=_text_of(kwargs.get("file_path"), 500),
                registry=registry_for(_worktree_of(kwargs)),
            )
        except Exception as exc:  # noqa: BLE001 - discovery layer is untrusted
            report = _error_report(exc)
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

    @_fail_open
    def execute(self, **kwargs) -> ToolResult:
        owner = _text_of(kwargs.get("owner"), 200).strip()
        repo = _text_of(kwargs.get("repo"), 200).strip()
        if not owner or not repo:
            return _result(self.name, {"ok": False, "reason": "owner and repo required"})
        try:
            report = discovery.import_external(
                owner,
                repo,
                file_path=_text_of(kwargs.get("file_path"), 500),
                approve=_bool_of(kwargs.get("approve")),
                scope=_text_of(kwargs.get("scope"), 32) or "agent",
                acknowledge_license=_bool_of(kwargs.get("acknowledge_license")),
                registry=registry_for(_worktree_of(kwargs)),
                agent_id=_text_of(kwargs.get("agent_id"), 200) or "opencode",
                project_id=_text_of(kwargs.get("project"), 200),
                session_id=_text_of(kwargs.get("session"), 200),
            )
        except Exception as exc:  # noqa: BLE001 - discovery layer is untrusted
            report = _error_report(exc)
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
