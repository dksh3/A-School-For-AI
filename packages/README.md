# School — Distribution Packages

Universal, fail-proof distribution of School (all **48 tools**) for every AI
agent — coding, writing, research, business, planning, education, creative,
ops, data, life, and general.

## Layout

- `packages/mcp/school_mcp/` — the **MCP server** + client-compat config
  generators. `tools.py` (48-tool fail-open registry + `call_tool`/`describe`),
  `server.py` (stdio + streamable-HTTP), `compat.py` (config for 14 clients
  incl. ChatGPT / Claude.ai web connectors).
- `packages/plugin/school_plugin/` — the **plugin/CLI bridge** adapters that
  emit the native OpenCode plugin and MCP shims for every other host.
- `packages/tests/test_dist_failproof.py` — the **designed-to-fail** adversarial
  suite (hostile, wrong-typed, cyclic, concurrent input). 33 tests; if it
  passes, the packages are fool-proof.
- `packages/COMPAT.md` — the full compatibility matrix + setup guide.

## Quick start

```bash
# MCP over stdio (local CLIs / desktop apps)
python -m school_mcp.server

# MCP over streamable-HTTP (web interfaces: ChatGPT / Claude.ai)
python -m school_mcp.server http     # http://127.0.0.1:8765/mcp
```

```python
from school_mcp.compat import as_json
print(as_json("cursor"))             # ready-to-paste config for any client
```

## Design principles

1. **Universal** — one build reaches every agent type and every host.
2. **Fail-open** — nothing ever raises; hostile input degrades gracefully.
3. **Fool-proof** — proven by the adversarial suite before shipping.

See `COMPAT.md` for per-client setup and the full compatibility matrix.
