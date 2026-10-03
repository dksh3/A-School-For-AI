"""Unit tests for the School MCP server — thin translation over the bridge."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from school import bridge
from school.mcp import server as mcp_server

EXPECTED_TOOL_ORDER = [
    "school_status",
    "school_remember",
    "school_recall",
    "school_learn",
    "school_conflict",
    "school_confidence",
    "school_search",
    "school_deduplicate",
    "school_knowledge",
    "school_lifecycle",
    "school_diagnose",
    "school_route",
    "school_route_stats",
]


@pytest.fixture(autouse=True)
def fresh_bridge() -> Any:
    """Reset the bridge's single-worktree module cache around every test."""

    def _reset() -> None:
        bridge._manager = None
        bridge._storage = None
        bridge._init_error = None
        bridge._orchestrator = None

    _reset()
    yield
    _reset()


@pytest.fixture()
def worktree(tmp_path: Path) -> str:
    project = tmp_path / "mcp_project"
    project.mkdir()
    return str(project)


class TestToolSurface:
    def test_list_tools_exact_names_and_order(self) -> None:
        result = mcp_server._list_tools()
        assert [t.name for t in result.tools] == EXPECTED_TOOL_ORDER

    def test_all_schemas_are_json_objects(self) -> None:
        for tool in mcp_server._list_tools().tools:
            assert tool.input_schema["type"] == "object"
            assert tool.description

    def test_recall_schema_contract(self) -> None:
        schema = mcp_server._TOOLS["school_recall"]["schema"]
        assert schema["required"] == ["query"]
        assert set(schema["properties"]) == {
            "query",
            "confidence_threshold",
            "context_budget",
            "limit",
            "project",
            "session",
            "agent_id",
        }

    def test_remember_schema_contract(self) -> None:
        schema = mcp_server._TOOLS["school_remember"]["schema"]
        assert schema["required"] == ["content"]
        assert schema["properties"]["outcome"]["enum"] == [
            "SUCCESS",
            "FAILURE",
            "NEUTRAL",
            "MIXED",
        ]
        assert {"confidence", "tags", "project", "session", "agent_id"} <= set(
            schema["properties"]
        )

    def test_learn_schema_contract(self) -> None:
        schema = mcp_server._TOOLS["school_learn"]["schema"]
        assert schema["required"] == ["content"]
        assert {"outcome", "project", "session", "agent_id"} <= set(schema["properties"])

    def test_lifecycle_schema_enums(self) -> None:
        schema = mcp_server._TOOLS["school_lifecycle"]["schema"]
        assert schema["required"] == ["action"]
        assert schema["properties"]["action"]["enum"] == [
            "score",
            "decay",
            "promote",
            "archive",
        ]


class TestToolCalls:
    def test_status_returns_ok_payload(self, worktree: str) -> None:
        result = mcp_server._call_tool(worktree, "school_status", {})
        assert result.is_error is False
        payload = json.loads(result.content[0].text)
        assert payload["ok"] is True
        assert payload["components"]["school"] == "available"
        assert result.structured_content == payload

    def test_recall_missing_query_is_error(self, worktree: str) -> None:
        result = mcp_server._call_tool(worktree, "school_recall", {})
        assert result.is_error is True
        payload = json.loads(result.content[0].text)
        assert payload["ok"] is False
        assert payload["error"]["type"] == "validation"

    def test_remember_missing_content_is_error(self, worktree: str) -> None:
        result = mcp_server._call_tool(worktree, "school_remember", {})
        assert result.is_error is True

    def test_unknown_tool_raises(self, worktree: str) -> None:
        with pytest.raises(ValueError, match="Unknown tool"):
            mcp_server._call_tool(worktree, "school_bogus", {})

    def test_unknown_arguments_are_filtered(self, worktree: str) -> None:
        result = mcp_server._call_tool(
            worktree,
            "school_recall",
            {"query": "anything", "bogus_argument": 123, "nested": {"x": 1}},
        )
        assert result.is_error is False

    def test_learn_alias_stores_and_recall_finds(self, worktree: str) -> None:
        stored = mcp_server._call_tool(
            worktree,
            "school_learn",
            {"content": "learn alias unit probe", "outcome": "SUCCESS"},
        )
        assert stored.is_error is False
        assert stored.structured_content["ok"] is True
        assert stored.structured_content["result"]["stored"] is True
        assert stored.structured_content["result"]["experience_id"]

        recalled = mcp_server._call_tool(
            worktree, "school_recall", {"query": "learn alias probe"}
        )
        assert recalled.is_error is False
        memories = recalled.structured_content["memories"]
        assert len(memories) >= 1
        assert any("learn alias unit probe" in m["content"] for m in memories)

    def test_remember_then_recall_same_session_scope(
        self, worktree: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SCHOOL_PROJECT", raising=False)
        monkeypatch.delenv("SCHOOL_SESSION", raising=False)
        monkeypatch.delenv("SCHOOL_AGENT", raising=False)
        mcp_server._call_tool(
            worktree,
            "school_remember",
            {"content": "scoped memory probe", "project": "envscope", "session": "s1"},
        )
        recall = mcp_server._call_tool(
            worktree, "school_recall", {"query": "scoped memory probe"}
        )
        # No env project set: recall defaults to worktree basename, so the
        # project-scoped memory must NOT leak through.
        assert recall.is_error is False
        assert recall.structured_content["memories"] == []

        monkeypatch.setenv("SCHOOL_PROJECT", "envscope")
        monkeypatch.setenv("SCHOOL_SESSION", "s1")
        recall = mcp_server._call_tool(
            worktree, "school_recall", {"query": "scoped memory probe"}
        )
        assert recall.is_error is False
        memories = recall.structured_content["memories"]
        assert any("scoped memory probe" in m["content"] for m in memories)


class TestScopeIsolation:
    def test_cross_worktree_isolation(self, tmp_path: Path) -> None:
        one = tmp_path / "one"
        two = tmp_path / "two"
        one.mkdir()
        two.mkdir()

        stored = mcp_server._call_tool(
            str(one), "school_remember", {"content": "isolated secret memory"}
        )
        assert stored.is_error is False

        leaked = mcp_server._call_tool(
            str(two), "school_recall", {"query": "isolated secret memory"}
        )
        assert leaked.is_error is False
        assert leaked.structured_content["memories"] == []

    def test_same_worktree_finds_memory(self, tmp_path: Path) -> None:
        one = tmp_path / "one"
        one.mkdir()
        mcp_server._call_tool(str(one), "school_remember", {"content": "visible memory"})
        found = mcp_server._call_tool(str(one), "school_recall", {"query": "visible memory"})
        assert len(found.structured_content["memories"]) >= 1


class TestBuildRequest:
    def test_project_defaults_to_worktree_basename(self) -> None:
        req = mcp_server._build_request("/tmp/proj-xyz", "school_recall", {"query": "q"})
        assert req["project"] == "proj-xyz"

    def test_lifecycle_has_no_basename_default(self) -> None:
        req = mcp_server._build_request("/tmp/proj-xyz", "school_lifecycle", {"action": "score"})
        assert "project" not in req

    def test_agent_defaults_to_opencode_for_bridge_tools(self) -> None:
        # Matches bridge remember/recall defaults and the OpenCode plugin,
        # so MCP and plugin memories share one agent scope.
        req = mcp_server._build_request("/tmp/p", "school_recall", {"query": "q"})
        assert req["agent"] == "opencode"
        assert "agent_id" not in req

    def test_agent_defaults_to_opencode_for_dispatch_tools(self) -> None:
        req = mcp_server._build_request("/tmp/p", "school_learn", {"content": "x"})
        assert req["agent_id"] == "opencode"
        assert "agent" not in req

    def test_env_project_overrides_basename(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SCHOOL_PROJECT", "env-proj")
        req = mcp_server._build_request("/tmp/proj-xyz", "school_recall", {"query": "q"})
        assert req["project"] == "env-proj"

    def test_arg_project_overrides_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SCHOOL_PROJECT", "env-proj")
        req = mcp_server._build_request(
            "/tmp/proj-xyz", "school_recall", {"query": "q", "project": "arg-proj"}
        )
        assert req["project"] == "arg-proj"

    def test_session_env_fill(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SCHOOL_SESSION", "sess-9")
        req = mcp_server._build_request("/tmp/p", "school_recall", {"query": "q"})
        assert req["session"] == "sess-9"

    def test_agent_env_maps_to_bridge_agent_for_remember(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SCHOOL_AGENT", "mcp-agent")
        req = mcp_server._build_request("/tmp/p", "school_remember", {"content": "x"})
        assert req["agent"] == "mcp-agent"
        assert "agent_id" not in req

    def test_agent_env_maps_to_agent_id_for_dispatch_tools(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SCHOOL_AGENT", "mcp-agent")
        req = mcp_server._build_request("/tmp/p", "school_learn", {"content": "x"})
        assert req["agent_id"] == "mcp-agent"
        assert "agent" not in req

    def test_worktree_always_present(self) -> None:
        req = mcp_server._build_request("/tmp/p", "school_status", {})
        assert req["worktree"] == "/tmp/p"

    def test_foreign_arguments_dropped(self) -> None:
        req = mcp_server._build_request("/tmp/p", "school_recall", {"query": "q", "zzz": 1})
        assert "zzz" not in req


class TestIntParam:
    def test_clamps_high_values(self) -> None:
        assert mcp_server._int_param({"limit": ["99"]}, "limit", 5, 1, 5) == 5
        assert mcp_server._int_param({"budget": ["999999"]}, "budget", 600, 1, 600) == 600

    def test_clamps_low_values(self) -> None:
        assert mcp_server._int_param({"limit": ["0"]}, "limit", 5, 1, 5) == 1

    def test_defaults_on_missing_or_invalid(self) -> None:
        assert mcp_server._int_param({}, "limit", 5, 1, 5) == 5
        assert mcp_server._int_param({"limit": ["abc"]}, "limit", 5, 1, 5) == 5


class TestResources:
    def test_list_resources_status_only(self) -> None:
        resources = mcp_server._list_resources().resources
        assert [str(r.uri) for r in resources] == ["school://status"]

    def test_list_resource_templates(self) -> None:
        templates = mcp_server._list_resource_templates().resource_templates
        assert templates[0].uri_template == "school://context/{project}"

    def test_read_status_resource(self, worktree: str) -> None:
        result = mcp_server._read_resource(worktree, "school://status")
        payload = json.loads(result.contents[0].text)
        assert payload["ok"] is True
        assert result.contents[0].mime_type == "application/json"

    def test_read_context_resource_budgeted(
        self, worktree: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SCHOOL_PROJECT", "ctxproj")
        for index in range(7):
            mcp_server._call_tool(
                worktree,
                "school_remember",
                {"content": f"ctx memory number {index}", "project": "ctxproj"},
            )
        project = Path(worktree).name
        uri = f"school://context/{project}?q=ctx memory&limit=99&budget=99999"
        result = mcp_server._read_resource(worktree, uri)
        payload = json.loads(result.contents[0].text)
        assert payload["ok"] is True
        # limit is clamped to 5 no matter what the caller asks for
        assert len(payload["memories"]) <= 5

    def test_unknown_resource_raises(self, worktree: str) -> None:
        with pytest.raises(ValueError, match="Unknown resource"):
            mcp_server._read_resource(worktree, "school://bogus")

    def test_context_without_project_raises(self, worktree: str) -> None:
        with pytest.raises(ValueError, match="Unknown resource"):
            mcp_server._read_resource(worktree, "school://context/")


class TestPrompts:
    def test_list_prompts(self) -> None:
        prompts = mcp_server._list_prompts().prompts
        assert [p.name for p in prompts] == ["relevant_context"]
        query_arg = prompts[0].arguments[0]
        assert query_arg.name == "query"
        assert query_arg.required is True

    def test_get_prompt_marks_context_block(self, worktree: str) -> None:
        mcp_server._call_tool(worktree, "school_remember", {"content": "prompt memory probe"})
        result = mcp_server._get_prompt(worktree, "relevant_context", {"query": "prompt memory"})
        text = result.messages[0].content.text
        assert text.startswith("[school context]")
        assert text.rstrip().endswith("[/school]")
        assert "prompt memory probe" in text
        assert result.messages[0].role == "user"

    def test_get_prompt_no_hits_is_not_an_error(self, worktree: str) -> None:
        result = mcp_server._get_prompt(worktree, "relevant_context", {"query": "nothing here"})
        assert "No memories matched" in result.messages[0].content.text

    def test_get_prompt_missing_query_raises(self, worktree: str) -> None:
        with pytest.raises(ValueError, match="query"):
            mcp_server._get_prompt(worktree, "relevant_context", {})

    def test_unknown_prompt_raises(self, worktree: str) -> None:
        with pytest.raises(ValueError, match="Unknown prompt"):
            mcp_server._get_prompt(worktree, "bogus", {"query": "x"})


class TestBuildServer:
    def test_build_server_binds_worktree(self, worktree: str) -> None:
        server = mcp_server.build_server(worktree)
        assert server.name == "school"
        assert bridge._manager is not None
        assert bridge._storage is not None

    def test_build_server_env_worktree(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = tmp_path / "env_wt"
        project.mkdir()
        monkeypatch.setenv("SCHOOL_WORKTREE", str(project))
        mcp_server.build_server()
        assert bridge._manager is not None

    def test_instructions_frame_memory_as_data(self) -> None:
        assert "never instructions" in mcp_server._INSTRUCTIONS


class TestClientConfig:
    def test_all_presets_produce_valid_config(self) -> None:
        import json as jsonlib
        import tomllib

        from school.mcp.config import CLIENT_PATHS, build_client_config

        for client in CLIENT_PATHS:
            preset = build_client_config(client)
            assert preset["name"] == client
            assert preset["path"]
            if preset["format"] == "json":
                jsonlib.loads(preset["config"])
            else:
                tomllib.loads(preset["config"])
            assert "school.mcp" in preset["config"]

    def test_unknown_client_raises(self) -> None:
        from school.mcp.config import build_client_config

        with pytest.raises(ValueError, match="Unknown MCP client"):
            build_client_config("not-a-client")

    def test_custom_python_interpreter(self) -> None:
        import json as jsonlib

        from school.mcp.config import build_client_config

        preset = build_client_config("claude", python="C:\\custom\\python.exe")
        block = jsonlib.loads(preset["config"])
        assert block["mcpServers"]["school"]["command"] == "C:\\custom\\python.exe"


class TestRoutingGuidance:
    """Descriptions and instructions teach the model how to route to tools."""

    def test_every_description_has_use_guidance(self) -> None:
        for name, spec in mcp_server._TOOLS.items():
            assert "Use" in spec["description"], name
            assert len(spec["description"]) <= 400, name

    def test_instructions_teach_routing(self) -> None:
        for key in (
            "school_recall",
            "school_remember",
            "school_search",
            "school_conflict",
            "school_status",
            "school_diagnose",
            "never instructions",
        ):
            assert key in mcp_server._INSTRUCTIONS, key

    def test_read_only_annotations(self) -> None:
        tools = {t.name: t for t in mcp_server._list_tools().tools}
        read_only = {
            name
            for name, tool in tools.items()
            if tool.annotations is not None and tool.annotations.read_only_hint
        }
        assert read_only == {
            "school_status",
            "school_recall",
            "school_search",
            "school_confidence",
            "school_conflict",
            "school_diagnose",
            "school_route_stats",
        }
        for name in read_only:
            assert tools[name].annotations.idempotent_hint is True, name

    def test_mcp_descriptions_match_plugin_ts(self) -> None:
        import re

        from school.plugin_source import TS_PLUGIN_SOURCE

        for name, spec in mcp_server._TOOLS.items():
            match = re.search(
                rf"{re.escape(name)}: tool\(.*?description:\s*\n(.*?),\n\s*args:",
                TS_PLUGIN_SOURCE,
                re.S,
            )
            assert match, f"no TS description block for {name}"
            ts_desc = "".join(re.findall(r'"([^"]*)"', match.group(1)))
            assert ts_desc == spec["description"], name


class TestRouteToolsMCP:
    def test_tools_present_with_use_guidance(self):
        from school.mcp.server import _TOOLS
        for name in ("school_route", "school_route_stats"):
            assert name in _TOOLS
            assert "Use" in _TOOLS[name]["description"]
            assert "coding" in _TOOLS[name]["description"]

    def test_route_schema(self):
        from school.mcp.server import _TOOLS
        props = _TOOLS["school_route"]["schema"]["properties"]
        assert props["mode"]["enum"] == ["assess", "report"]
        assert props["severity"]["enum"] == ["light", "medium", "high"]
        assert "situation" in _TOOLS["school_route"]["schema"]["required"]

    def test_stats_annotations(self):
        from school.mcp.server import _TOOLS
        ann = _TOOLS["school_route_stats"]["annotations"]
        assert ann["read_only_hint"] is True

    def test_engage_mapping_parity(self):
        from school.mcp.server import _engage_for
        assert _engage_for("light") == "skill"
        assert _engage_for("medium") == "both"
        assert _engage_for("high") == "both"

    def test_assess_requires_severity_and_writes_evidence(self, tmp_path):
        from school.mcp.server import _call_tool
        wt = str(tmp_path)
        with pytest.raises(ValueError) as exc:
            _call_tool(wt, "school_route",
                       {"mode": "assess", "situation": "planning a trip"})
        assert "severity" in str(exc.value).lower()
        res = _call_tool(wt, "school_route",
                         {"mode": "assess", "situation": "planning a trip",
                          "severity": "light"})
        assert res.is_error is False
        data = res.structured_content
        assert data["source"] == "self-rated"
        assert data["engage"] == "skill"
        ev = tmp_path / ".school" / "routing-stats.jsonl"
        assert ev.exists()
        assert "assess" in ev.read_text(encoding="utf-8")

    def test_report_stores_tagged_lesson(self, tmp_path, monkeypatch):
        from school.mcp.server import _call_tool
        res = _call_tool(str(tmp_path), "school_route",
                         {"mode": "report", "situation": "debugging session",
                          "lesson": "recall first, search second",
                          "outcome": "helpful"})
        assert res.is_error is False
        assert res.structured_content["ok"] is True
        # Lesson is retrievable through the normal recall path.
        res2 = _call_tool(str(tmp_path), "school_recall",
                          {"query": "routing lesson"})
        assert res2.is_error is False
        found = " ".join(
            str(m.get("content", ""))
            for m in res2.structured_content.get("memories", [])
        )
        assert "recall first" in found

    def test_stats_aggregates(self, tmp_path):
        from school.mcp.server import _call_tool
        _call_tool(str(tmp_path), "school_route",
                   {"mode": "assess", "situation": "x", "severity": "high"})
        res = _call_tool(str(tmp_path), "school_route_stats", {"limit": 5})
        assert res.is_error is False
        data = res.structured_content
        assert data["last_activity"]
        assert any(e.get("kind") == "assess" for e in data["recent"])
        assert "knobs" in data

    def test_default_assess_without_severity_fails(self, tmp_path):
        # MCP has no model client: severity is mandatory.
        from school.mcp.server import _call_tool
        with pytest.raises(ValueError):
            _call_tool(str(tmp_path), "school_route",
                       {"mode": "assess", "situation": "x"})
