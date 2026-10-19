"""School MCP server — multi-transport, fail-open.

Wraps the optional ``mcp`` SDK to expose all 48 ``school_*`` tools over stdio
and streamable-HTTP. Every handler is fail-open: tool errors are returned as
structured results, never as crashes. If the ``mcp`` SDK is absent, ``available``
is False and the pure-Python ``tools.call_tool`` still works standalone.
"""

from __future__ import annotations

import inspect
from typing import Any

from .tools import TOOL_NAMES, TOOLS, _safe_str, call_tool

try:  # optional SDK — support both mcp v1 (FastMCP) and v2 (MCPServer)
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore  # mcp < 2
    except Exception:  # noqa: BLE001
        from mcp.server.mcpserver import MCPServer as FastMCP  # type: ignore  # mcp 2.x

    SDK = True
except Exception:  # noqa: BLE001
    FastMCP = None  # type: ignore
    SDK = False


def available() -> bool:
    """True when the ``mcp`` SDK is importable."""
    return SDK


def build_server(name: str = "school", **kwargs: Any):
    """Build a FastMCP server exposing all 48 tools. Fail-open.

    Returns the FastMCP instance, or an error dict if the SDK is missing.
    """
    if not SDK:
        return {"ok": False, "error": "mcp SDK not installed"}
    try:
        mcp = FastMCP(name, **kwargs)

        for tool_name in TOOL_NAMES:
            meta = TOOLS[tool_name]
            desc = meta["description"]

            def _make(n: str):
                def _handler(**tool_args: Any) -> dict:
                    try:
                        return call_tool(n, tool_args)
                    except Exception as exc:  # noqa: BLE001
                        return {"ok": False, "error": _safe_str(exc)[:200]}

                return _handler

            handler = _make(tool_name)
            handler.__name__ = tool_name
            handler.__doc__ = desc
            # Give the handler a flat signature matching the tool's real schema
            # so the SDK generates the correct inputSchema and accepts the flat
            # arguments clients send (instead of a wrapping ``tool_args`` object).
            try:
                props = (meta.get("schema") or {}).get("properties") or {}
                params = [
                    inspect.Parameter(
                        _safe_str(prop, "arg"),
                        inspect.Parameter.KEYWORD_ONLY,
                        default=None,
                        annotation=Any,
                    )
                    for prop in props
                ]
                handler.__signature__ = inspect.Signature(params)  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass
            # Register with a permissive schema (args forwarded fail-open).
            try:
                mcp.tool(name=tool_name, description=desc)(handler)
            except Exception:  # noqa: BLE001
                continue

        return mcp
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": _safe_str(exc)[:200]}


def run_stdio(server: Any) -> None:
    """Run a built server over stdio. Fail-open (no raise)."""
    try:
        if hasattr(server, "run"):
            server.run("stdio")
    except Exception:  # noqa: BLE001
        return


def run_http(server: Any, host: str = "127.0.0.1", port: int = 8765, **kw: Any) -> None:
    """Run a built server over streamable-HTTP. Fail-open (no raise)."""
    try:
        if hasattr(server, "run"):
            server.run("streamable-http", host=host, port=port, **kw)
        elif hasattr(server, "run_http"):
            server.run_http(host=host, port=port, **kw)
    except Exception:  # noqa: BLE001
        return


def main() -> None:
    import sys

    transport = "stdio"
    if len(sys.argv) > 1 and sys.argv[1] in {"http", "stdio"}:
        transport = sys.argv[1]
    server = build_server()
    if isinstance(server, dict):  # SDK missing — degrade gracefully
        print(_safe_str(server.get("error", "server unavailable")))
        raise SystemExit(0)
    if transport == "http":
        run_http(server)
    else:
        run_stdio(server)


if __name__ == "__main__":
    main()
