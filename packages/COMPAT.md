# School — Universal Compatibility Guide (Phase D)

School's tools reach **every** AI agent through two universal mechanisms:

1. **MCP** (`packages/mcp/school_mcp/`) — the Model Context Protocol, a
   standard supported by Claude, ChatGPT, VS Code, Cursor, Zed, and more.
   Registers all **48 tools**. Runs over **stdio** (local) or **streamable-HTTP**
   (remote, `http://127.0.0.1:8765/mcp`).
2. **Plugin / CLI bridge** (`packages/plugin/school_plugin/`) — the native
   OpenCode TypeScript plugin (46 tools) plus CLI/MCP shims for every other host.

Both are **fail-open**: hostile input never raises and never crashes the host.

## Compatibility matrix

| Client | Kind | Transport | Config file | Key shape |
|---|---|---|---|---|
| OpenCode | local | stdio | `opencode.jsonc` | `mcp.school` |
| Claude Code | local | stdio | `.mcp.json` | `mcpServers` |
| Claude Desktop | local | stdio | `%APPDATA%\Claude\claude_desktop_config.json` | `mcpServers` |
| Claude.ai (web) | remote | http | Settings → Connectors | connector |
| ChatGPT (web) | remote | http | Settings → Connectors | connector |
| OpenAI Codex CLI | local | stdio | `~/.codex/config.toml` | `[mcp_servers.school]` |
| Cursor | local | stdio | `~/.cursor/mcp.json` | `mcpServers` |
| Windsurf | local | stdio | `~/.codeium/windsurf/mcp_config.json` | `mcpServers` |
| Cline | local | stdio | `cline_mcp_settings.json` | `mcpServers` |
| VS Code (Copilot) | local | stdio | `.vscode/mcp.json` | `servers` |
| Zed | local | stdio | `~/.config/zed/settings.json` | `context_servers` |
| Continue | local | stdio | `~/.continue/config.yaml` | `mcpServers` (YAML) |
| Aider | local | stdio | `.mcp.json` | `mcpServers` |
| Any MCP client | either | either | (client-specific) | `mcpServers` |

Generate any row with:

```python
from school_mcp.compat import generate, all_configs, as_json
print(as_json("cursor"))           # Cursor config
print(as_json("chatgpt"))          # ChatGPT remote connector
print(all_configs())               # every client at once
```

## Web interfaces (ChatGPT / Claude.ai)

Web assistants connect to School as a **remote MCP connector** over
streamable-HTTP. Start the server in HTTP mode, then register the URL:

```bash
python -m school_mcp.server http     # serves http://127.0.0.1:8765/mcp
```

Then add `http://127.0.0.1:8765/mcp` as a custom connector in ChatGPT
(developer mode) or Claude.ai (Connectors → Add custom connector). School
exposes all 48 tools to the web assistant through that one URL.

## MCP in general

MCP is the great equalizer: build once, run in any compliant client. School's
server speaks the standard protocol, so any present-or-future MCP client —
desktop, editor, CLI, or web — can discover and call all 48 tools with no
custom code. Local clients spawn the server over stdio; remote/web clients
reach it over streamable-HTTP. Both paths route into the same fail-open
`call_tool` dispatch (`packages/mcp/school_mcp/tools.py`).

## Plugin / CLI bridge

For hosts that load native plugins (OpenCode), `emit_opencode()` ships the full
TypeScript plugin with 46 tools and the visual/guard layers. For every other
host, `emit_plugin(cli)` returns the right MCP registration shim so the agent
gets School's tools through MCP. `school-bridge '<json>'` and
`python -m school.cli <cmd>` remain available for shell-driven agents.

## Fail-proof guarantees

- Every `call_tool`, `describe`, `generate`, `emit_*` returns a dict/str and
  **never raises**, even on `_Evil`/`_Throws`/cyclic/NaN/oversized input.
- Concurrency-safe (hammered by 8 threads in tests).
- No dependency on the `mcp` SDK for the registry/dispatch layer — importable
  and testable everywhere; the SDK is only used when actually serving.
