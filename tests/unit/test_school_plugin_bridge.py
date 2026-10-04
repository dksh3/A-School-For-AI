"""Tests for School plugin source and bridge protocol."""

from __future__ import annotations

import json
import re
from io import StringIO
from unittest.mock import patch

from school.plugin_source import TS_PLUGIN_SOURCE

#: The approved agent-facing OpenCode tool surface (order matters).
EXPECTED_OPENCODE_TOOLS = [
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


def _tool_names() -> list[str]:
    """Return the tool names registered by the TypeScript plugin, in order."""
    return re.findall(r"^\s+(school_\w+): tool\(", TS_PLUGIN_SOURCE, re.MULTILINE)


def _tool_block(name: str) -> str:
    """Return the full source block of a single plugin tool."""
    pattern = rf"^\s+{name}: tool\(\{{[\s\S]*?^[ ]{{6}}\}}\),"
    match = re.search(pattern, TS_PLUGIN_SOURCE, re.MULTILINE)
    assert match is not None, f"tool block not found: {name}"
    return match.group(0)


class TestPluginSource:
    """Test the bundled TypeScript plugin source."""

    def test_contains_school_plugin(self) -> None:
        """Plugin source defines School plugin."""
        assert "const School: Plugin" in TS_PLUGIN_SOURCE

    def test_contains_discover_bridge(self) -> None:
        """Plugin source has bridge discovery."""
        assert "discoverBridge" in TS_PLUGIN_SOURCE

    def test_contains_tools(self) -> None:
        """Plugin source defines all 10 tools."""
        assert "school_status" in TS_PLUGIN_SOURCE
        assert "school_remember" in TS_PLUGIN_SOURCE
        assert "school_recall" in TS_PLUGIN_SOURCE
        assert "school_conflict" in TS_PLUGIN_SOURCE
        assert "school_confidence" in TS_PLUGIN_SOURCE
        assert "school_search" in TS_PLUGIN_SOURCE
        assert "school_deduplicate" in TS_PLUGIN_SOURCE
        assert "school_knowledge" in TS_PLUGIN_SOURCE
        assert "school_lifecycle" in TS_PLUGIN_SOURCE
        assert "school_diagnose" in TS_PLUGIN_SOURCE

    def test_cross_platform_bridge_discovery(self) -> None:
        """Plugin uses cross-platform PATH detection."""
        assert 'process.platform === "win32"' in TS_PLUGIN_SOURCE
        assert "where ${command}" in TS_PLUGIN_SOURCE
        assert "which ${command}" in TS_PLUGIN_SOURCE
        assert "school-bridge" in TS_PLUGIN_SOURCE
        assert "lerev-bridge" not in TS_PLUGIN_SOURCE

    def test_exports_default(self) -> None:
        """Plugin exports default."""
        assert "export default School" in TS_PLUGIN_SOURCE

    def test_no_evo_references(self) -> None:
        """No stale EVO references in user-facing output."""
        assert "evo_status" not in TS_PLUGIN_SOURCE
        assert "evo_remember" not in TS_PLUGIN_SOURCE
        assert "evo_recall" not in TS_PLUGIN_SOURCE

    def test_json_protocol(self) -> None:
        """Plugin uses JSON stdin/stdout protocol."""
        assert "JSON.stringify" in TS_PLUGIN_SOURCE
        assert "JSON.parse" in TS_PLUGIN_SOURCE

    def test_error_handling(self) -> None:
        """Plugin handles errors gracefully."""
        assert "catch" in TS_PLUGIN_SOURCE
        assert "bridge_error" in TS_PLUGIN_SOURCE


class TestBridgeProtocol:
    """Test the bridge JSON protocol."""

    def test_bridge_module_importable(self) -> None:
        """school.bridge module is importable."""
        from school.bridge import _COMMANDS

        assert "status" in _COMMANDS
        assert "remember" in _COMMANDS
        assert "recall" in _COMMANDS
        assert "conflict" in _COMMANDS
        assert "confidence" in _COMMANDS
        assert "search" in _COMMANDS
        assert "deduplicate" in _COMMANDS
        assert "knowledge" in _COMMANDS
        assert "lifecycle" in _COMMANDS
        assert "diagnose" in _COMMANDS

    def test_bridge_handles_malformed_json(self) -> None:
        """Bridge handles malformed JSON input."""
        from school.bridge import main

        stdin = StringIO("not valid json {{{")
        stdout = StringIO()
        with (
            patch("sys.stdin", stdin),
            patch("sys.stdout", stdout),
        ):
            main()

        output = json.loads(stdout.getvalue())
        assert output["ok"] is False
        assert output["error"]["type"] == "protocol"

    def test_bridge_handles_unknown_command(self) -> None:
        """Bridge handles unknown commands."""
        from school.bridge import main

        stdin = StringIO(json.dumps({"command": "nonexistent"}))
        stdout = StringIO()
        with (
            patch("sys.stdin", stdin),
            patch("sys.stdout", stdout),
        ):
            main()

        output = json.loads(stdout.getvalue())
        assert output["ok"] is False
        assert output["error"]["type"] == "protocol"

    def test_bridge_status_command(self) -> None:
        """Bridge status command returns component info."""
        from school.bridge import _handle_status

        result = _handle_status({"worktree": "."})
        assert result["ok"] is True
        assert "components" in result
        assert "school" in result["components"]

    def test_bridge_remember_requires_content(self) -> None:
        """Bridge remember command requires content."""
        from school.bridge import _handle_remember

        result = _handle_remember({"worktree": ".", "content": "", "observation": ""})
        assert result["ok"] is False
        assert result["error"]["type"] == "validation"

    def test_bridge_recall_requires_query(self) -> None:
        """Bridge recall command requires query."""
        from school.bridge import _handle_recall

        result = _handle_recall({"worktree": ".", "query": ""})
        assert result["ok"] is False
        assert result["error"]["type"] == "validation"


class TestPluginToolSurface:
    """The plugin must expose exactly the approved 13-tool surface."""

    def test_exposes_exactly_13_tools(self) -> None:
        names = _tool_names()
        assert len(names) == 13, f"expected 13 tools, got {len(names)}: {names}"
        assert set(names) == set(EXPECTED_OPENCODE_TOOLS)

    def test_tool_order_matches_approved_surface(self) -> None:
        assert _tool_names() == EXPECTED_OPENCODE_TOOLS

    def test_learn_registered_after_recall(self) -> None:
        names = _tool_names()
        assert "school_learn" in names
        assert names.index("school_learn") == names.index("school_recall") + 1

    def test_existing_ten_tools_preserved(self) -> None:
        names = set(_tool_names())
        for tool_name in EXPECTED_OPENCODE_TOOLS:
            if tool_name != "school_learn":
                assert tool_name in names

    def test_no_internal_orchestrator_tools_exposed(self) -> None:
        """Internal Orchestrator primitives stay internal (no second routing surface)."""
        for forbidden in (
            "pipeline(",
            "parallel(",
            "remember_with_learning",
            "trigger_background",
            "process_background",
            "school_pipeline",
            "school_parallel",
            "school_background",
        ):
            assert forbidden not in TS_PLUGIN_SOURCE, f"internal API exposed: {forbidden}"


class TestLearnTool:
    """school_learn must be a thin passthrough to the existing bridge `learn` command."""

    def test_learn_sends_learn_command(self) -> None:
        block = _tool_block("school_learn")
        assert 'command: "learn"' in block
        assert 'command: "remember"' not in block

    def test_learn_content_is_required(self) -> None:
        block = _tool_block("school_learn")
        args_section = block.split("async execute")[0]
        content_decl = re.search(r"content: (tool\.schema[\s\S]*?)\n\s+\w+:", args_section)
        assert content_decl is not None, "content argument not declared"
        assert ".optional()" not in content_decl.group(1)

    def test_learn_supports_all_approved_arguments(self) -> None:
        args_section = _tool_block("school_learn").split("async execute")[0]
        for arg in (
            "content",
            "outcome",
            "project",
            "session",
            "observation",
            "action",
            "tags",
            "confidence",
        ):
            assert re.search(rf"\b{arg}:", args_section), f"missing learn argument: {arg}"

    def test_learn_surfaces_bridge_errors(self) -> None:
        """Orchestrator failures arrive as `errors: [...]`, not `error: {...}`."""
        block = _tool_block("school_learn")
        assert "errors" in block

    def test_learn_contains_no_learning_logic(self) -> None:
        """No second learning engine in TypeScript: no orchestrator/storage calls."""
        block = _tool_block("school_learn")
        for forbidden in ("create_orchestrator", "dispatch(", "store(", "MemoryManager"):
            assert forbidden not in block, f"TS learning logic found: {forbidden}"


class TestPluginVersionMetadata:
    """The installed plugin reports the canonical School version."""

    def test_version_matches_python_package_version(self) -> None:
        from school import __version__

        assert f'const SCHOOL_VERSION = "{__version__}"' in TS_PLUGIN_SOURCE

    def test_no_unresolved_version_placeholder(self) -> None:
        assert "__SCHOOL_VERSION__" not in TS_PLUGIN_SOURCE

    def test_status_reports_plugin_and_bridge_versions(self) -> None:
        block = _tool_block("school_status")
        assert "SCHOOL_VERSION" in block
        assert "bridgeVersion" in block
        assert "Version match" in block

    def test_status_mismatch_is_non_fatal(self) -> None:
        """A version mismatch must never block the status call."""
        block = _tool_block("school_status")
        assert "throw" not in block
        assert "MISMATCH" in block
        # mismatch is only ever surfaced in reporting, via metadata
        assert "compat" in block


class TestBridgeLearnCommand:
    """Bridge `learn` command → Orchestrator.dispatch("school_remember")."""

    def test_learn_command_registered(self) -> None:
        from school.bridge import _COMMANDS

        assert "learn" in _COMMANDS

    def test_learn_dispatches_to_orchestrator(self) -> None:
        from core.routing.v26.tools.base import ToolResult
        from school import bridge as bridge_module

        calls: dict[str, object] = {}

        class StubOrchestrator:
            def dispatch(self, command: str, **params: object) -> ToolResult:
                calls["command"] = command
                calls["params"] = params
                return ToolResult(success=True, data={"stored": True}, errors=[], metadata={})

        request = {"command": "learn", "content": "learned something", "worktree": "."}
        with patch.object(bridge_module, "_get_orchestrator", return_value=StubOrchestrator()):
            resp = bridge_module._handle_learn(request)

        assert calls["command"] == "school_remember"
        assert calls["params"]["content"] == "learned something"
        assert "command" not in calls["params"]
        assert resp["ok"] is True
        assert resp["result"] == {"stored": True}

    def test_successful_learn_call_through_real_orchestrator(self) -> None:
        from school.bridge import _handle_learn

        resp = _handle_learn(
            {
                "command": "learn",
                "content": "pytest suites must stay green before committing",
                "outcome": "SUCCESS",
            }
        )
        assert resp["ok"] is True, resp
        assert resp["result"]["stored"] is True

    def test_malformed_learn_input_reports_errors(self) -> None:
        from school.bridge import _handle_learn

        resp = _handle_learn({"command": "learn"})
        assert resp["ok"] is False
        assert resp["errors"], "expected validation errors for missing content"

    def test_learn_orchestrator_failure_propagates(self) -> None:
        from core.routing.v26.tools.base import ToolResult
        from school import bridge as bridge_module

        class FailingOrchestrator:
            def dispatch(self, command: str, **params: object) -> ToolResult:
                return ToolResult(
                    success=False, data={}, errors=["storage rejected"], metadata={}
                )

        with patch.object(bridge_module, "_get_orchestrator", return_value=FailingOrchestrator()):
            resp = bridge_module._handle_learn({"command": "learn", "content": "x"})

        assert resp["ok"] is False
        assert resp["errors"] == ["storage rejected"]

    def test_bridge_exception_returns_runtime_error(self) -> None:
        from school.bridge import main

        stdin = StringIO(json.dumps({"command": "learn", "content": "x"}))
        stdout = StringIO()
        with (
            patch("sys.stdin", stdin),
            patch("sys.stdout", stdout),
            patch("school.bridge._get_orchestrator", side_effect=RuntimeError("orch down")),
        ):
            main()

        output = json.loads(stdout.getvalue())
        assert output["ok"] is False
        assert output["error"]["type"] == "runtime"
        assert "orch down" in output["error"]["message"]


class TestBridgeVersionCompatibility:
    """Offline plugin/bridge compatibility reporting."""

    def test_status_includes_version(self) -> None:
        from school import __version__
        from school.bridge import _handle_status

        result = _handle_status({"worktree": "."})
        assert result["version"] == __version__

    def test_status_version_matches_plugin_version(self) -> None:
        from school import __version__

        assert f'const SCHOOL_VERSION = "{__version__}"' in TS_PLUGIN_SOURCE


class TestSkeletonCommand:
    def test_registered_in_commands(self):
        import school.bridge as bridge_mod

        assert "skeleton" in bridge_mod._COMMANDS
        assert bridge_mod._COMMANDS["skeleton"] is bridge_mod._handle_skeleton

    def test_payload_compressed_with_footer(self):
        import school.bridge as bridge_mod

        text = "\n".join(f'{{"k": "some value {i}}}' for i in range(400))
        out = bridge_mod._handle_skeleton(
            {"text": text, "filename": "data.json"}
        )
        assert out["ok"] is True
        assert out["compressed"] is True
        assert out["tokens_in"] >= 1000
        assert out["tokens_out"] < out["tokens_in"]
        assert "[school ctx:" in out["content"]
        assert out["parser"] == "payload"

    def test_small_text_passthrough(self):
        import school.bridge as bridge_mod

        out = bridge_mod._handle_skeleton({"text": "tiny", "filename": "a.txt"})
        assert out["ok"] is True
        assert out["compressed"] is False
        assert out["content"] == "tiny"
        assert "school ctx" not in out["content"]

    def test_missing_text_validation(self):
        import school.bridge as bridge_mod

        out = bridge_mod._handle_skeleton({})
        assert out["ok"] is False
        assert out["error"]["type"] == "validation"

    def test_invalid_strategy_validation(self):
        import school.bridge as bridge_mod

        out = bridge_mod._handle_skeleton(
            {"text": "x" * 4000, "strategy": "nope"}
        )
        assert out["ok"] is False
        assert out["error"]["type"] == "validation"

    def test_kill_switch(self, monkeypatch):
        import school.bridge as bridge_mod

        monkeypatch.setenv("SCHOOL_CTX", "0")
        text = "\n".join(f'{{"k": "some value {i}}}' for i in range(400))
        out = bridge_mod._handle_skeleton({"text": text, "filename": "d.json"})
        assert out["ok"] is True
        assert out["compressed"] is False
        assert out["content"] == text

    def test_stdio_roundtrip(self):
        import json as json_mod
        from io import StringIO
        from unittest.mock import patch

        import school.bridge as bridge_mod

        text = "\n".join(f'{{"k": "some value {i}}}' for i in range(400))
        payload = json_mod.dumps(
            {"command": "skeleton", "text": text, "filename": "d.json"}
        )
        stdin = StringIO(payload)
        stdout = StringIO()
        with (
            patch("sys.stdin", stdin),
            patch("sys.stdout", stdout),
        ):
            bridge_mod.main()
        output = json_mod.loads(stdout.getvalue())
        assert output["ok"] is True
        assert output["compressed"] is True
        assert "[school ctx:" in output["content"]
