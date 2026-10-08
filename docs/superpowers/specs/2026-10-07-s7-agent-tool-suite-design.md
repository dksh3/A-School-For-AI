# S7: Agent-Native Tool Suite — Design Spec

Date: 2026-10-07
Status: design — inspired by the OpenCode built-in tool inventory
Master spec: `docs/superpowers/specs/2026-10-06-school-context-engine-design.md`

## 1. Goal

School gains a suite of **agent-native tools** inspired by the OpenCode
built-in tool inventory (browser, memory, goals, web, subagents, session,
files, shell, context, skills). These tools let School **observe, research,
explore, track, and delegate** — turning School from a passive memory store
into an active learning agent.

## 2. Inspiration map

| OpenCode tool family | What it does | School S7 tool | What School does differently |
|---------------------|-------------|----------------|---------------------------|
| `browser.*` (observe, snapshot, evaluate) | See and inspect web pages | **`school_observe`** | Observe agent behavior, tool calls, conversation patterns → learn from them |
| `goal_set/status/complete/block/pause/resume/clear/history/update` | Track goals | **`school_goal`** | Track learning objectives and milestones → auto-advance on evidence |
| `websearch/webfetch` | Research the web | **`school_research`** | Research topics and distill learnings → store as structured memories |
| `subagent` (explore, general) | Delegate tasks | **`school_explore`** | Explore codebases/patterns → extract structural knowledge |
| `todowrite/todoread` | Track tasks | **`school_progress`** | Track learning progress with visual bars → surface in dashboard |
| `opencode.session_move/rename/models` | Manage sessions | **`school_session`** | Manage learning sessions → cross-session knowledge continuity |
| `shell` | Execute commands | **`school_execute`** | Execute and learn from command outcomes → build command knowledge |
| `read/write/edit/glob/grep` | File operations | **`school_navigate`** | Navigate and learn from file structures → build project maps |
| `compress` | Context compression | (exists: S1/S2) | Already built |
| `memory` | Persistent memory | (exists: Phase 1) | Already built |
| `skill` | Load skills | (exists: Phase 1) | Already built |
| `browser.console/network` | Observe events | **`school_monitor`** | Monitor tool call streams → detect patterns and anomalies |

## 3. New tools (8)

### 3.1 `school_observe`

**Purpose**: Observe agent behavior and learn from it.
**Input**: `observation` (string), `category` (tool_call|conversation|error|pattern), `evidence` (optional JSON).
**Output**: Acknowledged observation ID, learning extracted (if any), updated profile.

**What it does**:
- Records observations about agent behavior (what tools were called, what worked, what failed).
- Extracts patterns: "you always use `school_remember` before `school_recall`", "errors cluster around file operations".
- Stores structured learnings as memories with `tags: ["observation", category]`.
- Updates the agent profile (`school_profile`) with behavioral insights.

**Inspired by**: `browser.observe` / `browser.snapshot` / `browser.console` — but observing *agent behavior* instead of web pages.

### 3.2 `school_goal`

**Purpose**: Track learning objectives and milestones.
**Input**: `action` (set|status|complete|block|pause|resume|clear|history), `goal_id`, `objective`, `success_criteria`, `max_turns`, `constraints`.
**Output**: Goal state (active|complete|blocked|paused), progress, evidence.

**What it does**:
- `set`: Create a learning goal with success criteria.
- `status`: Show current goals and progress.
- `complete`: Mark goal done with evidence.
- `block`: Mark goal blocked with a concrete external requirement.
- `history`: Show completed goals and what was learned.

**Inspired by**: `goal_set` / `goal_status` / `goal_complete` / `goal_block` / `goal_pause` / `goal_resume` / `goal_clear` / `get_goal_history` / `update_goal`.

### 3.3 `school_research`

**Purpose**: Research topics and distill learnings.
**Input**: `query` (string), `depth` (shallow|deep), `format` (summary|structured|raw).
**Output**: Research summary, key findings, extracted learnings (stored as memories).

**What it does**:
- Searches internal knowledge (memory, knowledge graph) first.
- Falls back to web search if configured.
- Distills findings into structured learnings.
- Stores as memories with `tags: ["research", topic]`.

**Inspired by**: `websearch` / `webfetch` — but focused on *learning extraction* instead of raw content.

### 3.4 `school_explore`

**Purpose**: Explore codebases and extract structural knowledge.
**Input**: `target` (path or pattern), `depth` (file|module|project), `focus` (structure|patterns|conventions).
**Output**: Structural map, patterns found, conventions detected.

**What it does**:
- Walks file trees and extracts structure (modules, dependencies, patterns).
- Identifies conventions (naming, architecture, test patterns).
- Builds a project knowledge map stored as memories.

**Inspired by**: `subagent` (explore) / `glob` / `grep` — but focused on *structural learning*.

### 3.5 `school_progress`

**Purpose**: Track learning progress with visual indicators.
**Input**: `action` (write|read), `items` (list of progress items), `context` (string).
**Output**: Current progress state, visual bars.

**What it does**:
- Tracks progress on learning tasks with status (pending|in_progress|completed).
- Renders Apple-grade progress bars.
- Integrates with `school_goal` and `school_session`.

**Inspired by**: `todowrite` / `todoread` — but focused on *learning progress*.

### 3.6 `school_session`

**Purpose**: Manage learning sessions and cross-session continuity.
**Input**: `action` (create|resume|list|summarize|export), `session_id`, `focus`.
**Output**: Session state, summary, continuity bridge.

**What it does**:
- `create`: Start a new learning session.
- `resume`: Resume a previous session with continuity context.
- `summarize`: Summarize what was learned in a session.
- `export`: Export session learnings for other agents.

**Inspired by**: `opencode.session_move` / `opencode.session_rename` / `opencode.models` — but focused on *learning continuity*.

### 3.7 `school_execute`

**Purpose**: Execute and learn from command outcomes.
**Input**: `command` (string), `learn` (boolean), `context` (string).
**Output**: Command result, learning extracted (if `learn=true`).

**What it does**:
- Executes a command (via the bridge).
- If `learn=true`, extracts learning from the outcome (success/failure pattern, error type, timing).
- Stores as memories with `tags: ["execution", outcome]`.

**Inspired by**: `shell` — but focused on *learning from execution*.

### 3.8 `school_navigate`

**Purpose**: Navigate and learn from file structures.
**Input**: `action` (read|list|search|map), `path`, `pattern`, `depth`.
**Output**: File content, directory listing, search results, project map.

**What it does**:
- `read`: Read a file and extract learning (patterns, conventions, issues).
- `list`: List directory and extract structure.
- `search`: Search for patterns and extract findings.
- `map`: Build a project map from file structure.

**Inspired by**: `read` / `glob` / `grep` — but focused on *structural learning*.

## 4. Tool surface after S7

| Surface | Count | New tools |
|---------|-------|-----------|
| TS plugin | 22 | +8 (observe, goal, research, explore, progress, session, execute, navigate) |
| MCP | 24 | +8 (same names, byte-equal descriptions) |
| CLI | 13 | +8 (same subcommands) |

Total: 22 TS / 24 MCP / 13 CLI subcommands.

## 5. Architecture

```
school/tools/agent/          # S7 core (new)
    observe.py               # school_observe
    goal.py                  # school_goal
    research.py              # school_research
    explore.py               # school_explore
    progress.py              # school_progress
    session.py               # school_session
    execute.py               # school_execute
    navigate.py              # school_navigate
    __init__.py

core/agent/                  # S7 core logic (new)
    observer.py              # Observation recorder + pattern extractor
    goals.py                 # Goal lifecycle manager
    researcher.py            # Research + learning distiller
    explorer.py              # Codebase structure analyzer
    progress.py              # Progress tracker + visual renderer
    sessions.py              # Session manager + continuity bridge
    executor.py              # Command executor + outcome learner
    navigator.py             # File navigator + structure mapper
    __init__.py
```

## 6. Integration points

- **Memory**: All learnings stored via existing `MemoryManager`.
- **Routing**: `school_route` gains `goal` and `progress` inputs.
- **Dashboard**: `school_dashboard` shows goal progress and learning stats.
- **Footer**: `school_progress` bars appear in footer chip.
- **Skills**: `school-routing` skill learns from observations.

## 7. Kill switches

| Env | Effect |
|-----|--------|
| `SCHOOL_OBSERVE=0` | No observation recording |
| `SCHOOL_GOAL=0` | No goal tracking |
| `SCHOOL_RESEARCH=0` | No research calls |
| `SCHOOL_EXPLORE=0` | No codebase exploration |
| `SCHOOL_PROGRESS=0` | No progress tracking |
| `SCHOOL_SESSION=0` | No session management |
| `SCHOOL_EXECUTE=0` | No command execution learning |
| `SCHOOL_NAVIGATE=0` | No file navigation |

## 8. Constraints (from master spec)

- Apple-grade presentation on every surface.
- Fail-open everywhere.
- No secrets in observations/learnings.
- Kill switches for every automatic behavior.
- Backward compat: existing tools stay green.
- No commits unless the user explicitly asks.

## 9. Exit criteria

- [ ] All 8 tools implemented in TS + MCP + CLI
- [ ] Parity tests: TS == MCP == CLI descriptions (byte-equal)
- [ ] Each tool has unit tests (happy path, fail-open, kill switch)
- [ ] Integration tests: tools work end-to-end
- [ ] Dashboard shows goal progress and learning stats
- [ ] Footer shows progress bars
- [ ] Full battery green
- [ ] `ruff check` clean (plugin_source.py stays at 16 E501)
- [ ] `node --check` exit 0
