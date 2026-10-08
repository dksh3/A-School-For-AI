"""1A-2Z: orchestrator tools (school_skill_*) and bridge command wiring."""

from __future__ import annotations

from pathlib import Path

from core.routing.v26.factory import create_orchestrator
from core.routing.v26.tools.skillgen import create_skillgen_tools

SKILL_TOOLS = [
    "school_skill_list",
    "school_skill_search",
    "school_skill_create",
    "school_skill_use",
    "school_skill_feedback",
    "school_skill_status",
    "school_skill_evolve",
]


def _orch():
    return create_orchestrator()


def _payload(**kw) -> dict:
    payload = {
        "name": "quarantine-flaky-tests",
        "description": "Quarantine and stabilize flaky tests",
        "purpose": "Stop flaky tests from blocking CI",
        "triggers": ["flaky test quarantine"],
        "procedure": ["Identify the flaky test", "Quarantine and rerun"],
    }
    payload.update(kw)
    return payload


class TestRegistration:
    def test_seven_tools_in_approved_order(self) -> None:
        assert [t.name for t in create_skillgen_tools()] == SKILL_TOOLS

    def test_none_are_unknown_to_orchestrator(self, tmp_path: Path) -> None:
        orch = _orch()
        for name in SKILL_TOOLS:
            result = orch.dispatch(name, worktree=str(tmp_path))
            assert not any("Unknown tool" in e for e in result.errors), name

    def test_create_schema_required_fields(self) -> None:
        from core.routing.v26.tools.skillgen import SkillCreateTool

        assert SkillCreateTool().schema["required"] == [
            "name", "description", "purpose", "procedure"
        ]

    def test_feedback_schema_requires_success(self) -> None:
        from core.routing.v26.tools.skillgen import SkillFeedbackTool

        assert "success" in SkillFeedbackTool().schema["required"]

    def test_search_schema_requires_query(self) -> None:
        from core.routing.v26.tools.skillgen import SkillSearchTool

        assert SkillSearchTool().schema["required"] == ["query"]


class TestToolLoop:
    def test_status_on_empty_registry(self, tmp_path: Path) -> None:
        result = _orch().dispatch("school_skill_status", worktree=str(tmp_path))
        assert result.success is True
        assert result.data["ok"] is True
        assert result.data["skills"] == 0
        assert result.data["by_state"] == {}

    def test_create_then_search_use_feedback_list(
        self, tmp_path: Path
    ) -> None:
        wt = str(tmp_path)
        orch = _orch()

        created = orch.dispatch("school_skill_create", worktree=wt, **_payload())
        assert created.success is True
        assert created.data["action"] == "created"
        assert created.data["state"] == "active"

        searched = orch.dispatch(
            "school_skill_search", worktree=wt, query="quarantine flaky test"
        )
        assert searched.success is True
        assert searched.data["count"] >= 1
        assert searched.data["matches"][0]["name"] == "quarantine-flaky-tests"

        used = orch.dispatch(
            "school_skill_use", worktree=wt, name="quarantine-flaky-tests"
        )
        assert used.success is True
        assert "name: quarantine-flaky-tests" in used.data["markdown"]

        feedback = orch.dispatch(
            "school_skill_feedback",
            worktree=wt,
            name="quarantine-flaky-tests",
            success=True,
            note="verified",
        )
        assert feedback.success is True
        assert feedback.data["confidence"] > 0.5
        assert feedback.data["success_count"] == 1

        listed = orch.dispatch("school_skill_list", worktree=wt)
        assert listed.success is True
        assert listed.data["count"] == 1
        assert listed.data["skills"][0]["name"] == "quarantine-flaky-tests"
        assert listed.data["skills"][0]["state"] == "active"

        status = orch.dispatch("school_skill_status", worktree=wt)
        assert status.success is True
        assert status.data["skills"] == 1

    def test_search_without_query_fails(self, tmp_path: Path) -> None:
        result = _orch().dispatch("school_skill_search", worktree=str(tmp_path))
        assert result.success is False
        assert "query required" in result.errors[0]

    def test_feedback_without_success_fails(self, tmp_path: Path) -> None:
        result = _orch().dispatch(
            "school_skill_feedback",
            worktree=str(tmp_path),
            name="quarantine-flaky-tests",
        )
        assert result.success is False
        assert "success (bool) required" in result.errors[0]

    def test_create_without_purpose_fails_validation(self, tmp_path: Path) -> None:
        result = _orch().dispatch(
            "school_skill_create",
            worktree=str(tmp_path),
            **_payload(purpose=""),
        )
        assert result.success is False
        assert result.data["action"] == "rejected:validation"

    def test_evolve_revise_and_consolidate(self, tmp_path: Path) -> None:
        wt = str(tmp_path)
        orch = _orch()
        orch.dispatch("school_skill_create", worktree=wt, **_payload())

        revised = orch.dispatch(
            "school_skill_evolve",
            worktree=wt,
            action="revise",
            name="quarantine-flaky-tests",
            changes={"description": "Updated by evolve"},
        )
        assert revised.success is True
        assert revised.data["version"] == 2

        consolidated = orch.dispatch(
            "school_skill_evolve", worktree=wt, action="consolidate"
        )
        assert consolidated.success is True
        assert consolidated.data["count"] == 0

    def test_scoped_search_uses_agent_project_session(
        self, tmp_path: Path
    ) -> None:
        wt = str(tmp_path)
        orch = _orch()
        orch.dispatch(
            "school_skill_create",
            worktree=wt,
            project="p1",
            **_payload(),
        )
        visible = orch.dispatch(
            "school_skill_search",
            worktree=wt,
            query="quarantine flaky test",
            project="p1",
        )
        assert visible.data["count"] == 1
        hidden = orch.dispatch(
            "school_skill_search",
            worktree=wt,
            query="quarantine flaky test",
            project="p2",
        )
        assert hidden.data["count"] == 0


class TestBridgeWiring:
    def test_bridge_exposes_all_seven_commands(self) -> None:
        import school.bridge as bridge

        commands = set(bridge._COMMANDS)
        expected = {
            "skill_list", "skill_search", "skill_create", "skill_use",
            "skill_feedback", "skill_status", "skill_evolve",
        }
        assert expected <= commands

    def test_bridge_skill_command_dispatches(self, tmp_path: Path) -> None:
        import school.bridge as bridge

        handler = bridge._COMMANDS["skill_status"]
        response = handler({"command": "skill_status", "worktree": str(tmp_path)})
        assert response["ok"] is True
        assert response["result"]["skills"] == 0
