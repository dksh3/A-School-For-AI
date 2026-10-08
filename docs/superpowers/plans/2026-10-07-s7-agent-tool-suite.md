# S7: Agent-Native Tool Suite — Implementation Plan

Spec: `docs/superpowers/specs/2026-10-07-s7-agent-tool-suite-design.md`
Master spec: `docs/superpowers/specs/2026-10-06-school-context-engine-design.md`
Base: HEAD c62e3ce (NO COMMITS rule)

## Task Batches

- **Batch 1** — Tasks 1–2: `school_observe` + `school_goal`
- **Batch 2** — Tasks 3–4: `school_research` + `school_explore`
- **Batch 3** — Tasks 5–6: `school_progress` + `school_session`
- **Batch 4** — Tasks 7–8: `school_execute` + `school_navigate`
- **Batch 5** — Task 9: Integration + full regression gates

---

### Task 1: `school_observe`

**Files:**
- Create: `core/agent/observer.py`
- Create: `tests/unit/test_agent_observer.py`
- Modify: `school/plugin_source.py` (add TS tool block)
- Modify: `school/mcp/server.py` (add MCP tool)
- Modify: `school/bridge.py` (add bridge command)

**Interfaces:**
- Produces: `observe(observation, category, evidence) -> ObserveResult`
- Consumes: `core/knowledge` (MemoryManager)

**Steps:**
1. Write failing tests: `test_observe_records`, `test_observe_extracts_pattern`, `test_observe_kill_switch`, `test_observe_fail_open`
2. Implement `core/agent/observer.py`
3. Add TS tool block + MCP tool + bridge command
4. Parity tests: TS == MCP descriptions
5. Run tests → all pass
6. Ruff + `node --check`

---

### Task 2: `school_goal`

**Files:**
- Create: `core/agent/goals.py`
- Create: `tests/unit/test_agent_goals.py`
- Modify: `school/plugin_source.py`, `school/mcp/server.py`, `school/bridge.py`

**Interfaces:**
- Produces: `goal(action, goal_id, objective, success_criteria, ...) -> GoalResult`
- Consumes: `core/knowledge` (MemoryManager)

**Steps:**
1. Write failing tests: `test_goal_set`, `test_goal_status`, `test_goal_complete`, `test_goal_block`, `test_goal_history`, `test_goal_kill_switch`
2. Implement `core/agent/goals.py`
3. Add TS + MCP + bridge surfaces
4. Parity tests
5. Run tests → all pass
6. Ruff + `node --check`

---

### Task 3: `school_research`

**Files:**
- Create: `core/agent/researcher.py`
- Create: `tests/unit/test_agent_researcher.py`
- Modify: `school/plugin_source.py`, `school/mcp/server.py`, `school/bridge.py`

**Interfaces:**
- Produces: `research(query, depth, format) -> ResearchResult`
- Consumes: `core/knowledge` (MemoryManager), `core/evaluator` (if available)

**Steps:**
1. Write failing tests: `test_research_internal_first`, `test_research_distills_learnings`, `test_research_kill_switch`, `test_research_fail_open`
2. Implement `core/agent/researcher.py`
3. Add TS + MCP + bridge surfaces
4. Parity tests
5. Run tests → all pass
6. Ruff + `node --check`

---

### Task 4: `school_explore`

**Files:**
- Create: `core/agent/explorer.py`
- Create: `tests/unit/test_agent_explorer.py`
- Modify: `school/plugin_source.py`, `school/mcp/server.py`, `school/bridge.py`

**Interfaces:**
- Produces: `explore(target, depth, focus) -> ExploreResult`
- Consumes: `core/knowledge` (MemoryManager)

**Steps:**
1. Write failing tests: `test_explore_structure`, `test_explore_patterns`, `test_explore_kill_switch`, `test_explore_fail_open`
2. Implement `core/agent/explorer.py`
3. Add TS + MCP + bridge surfaces
4. Parity tests
5. Run tests → all pass
6. Ruff + `node --check`

---

### Task 5: `school_progress`

**Files:**
- Create: `core/agent/progress.py`
- Create: `tests/unit/test_agent_progress.py`
- Modify: `school/plugin_source.py`, `school/mcp/server.py`, `school/bridge.py`

**Interfaces:**
- Produces: `progress(action, items, context) -> ProgressResult`
- Consumes: `core/context.progress` (bar rendering)

**Steps:**
1. Write failing tests: `test_progress_write`, `test_progress_read`, `test_progress_bars`, `test_progress_kill_switch`
2. Implement `core/agent/progress.py`
3. Add TS + MCP + bridge surfaces
4. Parity tests
5. Run tests → all pass
6. Ruff + `node --check`

---

### Task 6: `school_session`

**Files:**
- Create: `core/agent/sessions.py`
- Create: `tests/unit/test_agent_sessions.py`
- Modify: `school/plugin_source.py`, `school/mcp/server.py`, `school/bridge.py`

**Interfaces:**
- Produces: `session(action, session_id, focus) -> SessionResult`
- Consumes: `core/knowledge` (MemoryManager)

**Steps:**
1. Write failing tests: `test_session_create`, `test_session_resume`, `test_session_summarize`, `test_session_export`, `test_session_kill_switch`
2. Implement `core/agent/sessions.py`
3. Add TS + MCP + bridge surfaces
4. Parity tests
5. Run tests → all pass
6. Ruff + `node --check`

---

### Task 7: `school_execute`

**Files:**
- Create: `core/agent/executor.py`
- Create: `tests/unit/test_agent_executor.py`
- Modify: `school/plugin_source.py`, `school/mcp/server.py`, `school/bridge.py`

**Interfaces:**
- Produces: `execute(command, learn, context) -> ExecuteResult`
- Consumes: `core/knowledge` (MemoryManager)

**Steps:**
1. Write failing tests: `test_execute_learns_on_success`, `test_execute_learns_on_failure`, `test_execute_no_learn`, `test_execute_kill_switch`
2. Implement `core/agent/executor.py`
3. Add TS + MCP + bridge surfaces
4. Parity tests
5. Run tests → all pass
6. Ruff + `node --check`

---

### Task 8: `school_navigate`

**Files:**
- Create: `core/agent/navigator.py`
- Create: `tests/unit/test_agent_navigator.py`
- Modify: `school/plugin_source.py`, `school/mcp/server.py`, `school/bridge.py`

**Interfaces:**
- Produces: `navigate(action, path, pattern, depth) -> NavigateResult`
- Consumes: `core/knowledge` (MemoryManager)

**Steps:**
1. Write failing tests: `test_navigate_read`, `test_navigate_list`, `test_navigate_search`, `test_navigate_map`, `test_navigate_kill_switch`
2. Implement `core/agent/navigator.py`
3. Add TS + MCP + bridge surfaces
4. Parity tests
5. Run tests → all pass
6. Ruff + `node --check`

---

### Task 9: Integration + full regression gates

**Files:**
- Create: `tests/integration/test_agent_tools.py`

**Steps:**
1. Write integration tests: `test_all_tools_end_to_end`, `test_parity_all_tools`, `test_dashboard_shows_goals`, `test_footer_shows_progress`
2. Run full battery
3. Ruff over all touched files
4. `node --check` exit 0
5. S7 exit criteria checklist

---

## Constraints (from master spec)

- Apple-grade presentation on every surface.
- Fail-open everywhere.
- No secrets in observations/learnings.
- Kill switches for every automatic behavior.
- Backward compat: existing tools stay green.
- No commits unless the user explicitly asks.
