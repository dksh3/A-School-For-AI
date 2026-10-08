"""Integration tests for the School MCP server over a real stdio connection.

Each test spawns `python -m school.mcp` as a genuine subprocess and talks
to it through the official MCP client — covering startup, discovery, real
tool calls, malformed input, cross-process persistence, and worktree
isolation.
"""

from __future__ import annotations

import json
import sys
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.exceptions import MCPError

REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)

EXPECTED_TOOLS = [
    "school_status",
    "school_dashboard",
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
    "school_read",
    "school_grep",
    "school_skill_list",
    "school_skill_search",
    "school_skill_create",
    "school_skill_use",
    "school_skill_feedback",
    "school_skill_status",
    "school_skill_evolve",
    "school_skill_search_github",
    "school_skill_discover",
    "school_skill_analyze_external",
    "school_skill_compare",
    "school_skill_import",
    "school_context_status",
    "school_context_compress",
    "school_context_restore",
]


def _params(cwd: Path | str, **env: str) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "school.mcp"],
        cwd=str(cwd),
        env={"PYTHONPATH": REPO_ROOT, **env},
    )


@asynccontextmanager
async def _server(
    cwd: Path | str, **env: str
) -> AsyncIterator[tuple[ClientSession, Any]]:
    """Spawn a school.mcp subprocess, initialize, and yield the session."""
    async with (
        stdio_client(_params(cwd, **env)) as (read, write),
        ClientSession(read, write) as session,
    ):
        init = await session.initialize()
        yield session, init


class TestStartupAndDiscovery:
    async def test_initialize_reports_school(self, tmp_path: Path) -> None:
        async with _server(tmp_path) as (_, init):
            assert init.server_info.name == "school"
            assert init.server_info.version

    async def test_lists_exact_tool_surface(self, tmp_path: Path) -> None:
        async with _server(tmp_path) as (session, _):
            tools = await session.list_tools()
            assert [t.name for t in tools.tools] == EXPECTED_TOOLS
            for tool in tools.tools:
                assert tool.input_schema["type"] == "object"

    async def test_lists_resources_and_prompts(self, tmp_path: Path) -> None:
        async with _server(tmp_path) as (session, _):
            resources = await session.list_resources()
            assert [str(r.uri) for r in resources.resources] == ["school://status"]

            templates = await session.list_resource_templates()
            assert templates.resource_templates[0].uri_template == (
                "school://context/{project}"
            )

            prompts = await session.list_prompts()
            assert [p.name for p in prompts.prompts] == ["relevant_context"]
            query_arg = prompts.prompts[0].arguments[0]
            assert query_arg.name == "query"
            assert query_arg.required is True


class TestRealToolCalls:
    async def test_status_call(self, tmp_path: Path) -> None:
        async with _server(tmp_path) as (session, _):
            result = await session.call_tool("school_status", {})
            assert result.is_error is False
            payload = json.loads(result.content[0].text)
            assert payload["ok"] is True
            assert payload["components"]["school"] == "available"

    async def test_unknown_tool_is_protocol_error(self, tmp_path: Path) -> None:
        async with _server(tmp_path) as (session, _):
            with pytest.raises(MCPError):
                await session.call_tool("school_bogus", {})

    async def test_dashboard_call(self, tmp_path: Path) -> None:
        async with _server(tmp_path) as (session, _):
            result = await session.call_tool("school_dashboard", {})
            assert result.is_error is False
            payload = json.loads(result.content[0].text)
            assert payload["ok"] is True
            assert "route:" in payload["text"]
            assert "diag:" in payload["text"]

    async def test_missing_required_argument_is_error_result(
        self, tmp_path: Path
    ) -> None:
        async with _server(tmp_path) as (session, _):
            result = await session.call_tool("school_recall", {})
            assert result.is_error is True
            payload = json.loads(result.content[0].text)
            assert payload["error"]["type"] == "validation"

    async def test_status_resource_read(self, tmp_path: Path) -> None:
        async with _server(tmp_path) as (session, _):
            result = await session.read_resource("school://status")
            payload = json.loads(result.contents[0].text)
            assert payload["ok"] is True

    async def test_context_resource_read(self, tmp_path: Path) -> None:
        async with _server(tmp_path) as (session, _):
            await session.call_tool(
                "school_remember", {"content": "wire context probe"}
            )
            project = tmp_path.name
            result = await session.read_resource(
                f"school://context/{project}?q=context probe&limit=99"
            )
            payload = json.loads(result.contents[0].text)
            assert payload["ok"] is True
            assert len(payload["memories"]) <= 5

    async def test_get_prompt_over_wire(self, tmp_path: Path) -> None:
        async with _server(tmp_path) as (session, _):
            await session.call_tool(
                "school_remember", {"content": "prompt wire probe"}
            )
            prompt = await session.get_prompt(
                "relevant_context", {"query": "prompt wire"}
            )
            text = prompt.messages[0].content.text
            assert "[school context]" in text
            assert "prompt wire probe" in text


class TestPersistenceAcrossProcesses:
    async def test_remember_survives_fresh_server(self, tmp_path: Path) -> None:
        token = uuid.uuid4().hex[:12]
        content = f"unique persistence probe {token}"

        async with _server(tmp_path) as (session, _):
            result = await session.call_tool("school_remember", {"content": content})
            assert result.is_error is False
            assert json.loads(result.content[0].text)["ok"] is True

        # Brand-new subprocess must see the memory written by the first one.
        async with _server(tmp_path) as (session, _):
            result = await session.call_tool(
                "school_recall", {"query": "persistence probe"}
            )
            payload = json.loads(result.content[0].text)
            assert payload["ok"] is True
            assert any(token in m["content"] for m in payload["memories"])

    async def test_learn_survives_fresh_server(self, tmp_path: Path) -> None:
        token = uuid.uuid4().hex[:12]

        async with _server(tmp_path) as (session, _):
            result = await session.call_tool(
                "school_learn", {"content": f"learn persistence probe {token}"}
            )
            assert result.is_error is False

        async with _server(tmp_path) as (session, _):
            result = await session.call_tool(
                "school_recall", {"query": "learn persistence probe"}
            )
            payload = json.loads(result.content[0].text)
            assert payload["ok"] is True
            assert any(token in m["content"] for m in payload["memories"])


class TestIsolation:
    async def test_separate_worktrees_do_not_leak(self, tmp_path: Path) -> None:
        dir_a = tmp_path / "alpha"
        dir_b = tmp_path / "beta"
        dir_a.mkdir()
        dir_b.mkdir()
        token = uuid.uuid4().hex[:12]

        async with _server(dir_a) as (session, _):
            result = await session.call_tool(
                "school_remember", {"content": f"isolation probe {token}"}
            )
            assert result.is_error is False

        async with _server(dir_b) as (session, _):
            result = await session.call_tool(
                "school_recall", {"query": "isolation probe"}
            )
            payload = json.loads(result.content[0].text)
            assert payload["ok"] is True
            assert payload["memories"] == []

        # Same worktree sees it again (fresh process, same storage).
        async with _server(dir_a) as (session, _):
            result = await session.call_tool(
                "school_recall", {"query": "isolation probe"}
            )
            payload = json.loads(result.content[0].text)
            assert any(token in m["content"] for m in payload["memories"])


class TestContextOptimizerTools:
    async def test_small_read_raw(self, tmp_path: Path) -> None:
        (tmp_path / "small.txt").write_text("hello world\n", encoding="utf-8")
        async with _server(tmp_path) as (session, _):
            result = await session.call_tool("school_read", {"path": "small.txt"})
            assert not result.is_error
            data = json.loads(result.content[0].text)
            assert data["ok"] is True
            assert data["skeletonized"] is False
            assert data["content"] == "hello world"

    async def test_oversized_read_skeletonized(self, tmp_path: Path) -> None:
        lines = ["def compute(a: int) -> int:"]
        for i in range(600):
            lines.append(f"    x = x + {i}")
        (tmp_path / "big.py").write_text("\n".join(lines), encoding="utf-8")
        async with _server(tmp_path) as (session, _):
            result = await session.call_tool("school_read", {"path": "big.py"})
            assert not result.is_error
            data = json.loads(result.content[0].text)
            assert data["skeletonized"] is True
            assert "[school ctx:" in data["content"]

    async def test_unknown_path_is_error(self, tmp_path: Path) -> None:
        async with _server(tmp_path) as (session, _):
            result = await session.call_tool("school_read", {"path": "missing.txt"})
            assert result.is_error
            data = json.loads(result.content[0].text)
            assert data["error"]["type"] == "not_found"

    async def test_grep_finds_def(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text(
            "def alpha():\n    pass\n", encoding="utf-8"
        )
        async with _server(tmp_path) as (session, _):
            result = await session.call_tool("school_grep", {"pattern": "^def "})
            assert not result.is_error
            data = json.loads(result.content[0].text)
            assert data["matches"] == 1
            assert "a.py:1:def alpha():" in data["content"]


class TestRouteStdio:
    async def test_route_assess_self_rated(self, tmp_path: Path) -> None:
        async with _server(tmp_path) as (session, _):
            with pytest.raises(MCPError):
                await session.call_tool(
                    "school_route",
                    {"mode": "assess", "situation": "starting a migration"},
                )
            res = await session.call_tool(
                "school_route",
                {
                    "mode": "assess",
                    "situation": "starting a migration",
                    "severity": "medium",
                },
            )
            assert res.is_error is False
            data = json.loads(res.content[0].text)
            assert data["source"] == "self-rated"
            assert data["engage"] == "both"

    async def test_route_report_then_stats(self, tmp_path: Path) -> None:
        async with _server(tmp_path) as (session, _):
            res = await session.call_tool(
                "school_route",
                {
                    "mode": "report",
                    "situation": "refactor planning",
                    "lesson": "assess before choosing tools",
                    "outcome": "helpful",
                },
            )
            assert res.is_error is False
            stats = await session.call_tool("school_route_stats", {"limit": 5})
            assert stats.is_error is False
            recent = json.loads(stats.content[0].text)["recent"]
            assert any(e.get("kind") == "report" for e in recent)
