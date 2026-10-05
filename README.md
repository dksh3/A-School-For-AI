# School

Universal AI-agent learning and long-term memory system.

School gives coding agents persistent, project-scoped memory that survives restarts.

## Install

### Python
```bash
pip install school
```

### npm / bun
```bash
npm install -g @dksh/school
# or
bun install -g @dksh/school
```

### Windows
Download `School-Setup.exe` from [releases](https://github.com/dex34132-web/lerev/releases)

### Chocolatey
```bash
choco install school
```

### Homebrew (macOS)
```bash
brew install school
```

### Linux
```bash
curl -fsSL https://raw.githubusercontent.com/dex34132-web/lerev/main/packaging/linux/install.sh | sh
```

### From source
```bash
git clone https://github.com/dex34132-web/lerev.git
pip install -e .
```

Plugin auto-installs on first use. Restart OpenCode after install.

## What School Does

- Long-term memory across sessions
- Project isolation (memories never leak between projects)
- Session and agent awareness
- Injection detection and security boundaries
- Works with OpenCode, Claude Code, Codex, and others

## How It Works

```
Your coding agent
    │
    ▼
School plugin (auto-discovered)
    │
    ▼
Python bridge (JSON over stdin/stdout)
    │
    ▼
School V2.6 memory engine
    ├── MemoryManager
    ├── Security
    ├── Persistence (project-scoped)
    └── MemoryStore
```

Memory is stored in `.school/memory/` per project.

## CLI

```bash
school --help        # Show commands
school version       # Print version
school status        # Show installation status
school doctor        # Run diagnostics
school install       # Reinstall plugin
school uninstall     # Remove plugin
school mcp           # Run MCP server (stdio)
school mcp config claude   # Print client MCP config
```

## MCP

School ships a production MCP server so any MCP-compatible client (Claude Code,
Codex, OpenCode, Cursor, Windsurf, Cline, Roo, Gemini CLI, …) can use the same
memory core — thin translation over the existing bridge, no second system:

```bash
pip install "school[mcp]"
school mcp                 # stdio server
python -m school.mcp       # identical entry point
```

Eleven `school_*` tools, a budgeted `school://` resource set, and a
`relevant_context` prompt. See **[docs/mcp.md](docs/mcp.md)** for copy-paste client
configs, tool reference, scope rules, and security notes. The JSON bridge and the
OpenCode plugin keep working unchanged alongside it.

- [Adaptive routing](docs/routing.md) - where School tools fire, and why

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
mypy core/
```

## Migration from LEREV

This project was formerly named **LEREV**. The canonical identity is now
**School**. Legacy aliases are kept so existing installs keep working:

- `lerev` console script → runs the School CLI (legacy alias)
- `import lerev` / `python -m lerev.bridge` → shim over `school`
- `LEREV_HOME` / `EVO_HOME` env vars → honoured as fallbacks after `SCHOOL_HOME`
- `lerev-bridge` on PATH → honoured as fallback after `school-bridge`
- `.lerev/memory/` (and older `.evo/memory/`) → copied non-destructively to
  `.school/memory/` on first use; the original data is never deleted
- stale `plugins/lerev.ts` / `node_modules/lerev` → removed on `school install`

New usage should always say **School** / `school` / `school_*`.

## License

MIT — see [LICENSE](LICENSE).
