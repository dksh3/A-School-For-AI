"""Phase 2 orchestrator tools (school_skill_*): registration, gating, wiring.

Every dispatch runs against a tmp_path worktree. Network tools are exercised
either offline (SCHOOL_SKILLGEN_GITHUB_DISABLED) or with discovery functions
monkeypatched - no test ever reaches api.github.com or an external model.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import core.routing.v26.tools.skillgen_github as github_tools_module
from core.routing.v26.factory import create_orchestrator
from core.routing.v26.tools.skillgen_github import (
    SkillAnalyzeExternalTool,
    SkillCompareTool,
    SkillDiscoverTool,
    SkillImportTool,
    SkillSearchGithubTool,
    create_skillgen_github_tools,
)
from core.skillgen.registry import SkillRegistry

GITHUB_TOOL_NAMES = [
    "school_skill_search_github",
    "school_skill_discover",
    "school_skill_analyze_external",
    "school_skill_compare",
    "school_skill_import",
]

DISPATCH_KWARGS: dict[str, dict[str, Any]] = {
    "school_skill_search_github": {"capability_gap": "format markdown tables"},
    "school_skill_discover": {"capability_gap": "format markdown tables"},
    "school_skill_analyze_external": {"owner": "acme", "repo": "markdown-tools"},
    "school_skill_compare": {"owner": "acme", "repo": "markdown-tools"},
    "school_skill_import": {
        "owner": "acme",
        "repo": "markdown-tools",
        "approve": True,
    },
}


def ok_discovery(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {"ok": True}


class TestRegistration:
    def test_all_five_tools_registered_in_approved_order(self) -> None:
        names = [t.name for t in create_skillgen_github_tools()]
        assert names == GITHUB_TOOL_NAMES

    def test_orchestrator_knows_every_github_tool(self, tmp_path: Path) -> None:
        orch = create_orchestrator()
        for name in GITHUB_TOOL_NAMES:
            result = orch.dispatch(name, worktree=str(tmp_path))
            assert not any("Unknown tool" in e for e in result.errors), name

    def test_search_and_discover_schema_require_nothing(self) -> None:
        assert SkillSearchGithubTool().schema["required"] == []
        assert SkillDiscoverTool().schema["required"] == []

    def test_analyze_schema_requires_owner_repo(self) -> None:
        assert SkillAnalyzeExternalTool().schema["required"] == ["owner", "repo"]

    def test_compare_schema_requires_owner_repo(self) -> None:
        assert SkillCompareTool().schema["required"] == ["owner", "repo"]

    def test_import_schema_requires_owner_repo_approve(self) -> None:
        assert SkillImportTool().schema["required"] == ["owner", "repo", "approve"]


class TestOfflineFailClosed:
    def test_every_network_tool_fails_closed_when_disabled(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SCHOOL_SKILLGEN_GITHUB_DISABLED", "1")
        orch = create_orchestrator()
        for name, kwargs in DISPATCH_KWARGS.items():
            result = orch.dispatch(name, worktree=str(tmp_path), **kwargs)
            assert result.success is False, name
            assert result.data["ok"] is False, name
            assert result.data["offline"] is True, name
            assert result.data["reason"] == "github_disabled", name
            assert result.errors, name

    def test_results_are_structured_when_discovery_succeeds(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(github_tools_module.discovery, "search_github", ok_discovery)
        monkeypatch.setattr(github_tools_module.discovery, "discover", ok_discovery)
        monkeypatch.setattr(
            github_tools_module.discovery, "analyze_external", ok_discovery
        )
        monkeypatch.setattr(github_tools_module.discovery, "compare", ok_discovery)
        monkeypatch.setattr(
            github_tools_module.discovery, "import_external", ok_discovery
        )
        orch = create_orchestrator()
        for name, kwargs in DISPATCH_KWARGS.items():
            result = orch.dispatch(name, worktree=str(tmp_path), **kwargs)
            assert result.success is True, name
            assert result.data["ok"] is True, name
            assert result.errors == [], name
            assert result.metadata == {"tool": name}, name

    def test_analyze_without_owner_and_repo(self, tmp_path: Path) -> None:
        result = create_orchestrator().dispatch(
            "school_skill_analyze_external", worktree=str(tmp_path)
        )
        assert result.success is False
        assert result.data["reason"] == "owner and repo required"

    def test_compare_without_owner_and_repo(self, tmp_path: Path) -> None:
        result = create_orchestrator().dispatch(
            "school_skill_compare", worktree=str(tmp_path)
        )
        assert result.success is False
        assert result.data["reason"] == "owner and repo required"

    def test_import_without_owner_and_repo(self, tmp_path: Path) -> None:
        result = create_orchestrator().dispatch(
            "school_skill_import", worktree=str(tmp_path), approve=True
        )
        assert result.success is False
        assert result.data["reason"] == "owner and repo required"


class TestKwargForwarding:
    def test_search_forwards_gap_kwargs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def fake(**kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return {"ok": True}

        monkeypatch.setattr(github_tools_module.discovery, "search_github", fake)
        result = create_orchestrator().dispatch(
            "school_skill_search_github",
            worktree=str(tmp_path),
            task="current task",
            capability_gap="missing capability",
            keywords=["alpha", "beta"],
            skill_name="known-skill",
        )
        assert result.success is True
        assert captured["task"] == "current task"
        assert captured["capability_gap"] == "missing capability"
        assert captured["keywords"] == ["alpha", "beta"]
        assert captured["skill_name"] == "known-skill"

    def test_discover_forwards_gap_kwargs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def fake(**kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return {"ok": True}

        monkeypatch.setattr(github_tools_module.discovery, "discover", fake)
        result = create_orchestrator().dispatch(
            "school_skill_discover",
            worktree=str(tmp_path),
            task="current task",
            capability_gap="missing capability",
            keywords=["gamma"],
            skill_name="",
        )
        assert result.success is True
        assert captured["task"] == "current task"
        assert captured["capability_gap"] == "missing capability"
        assert captured["keywords"] == ["gamma"]
        assert captured["skill_name"] == ""

    def test_analyze_forwards_owner_repo_task_and_registry(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def fake(owner: str, repo: str, **kwargs: Any) -> dict[str, Any]:
            captured["owner"] = owner
            captured["repo"] = repo
            captured.update(kwargs)
            return {"ok": True}

        monkeypatch.setattr(github_tools_module.discovery, "analyze_external", fake)
        result = create_orchestrator().dispatch(
            "school_skill_analyze_external",
            worktree=str(tmp_path),
            owner="acme",
            repo="markdown-tools",
            file_path="skills/SKILL.md",
            task="format tables",
        )
        assert result.success is True
        assert captured["owner"] == "acme"
        assert captured["repo"] == "markdown-tools"
        assert captured["file_path"] == "skills/SKILL.md"
        assert captured["task"] == "format tables"
        assert isinstance(captured["registry"], SkillRegistry)
        assert str(tmp_path) in str(captured["registry"].path)

    def test_compare_forwards_owner_repo_and_registry(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def fake(owner: str, repo: str, **kwargs: Any) -> dict[str, Any]:
            captured["owner"] = owner
            captured["repo"] = repo
            captured.update(kwargs)
            return {"ok": True}

        monkeypatch.setattr(github_tools_module.discovery, "compare", fake)
        result = create_orchestrator().dispatch(
            "school_skill_compare",
            worktree=str(tmp_path),
            owner="acme",
            repo="markdown-tools",
        )
        assert result.success is True
        assert captured["owner"] == "acme"
        assert captured["repo"] == "markdown-tools"
        assert isinstance(captured["registry"], SkillRegistry)
        assert str(tmp_path) in str(captured["registry"].path)

    def test_import_forwards_approval_scope_and_identity(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def fake(owner: str, repo: str, **kwargs: Any) -> dict[str, Any]:
            captured["owner"] = owner
            captured["repo"] = repo
            captured.update(kwargs)
            return {"ok": True}

        monkeypatch.setattr(github_tools_module.discovery, "import_external", fake)
        result = create_orchestrator().dispatch(
            "school_skill_import",
            worktree=str(tmp_path),
            owner="acme",
            repo="markdown-tools",
            file_path="skills/SKILL.md",
            approve=False,
            scope="project",
            acknowledge_license=True,
            agent_id="agent-9",
            project="proj-1",
            session="sess-1",
        )
        assert result.success is True
        assert captured["owner"] == "acme"
        assert captured["repo"] == "markdown-tools"
        assert captured["file_path"] == "skills/SKILL.md"
        assert captured["approve"] is False
        assert captured["scope"] == "project"
        assert captured["acknowledge_license"] is True
        assert captured["agent_id"] == "agent-9"
        assert captured["project_id"] == "proj-1"
        assert captured["session_id"] == "sess-1"
        assert isinstance(captured["registry"], SkillRegistry)

    def test_import_approve_omitted_stays_false(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def fake(owner: str, repo: str, **kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return {"ok": True}

        monkeypatch.setattr(github_tools_module.discovery, "import_external", fake)
        create_orchestrator().dispatch(
            "school_skill_import",
            worktree=str(tmp_path),
            owner="acme",
            repo="markdown-tools",
        )
        assert captured["approve"] is False

    def test_import_approve_boolean_true_forwarded(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def fake(owner: str, repo: str, **kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return {"ok": True, "action": "imported", "name": "markdown-table-tools"}

        monkeypatch.setattr(github_tools_module.discovery, "import_external", fake)
        result = create_orchestrator().dispatch(
            "school_skill_import",
            worktree=str(tmp_path),
            owner="acme",
            repo="markdown-tools",
            approve=True,
        )
        assert result.success is True
        assert captured["approve"] is True
        assert result.data["action"] == "imported"
