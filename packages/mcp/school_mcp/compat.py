"""Client compatibility for the School MCP distribution.

Generates ready-to-paste configuration for every MCP-capable client: local
CLIs (stdio servers), desktop apps, editors, and web interfaces (remote
connectors over streamable-HTTP). Every generator is FAIL-OPEN and returns a
dict that is always JSON/TOML/YAML-serializable, whatever the input.

Layout of a generated record::

    {
      "client": <id>,
      "display": <human name>,
      "kind": "local" | "remote",
      "transport": "stdio" | "http",
      "filename": <where to put it>,
      "format": "json" | "toml" | "yaml",
      "config": <the payload to write>,
      "notes": <free-form setup guidance>,
    }

Nothing here imports the ``mcp`` SDK, so it works everywhere.
"""

from __future__ import annotations

import json
from typing import Any

#: Command that launches the School MCP server over stdio.
SERVER_CMD: list[str] = ["python", "-m", "school_mcp.server"]

#: Default streamable-HTTP endpoint served by ``school_mcp.server``.
DEFAULT_HTTP_URL = "http://127.0.0.1:8765/mcp"

_STDIO_SERVER_ENTRY = {
    "command": SERVER_CMD[0],
    "args": SERVER_CMD[1:],
}


def _safe_str(value: Any, default: str = "") -> str:
    """Stringify anything without raising."""
    try:
        if isinstance(value, str):
            return value
        return str(value)
    except Exception:  # noqa: BLE001
        return default


def _norm_url(url: Any) -> str:
    """Return a usable URL; fall back to the default local endpoint."""
    text = _safe_str(url).strip()
    if text.startswith("http://") or text.startswith("https://"):
        return text
    return DEFAULT_HTTP_URL


def _stdio_payload() -> dict[str, Any]:
    return {"command": _STDIO_SERVER_ENTRY["command"], "args": list(SERVER_CMD[1:])}


def _mcp_servers_payload() -> dict[str, Any]:
    return {"mcpServers": {"school": _stdio_payload()}}


def _vscode_payload(url: Any, remote: bool) -> dict[str, Any]:
    if remote:
        return {"servers": {"school": {"type": "http", "url": _norm_url(url)}}}
    entry = {"type": "stdio", "command": SERVER_CMD[0], "args": list(SERVER_CMD[1:])}
    return {"servers": {"school": entry}}


def _zed_payload() -> dict[str, Any]:
    return {"context_servers": {"school": _stdio_payload()}}


def _codex_payload() -> str:
    args = " ".join(f'"{a}"' for a in SERVER_CMD[1:])
    return (
        "[mcp_servers.school]\n"
        f'command = "{SERVER_CMD[0]}"\n'
        f"args = [{args}]\n"
    )


def _continue_payload() -> str:
    return (
        "mcpServers:\n"
        "  school:\n"
        f'    command: "{SERVER_CMD[0]}"\n'
        "    args:\n"
        + "".join(f'      - "{a}"\n' for a in SERVER_CMD[1:])
    )


def _remote_connector(url: Any, title: str) -> dict[str, Any]:
    return {
        "connector": {
            "name": "school",
            "description": (
                "School — universal agent learning, memory, context, and the "
                "Forge idea-to-artifact suite."
            ),
            "url": _norm_url(url),
            "transport": "streamable-http",
            "title": title,
        }
    }


def _generic_payload(url: Any, remote: bool) -> dict[str, Any]:
    if remote:
        return {"mcpServers": {"school": {"url": _norm_url(url)}}}
    return _mcp_servers_payload()


def _record(
    client: str,
    display: str,
    kind: str,
    transport: str,
    filename: str,
    fmt: str,
    config: Any,
    notes: str,
) -> dict[str, Any]:
    return {
        "client": client,
        "display": display,
        "kind": kind,
        "transport": transport,
        "filename": filename,
        "format": fmt,
        "config": config,
        "notes": notes,
    }


def _build_claude_desktop(url: Any, remote: bool) -> dict[str, Any]:
    if remote:
        cfg = _remote_connector(url, "Claude Desktop connector")
        return _record(
            "claude_desktop", "Claude Desktop", "remote", "http",
            "Connectors (Settings > Connectors)", "json", cfg,
            "Add the remote connector URL in Claude Desktop settings.",
        )
    return _record(
        "claude_desktop", "Claude Desktop", "local", "stdio",
        "%APPDATA%\\Claude\\claude_desktop_config.json "
        "(macOS: ~/Library/Application Support/Claude/claude_desktop_config.json)",
        "json", _mcp_servers_payload(),
        "Restart Claude Desktop after saving.",
    )


def _build_claude_code(url: Any, remote: bool) -> dict[str, Any]:
    if remote:
        return _record(
            "claude_code", "Claude Code", "remote", "http", ".mcp.json", "json",
            {"mcpServers": {"school": {"type": "http", "url": _norm_url(url)}}},
            "Project-scoped .mcp.json; or `claude mcp add --transport http school <url>`.",
        )
    return _record(
        "claude_code", "Claude Code", "local", "stdio", ".mcp.json", "json",
        _mcp_servers_payload(),
        "Project-scoped .mcp.json; or `claude mcp add school -- python -m school_mcp.server`.",
    )


def _build_claude_ai(url: Any, remote: bool) -> dict[str, Any]:
    return _record(
        "claude_ai", "Claude.ai (web)", "remote", "http",
        "Settings > Connectors > Add custom connector", "json",
        _remote_connector(url, "Claude.ai custom connector"),
        "Enable developer mode / custom connectors, then add the MCP URL.",
    )


def _build_chatgpt(url: Any, remote: bool) -> dict[str, Any]:
    return _record(
        "chatgpt", "ChatGPT (web)", "remote", "http",
        "Settings > Connectors > Add custom connector (developer mode)", "json",
        _remote_connector(url, "ChatGPT custom MCP connector"),
        "ChatGPT connectors reach School over streamable-HTTP at the URL above.",
    )


def _build_codex(url: Any, remote: bool) -> dict[str, Any]:
    return _record(
        "codex", "OpenAI Codex CLI", "local", "stdio", "~/.codex/config.toml", "toml",
        _codex_payload(),
        "TOML `mcp_servers.school` block; restart the Codex CLI.",
    )


def _build_cursor(url: Any, remote: bool) -> dict[str, Any]:
    if remote:
        return _record(
            "cursor", "Cursor", "remote", "http", "~/.cursor/mcp.json", "json",
            {"mcpServers": {"school": {"url": _norm_url(url)}}},
            "Cursor supports remote MCP servers via a `url` key.",
        )
    return _record(
        "cursor", "Cursor", "local", "stdio", "~/.cursor/mcp.json", "json",
        _mcp_servers_payload(), "Global or project `.cursor/mcp.json`.",
    )


def _build_windsurf(url: Any, remote: bool) -> dict[str, Any]:
    return _record(
        "windsurf", "Windsurf", "local", "stdio",
        "~/.codeium/windsurf/mcp_config.json", "json", _mcp_servers_payload(),
        "Windsurf uses the standard `mcpServers` shape.",
    )


def _build_cline(url: Any, remote: bool) -> dict[str, Any]:
    return _record(
        "cline", "Cline", "local", "stdio", "cline_mcp_settings.json", "json",
        _mcp_servers_payload(), "Cline MCP settings use `mcpServers`.",
    )


def _build_vscode(url: Any, remote: bool) -> dict[str, Any]:
    return _record(
        "vscode", "VS Code (Copilot)", "remote" if remote else "local",
        "http" if remote else "stdio", ".vscode/mcp.json", "json",
        _vscode_payload(url, remote),
        "VS Code keys the map as `servers`, not `mcpServers`.",
    )


def _build_zed(url: Any, remote: bool) -> dict[str, Any]:
    return _record(
        "zed", "Zed", "local", "stdio", "~/.config/zed/settings.json", "json",
        _zed_payload(), "Zed keys the map as `context_servers`.",
    )


def _build_continue(url: Any, remote: bool) -> dict[str, Any]:
    return _record(
        "continue", "Continue", "local", "stdio",
        "~/.continue/config.yaml", "yaml", _continue_payload(),
        "Continue reads `mcpServers` from YAML config.",
    )


def _build_aider(url: Any, remote: bool) -> dict[str, Any]:
    return _record(
        "aider", "Aider", "local", "stdio", ".mcp.json", "json",
        _mcp_servers_payload(), "Aider loads MCP servers via a project `.mcp.json`.",
    )


def _build_generic(url: Any, remote: bool) -> dict[str, Any]:
    return _record(
        "generic", "Any MCP client", "remote" if remote else "local",
        "http" if remote else "stdio", "mcp config", "json",
        _generic_payload(url, remote),
        "Generic `mcpServers` shape accepted by most clients.",
    )


def _build_opencode(url: Any, remote: bool) -> dict[str, Any]:
    """OpenCode `opencode.jsonc` `mcp` block (local or remote)."""
    if remote:
        entry = {"type": "remote", "url": _norm_url(url), "enabled": True}
    else:
        entry = {
            "type": "local",
            "command": list(SERVER_CMD),
            "enabled": True,
        }
    cfg = {"mcp": {"school": entry}}
    return _record(
        "opencode", "OpenCode", "remote" if remote else "local",
        "http" if remote else "stdio", "opencode.jsonc", "json", cfg,
        "Add under the top-level `mcp` key in opencode.jsonc.",
    )


#: client id -> builder(url, remote) -> record dict
_BUILDERS = {
    "claude_desktop": _build_claude_desktop,
    "claude_code": _build_claude_code,
    "claude_ai": _build_claude_ai,
    "chatgpt": _build_chatgpt,
    "codex": _build_codex,
    "cursor": _build_cursor,
    "windsurf": _build_windsurf,
    "cline": _build_cline,
    "vscode": _build_vscode,
    "zed": _build_zed,
    "continue": _build_continue,
    "aider": _build_aider,
    "opencode": _build_opencode,
    "generic": _build_generic,
}

#: stable ordered list of supported client ids
CLIENTS: list[str] = sorted(_BUILDERS)

#: ids that are web interfaces / remote connectors by default
REMOTE_CLIENTS: list[str] = ["claude_ai", "chatgpt"]


def generate(client: Any, url: Any = None, remote: Any = None) -> dict[str, Any]:
    """Return the config record for a client. FAIL-OPEN, never raises.

    Unknown clients fall back to the generic shape. If ``remote`` is None the
    value is inferred (web connectors default to remote).
    """
    try:
        key = _safe_str(client).strip().lower()
        builder = _BUILDERS.get(key, _build_generic)
        if remote is None:
            remote = key in REMOTE_CLIENTS
        try:
            is_remote = bool(remote)
        except Exception:  # noqa: BLE001
            is_remote = key in REMOTE_CLIENTS
        return builder(url, is_remote)
    except Exception:  # noqa: BLE001
        return _record(
            "generic", "Any MCP client", "local", "stdio", "mcp config", "json",
            _mcp_servers_payload(), "Generic fallback.",
        )


def all_configs(url: Any = None) -> dict[str, Any]:
    """Return {client_id: record} for every supported client. Fail-open."""
    out: dict[str, Any] = {}
    try:
        for key in CLIENTS:
            out[key] = generate(key, url)
    except Exception:  # noqa: BLE001
        pass
    return out


def describe_clients() -> list[dict[str, Any]]:
    """Return a lightweight index of clients (id, display, kind, transport)."""
    rows: list[dict[str, Any]] = []
    try:
        for key in CLIENTS:
            rec = generate(key)
            rows.append({
                "client": rec["client"],
                "display": rec["display"],
                "kind": rec["kind"],
                "transport": rec["transport"],
                "format": rec["format"],
            })
    except Exception:  # noqa: BLE001
        pass
    return rows


def as_json(client: Any, url: Any = None) -> str:
    """Serialize a client config to a string, always valid, fail-open."""
    try:
        rec = generate(client, url)
        return json.dumps(rec, indent=2, default=_safe_str)
    except Exception:  # noqa: BLE001
        return json.dumps({"error": "config generation failed"}, default=_safe_str)
