# S6: Progress & Live Telemetry UX — Implementation Plan

Spec: `docs/superpowers/specs/2026-10-07-s6-progress-telemetry-design.md`
Master spec: `docs/superpowers/specs/2026-10-06-school-context-engine-design.md`
Base: HEAD c62e3ce (NO COMMITS rule)

## Task Batches

- **Batch 1** — Tasks 1–2: Progress renderer + Telemetry collector
- **Batch 2** — Tasks 3–4: Bar graph builder + Cumulative stats
- **Batch 3** — Tasks 5–6: Watchdog + Parity tests
- **Batch 4** — Task 7: Integration + full regression gates

---

### Task 1: Progress renderer (`core/context/progress.py`)

**Files:**
- Create: `core/context/progress.py`
- Create: `tests/unit/test_context_progress.py`

**Interfaces:**
- Produces: `render_bar(ratio, width, label) -> str`, `render_eta(elapsed_ms, ratio) -> str`
- Consumes: none (pure functions)

**Steps:**
1. Write failing tests: `test_bar_renders_at_0`, `test_bar_renders_at_50`, `test_bar_renders_at_100`, `test_bar_clamps_over_1`, `test_bar_clamps_under_0`, `test_eta_formats_seconds`, `test_eta_formats_minutes`, `test_eta_none_when_zero`
2. Implement `core/context/progress.py`
3. Run tests → all pass
4. Ruff clean

---

### Task 2: Telemetry collector (`core/context/telemetry.py`)

**Files:**
- Create: `core/context/telemetry.py`
- Create: `tests/unit/test_context_telemetry.py`

**Interfaces:**
- Produces: `TelemetryCollector(worktree, session)`, `.record(event)`, `.events() -> list`, `.flush()`
- Consumes: `core.context.types` (for event schema)

**Steps:**
1. Write failing tests: `test_record_and_read`, `test_flush_is_atomic`, `test_bounded_retention`, `test_corrupt_line_skipped`, `test_kill_switch_silent`
2. Implement `core/context/telemetry.py`
3. Run tests → all pass
4. Ruff clean

---

### Task 3: Bar graph builder (`core/context/graph.py`)

**Files:**
- Create: `core/context/graph.py`
- Create: `tests/unit/test_context_graph.py`

**Interfaces:**
- Produces: `render_bar_graph(items, width) -> str`
- Consumes: `core.context.progress` (for bar rendering)

**Steps:**
1. Write failing tests: `test_graph_renders_sorted`, `test_graph_empty`, `test_graph_compact_numbers`, `test_graph_single_item`
2. Implement `core/context/graph.py`
3. Run tests → all pass
4. Ruff clean

---

### Task 4: Cumulative stats (`core/context/cumulative.py`)

**Files:**
- Create: `core/context/cumulative.py`
- Create: `tests/unit/test_context_cumulative.py`

**Interfaces:**
- Produces: `CumulativeStats(worktree)`, `.refresh()`, `.to_dict()`, `.render_chip() -> str`
- Consumes: `core.context.telemetry` (for event data), `core.context.store` (for block count)

**Steps:**
1. Write failing tests: `test_default_stats`, `test_refresh_from_events`, `test_reconciles_with_block_store`, `test_render_chip_format`, `test_atomic_write`
2. Implement `core/context/cumulative.py`
3. Run tests → all pass
4. Ruff clean

---

### Task 5: Watchdog (`core/context/watchdog.py`)

**Files:**
- Create: `core/context/watchdog.py`
- Create: `tests/unit/test_context_watchdog.py`

**Interfaces:**
- Produces: `watchdog(fn, *args, timeout_ms=5000, **kwargs) -> Any`
- Consumes: none (pure decorator)

**Steps:**
1. Write failing tests: `test_passes_through_success`, `test_retries_once_on_error`, `test_fails_open_after_retry`, `test_timeout_triggers_retry`, `test_kill_switch_no_retry`, `test_covers_all_commands`
2. Implement `core/context/watchdog.py`
3. Run tests → all pass
4. Ruff clean

---

### Task 6: Parity tests (TS == MCP == CLI)

**Files:**
- Create: `tests/unit/test_context_parity.py`

**Interfaces:**
- Consumes: `school.plugin_source.TS_PLUGIN_SOURCE`, `school.mcp.server`, `school.cli`

**Steps:**
1. Write failing tests: `test_progress_bar_parity`, `test_bar_graph_parity`, `test_cumulative_chip_parity`, `test_watchdog_stub_parity`
2. Fix any parity gaps
3. Run tests → all pass
4. Ruff clean

---

### Task 7: Integration + full regression gates

**Files:**
- Create: `tests/integration/test_context_telemetry.py`

**Steps:**
1. Write integration tests: `test_telemetry_end_to_end`, `test_watchdog_over_bridge`, `test_cumulative_reconciles`
2. Run full battery
3. Ruff over all touched files
4. `node --check` exit 0
5. S6 exit criteria checklist

---

## Constraints (from master spec)

- Apple-grade presentation on every surface.
- Fail-open everywhere.
- No secrets in telemetry.
- Kill switches for every automatic behavior.
- Backward compat: existing tools stay green.
- No commits unless the user explicitly asks.
