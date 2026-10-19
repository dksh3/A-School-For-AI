"""Per-CLI plugin adapters — emit the School plugin for any agent CLI.

FAIL-OPEN: every emitter returns a string/dict, never raises. The canonical
OpenCode plugin source is pulled from ``school.plugin_source`` when available
and falls back to a minimal fail-open stub otherwise.
"""

from __future__ import annotations

from typing import Any

_MINIMAL_TS = (
    "// School plugin (minimal fail-open stub)\n"
    "export default function schoolPlugin() {\n"
    "  return { name: 'school', tools: {} };\n"
    "}\n"
)


def _safe_str(v: Any, default: str = "") -> str:
    try:
        return default if v is None else str(v)
    except Exception:  # noqa: BLE001
        return default


def emit_opencode() -> str:
    """The canonical OpenCode TypeScript plugin (46 tools). Fail-open."""
    try:
        from school.plugin_source import TS_PLUGIN_SOURCE

        return TS_PLUGIN_SOURCE
    except Exception:  # noqa: BLE001
        return _MINIMAL_TS


def emit_claude_code() -> str:
    """Claude Code ``.claude/commands`` + settings shim (JSON commands)."""
    try:
        body = {
            "name": "school",
            "description": "School agent tools (48) via MCP/CLI bridge.",
            "mcpServers": {"school": {"command": "python", "args": ["-m", "school_mcp.server"]}},
            "tools": ["school_*"],
        }
        import json

        return json.dumps(body, indent=2)
    except Exception:  # noqa: BLE001
        return "{}"


def emit_codex() -> str:
    """Codex ``config.toml`` shim."""
    try:
        return (
            "[mcp_servers.school]\n"
            'command = "python"\n'
            'args = ["-m", "school_mcp.server"]\n'
            "enabled = true\n"
        )
    except Exception:  # noqa: BLE001
        return ""


def emit_cursor() -> str:
    """Cursor ``.cursor/mcp.json`` shim."""
    try:
        import json

        return json.dumps(
            {"mcpServers": {"school": {"command": "python", "args": ["-m", "school_mcp.server"]}}},
            indent=2,
        )
    except Exception:  # noqa: BLE001
        return "{}"


def emit_generic() -> str:
    """Generic agent: a description + how to reach School via CLI/MCP."""
    try:
        return (
            "# School for any agent\n\n"
            "Call School tools through either interface:\n"
            "- MCP: `python -m school_mcp.server` (stdio or HTTP)\n"
            "- CLI: `school-bridge '<json>'` or `python -m school.cli <cmd>`\n"
            "All 48 tools are fail-open and never crash the host agent.\n"
        )
    except Exception:  # noqa: BLE001
        return ""


def _mcp_json(shape: str = "mcpServers") -> str:
    """Generic stdio MCP registration JSON in a given top-level shape."""
    try:
        import json

        entry = {"command": "python", "args": ["-m", "school_mcp.server"]}
        return json.dumps({shape: {"school": entry}}, indent=2)
    except Exception:  # noqa: BLE001
        return "{}"


def _remote_connector(url: str = "http://127.0.0.1:8765/mcp") -> str:
    """Remote MCP connector record for web interfaces (ChatGPT / Claude.ai)."""
    try:
        import json

        body = {
            "connector": {
                "name": "school",
                "url": url,
                "transport": "streamable-http",
            }
        }
        return json.dumps(body, indent=2)
    except Exception:  # noqa: BLE001
        return "{}"


def emit_claude_desktop() -> str:
    """Claude Desktop ``claude_desktop_config.json`` (mcpServers)."""
    return _mcp_json("mcpServers")


def emit_windsurf() -> str:
    """Windsurf ``~/.codeium/windsurf/mcp_config.json`` (mcpServers)."""
    return _mcp_json("mcpServers")


def emit_cline() -> str:
    """Cline ``cline_mcp_settings.json`` (mcpServers)."""
    return _mcp_json("mcpServers")


def emit_vscode() -> str:
    """VS Code ``.vscode/mcp.json`` (uses ``servers``, not ``mcpServers``)."""
    try:
        import json

        entry = {"type": "stdio", "command": "python", "args": ["-m", "school_mcp.server"]}
        return json.dumps({"servers": {"school": entry}}, indent=2)
    except Exception:  # noqa: BLE001
        return "{}"


def emit_zed() -> str:
    """Zed ``settings.json`` (uses ``context_servers``)."""
    return _mcp_json("context_servers")


def emit_continue() -> str:
    """Continue ``config.yaml`` (YAML mcpServers)."""
    return (
        "mcpServers:\n"
        "  school:\n"
        '    command: "python"\n'
        "    args:\n"
        '      - "-m"\n'
        '      - "school_mcp.server"\n'
    )


def emit_aider() -> str:
    """Aider project ``.mcp.json`` (mcpServers)."""
    return _mcp_json("mcpServers")


def emit_chatgpt() -> str:
    """ChatGPT custom MCP connector (remote streamable-HTTP)."""
    return _remote_connector()


def emit_claude_ai() -> str:
    """Claude.ai custom connector (remote streamable-HTTP)."""
    return _remote_connector()


ADAPTERS: dict[str, Any] = {
    "opencode": emit_opencode,
    "claude_code": emit_claude_code,
    "claude_desktop": emit_claude_desktop,
    "claude_ai": emit_claude_ai,
    "chatgpt": emit_chatgpt,
    "codex": emit_codex,
    "cursor": emit_cursor,
    "windsurf": emit_windsurf,
    "cline": emit_cline,
    "vscode": emit_vscode,
    "zed": emit_zed,
    "continue": emit_continue,
    "aider": emit_aider,
    "generic": emit_generic,
}


def emit_plugin(cli: str = "opencode") -> str:
    """Emit the plugin payload for a named CLI. FAIL-OPEN: never raises."""
    try:
        fn = ADAPTERS.get(cli) or emit_generic
        return fn()
    except Exception:  # noqa: BLE001
        return _MINIMAL_TS


def adapter_for(cli: str) -> dict:
    """Describe the adapter for a CLI. Fail-open."""
    try:
        return {
            "cli": _safe_str(cli, "generic"),
            "known": cli in ADAPTERS,
            "payload": emit_plugin(cli),
        }
    except Exception as exc:  # noqa: BLE001
        return {"cli": _safe_str(cli), "error": _safe_str(exc, "adapter error")[:120]}
