# S6: Progress & Live Telemetry UX — Design Spec

Date: 2026-10-07
Status: design — derived from master spec §10 (S6 row) and §7 (dashboards)
Master spec: `docs/superpowers/specs/2026-10-06-school-context-engine-design.md`

## 1. Goal

Every School surface gains **live, Apple-grade progress and telemetry**:
animated progress bars for long operations, bar graphs of context/token usage,
cumulative stats (tokens saved, contexts saved/restored), and a hard
**always-working guarantee** on every context tool (fail-open + watchdog +
parity tests).

## 2. Subsystems

| # | Subsystem | What it builds | Inspired by |
|---|-----------|---------------|-------------|
| 2.1 | **Progress renderer** | Unicode bar/gauge builder: `████████░░ 80%` with label + ETA. Deterministic (mocked clock). | OpenCode `todowrite` progress, Apple Activity Monitor |
| 2.2 | **Telemetry collector** | Append-only JSONL ledger per session: every tool call, token delta, compression event, restore event. Reconciles with block store. | OpenCode `browser.network.list`, `browser.cpu.analyze` |
| 2.3 | **Bar graph builder** | Horizontal bar graphs for context/token usage by tool. Renders in CLI, MCP text, footer chip. | OpenCode `browser.heap.compare` (class deltas) |
| 2.4 | **Cumulative stats** | Tokens saved, contexts compressed, contexts restored, blocks alive — rolling window + all-time. Surfaced in `school_dashboard`, `school status`, footer. | OpenCode `get_goal_history` |
| 2.5 | **Watchdog** | Context-tool always-working guarantee: any error/timeout/corrupt-store path must return a valid response (fail-open). Watchdog retries once, then degrades to a no-op chip. | OpenCode fail-open pattern |
| 2.6 | **Parity tests** | TS ↔ MCP ↔ CLI output byte-equal for every telemetry surface. | Existing S2 parity tests |

## 3. Data flow

```
tool call / compression / restore
    │
    ▼
TelemetryCollector.record(event)
    │  (append-only JSONL, atomic, bounded)
    ▼
<worktree>/.school/telemetry/<session>.jsonl
    │
    ├─► CumulativeStats.refresh()  ──►  dashboard / footer / CLI
    ├─► BarGraphBuilder.build()    ──►  CLI `school tokens report` / MCP text
    └─► ProgressRenderer.render()  ──►  live TUI / footer chip
```

## 4. Progress renderer

```python
def render_bar(ratio: float, width: int = 20, label: str = "") -> str:
    """Return: 'label ████████░░░░░░░░░░░░ 40%'"""
```

- Ratio clamped 0–1. Fills use `█` (U+2588), empties use `░` (U+2591).
- Label left-aligned, percentage right-aligned.
- Deterministic: no ANSI, no clock reads (caller passes elapsed/total).
- `render_eta(elapsed_ms, ratio) -> str` returns `~2m 14s` or `—`.

## 5. Bar graph builder

```python
def render_bar_graph(items: list[tuple[str, float]], width: int = 24) -> str:
    """Return multi-line horizontal bar graph sorted by value descending."""
```

- Each line: `label ▕████████░░░░░░░░░░░░░░░░▏ 1.2k`
- Values use compact notation (`1.2k`, `3.4M`).
- Empty list → `"(no data)"`.
- Used by `school tokens report --graph` and `school_dashboard`.

## 6. Cumulative stats

Stored at `<worktree>/.school/telemetry/cumulative.json`:

```json
{
  "tokens_saved": 18400,
  "contexts_compressed": 12,
  "contexts_restored": 3,
  "blocks_alive": 47,
  "tool_calls": 312,
  "last_updated": "2026-10-07T21:00:00Z"
}
```

- Atomic write (tmp + `os.replace`).
- Updated on every telemetry event.
- Surfaced in `school_dashboard` as a compact block:

```
[school] saved 18.4k tok · 12 compacted · 3 restored · 47 blocks
```

## 7. Watchdog (always-working guarantee)

Every context tool entry point wraps in `watchdog()`:

```python
def watchdog(fn, *args, **kwargs):
    """Call fn; on any exception/timeout, retry once, then return fail-open stub."""
```

- Fail-open stub: `{"ok": True, "mode": "degraded", "chip": "[school] degraded"}`
- Timeout: 5s per call (configurable via `SCHOOL_WATCHDOG_MS`).
- Kill switch: `SCHOOL_WATCHDOG=0` disables retry (still fail-open).
- Covers: `context_status`, `context_compress`, `context_restore`, `context_view`, `context_coexist`.

## 8. Parity tests

For every telemetry surface (progress bar, bar graph, cumulative stats block):

1. TS plugin output == MCP output == CLI output (byte-equal).
2. Deterministic under mocked clock.
3. Kill switch off → empty/silent output.

## 9. Kill switches

| Env | Effect |
|-----|--------|
| `SCHOOL_TELEMETRY=0` | No telemetry collection, no cumulative stats |
| `SCHOOL_WATCHDOG=0` | No retry (fail-open still active) |
| `SCHOOL_HOOKS=0` | No footer progress/graph |
| `SCHOOL_PROGRESS=0` | No animated bars in CLI |

## 10. Exit criteria

- [ ] Progress bars render under mocked clock (unit tests)
- [ ] Bar graphs render correctly (unit tests)
- [ ] Cumulative stats reconcile with block store (integration test)
- [ ] Watchdog covers all 5 context commands (error, timeout, corrupt-store paths)
- [ ] Parity tests: TS == MCP == CLI for all telemetry surfaces
- [ ] Full battery green
- [ ] `ruff check` clean (plugin_source.py stays at 16 E501)
- [ ] `node --check` exit 0

## 11. Constraints (from master spec)

- Apple-grade presentation on every surface.
- Fail-open everywhere.
- No secrets in telemetry.
- Kill switches for every automatic behavior.
- Backward compat: existing tools stay green.
