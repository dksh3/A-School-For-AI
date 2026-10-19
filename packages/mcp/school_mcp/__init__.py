"""School MCP distribution package.

A self-contained, fail-open MCP server exposing all 48 ``school_*`` tools.
Works with any MCP client (Claude Desktop, Claude/ChatGPT via MCP, Cursor,
VS Code, Zed, Windsurf, ...) over stdio or streamable-HTTP.
"""

from .tools import (
    CATALOG,
    TOOL_NAMES,
    TOOLS,
    call_tool,
    describe,
)

__all__ = [
    "CATALOG",
    "TOOLS",
    "TOOL_NAMES",
    "call_tool",
    "describe",
    "build_server",
]


def build_server(*args, **kwargs):
    """Build the MCP server (requires the optional ``mcp`` SDK). Fail-open."""
    try:
        from .server import build_server as _build

        return _build(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"server unavailable: {exc}"}
