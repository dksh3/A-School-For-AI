"""School MCP distribution — fail-open tool registry.

Self-contained: exposes all 48 ``school_*`` tools. Each tool is dispatched
FAIL-OPEN — ``call_tool`` *never* raises and always returns a valid dict.

Tools route to the hardened ``school.bridge`` where a wire command exists
(43 of 48); the 5 surface-native tools (read/grep/dashboard/route/route_stats)
are handled here directly, also fail-open.

No ``mcp`` SDK dependency at import time — the registry + dispatch are pure
Python and fully testable without the SDK.
"""

from __future__ import annotations

from typing import Any


def _str(desc: str = "") -> dict:
    d: dict[str, Any] = {"type": "string"}
    if desc:
        d["description"] = desc
    return d


def _num(desc: str = "", integer: bool = False) -> dict:
    d: dict[str, Any] = {"type": "integer" if integer else "number"}
    if desc:
        d["description"] = desc
    return d


def _bool(desc: str = "") -> dict:
    d: dict[str, Any] = {"type": "boolean"}
    if desc:
        d["description"] = desc
    return d


def _arr(desc: str = "") -> dict:
    d: dict[str, Any] = {"type": "array", "items": {"type": "string"}}
    if desc:
        d["description"] = desc
    return d


def _schema(props: dict, required: list | None = None) -> dict:
    out: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        out["required"] = required
    return out


def _worktree() -> dict:
    return {"worktree": _str("Working directory (project root).")}


def _mk(
    name: str,
    cat: str,
    desc: str,
    bridge: str | None,
    extra: dict | None = None,
    req: list | None = None,
) -> tuple:
    """Build a catalog row: schema = worktree + extra props."""
    props = {**_worktree(), **(extra or {})}
    return (name, cat, desc, bridge, _schema(props, req))


# --- catalog: (name, category, description, bridge_cmd | None, schema) -----

CATALOG: list[tuple] = [
    # Memory & Learning
    _mk("school_remember", "memory",
        "Store an experience or memory; returns the stored memory ID. Use "
        "for durable facts (decision, fix, preference, outcome).",
        "remember",
        {"content": _str("Fact or experience to store."),
         "outcome": _str("Outcome type."),
         "tags": _arr("Tags."),
         "confidence": _num("0-1 confidence.")},
        ["content"]),
    _mk("school_recall", "memory",
        "Retrieve memories scoped to project/session. One short query first "
        "— the cheapest way to load prior context.",
        "recall",
        {"query": _str("Short recall query."),
         "limit": _num("Max results.", True)},
        ["query"]),
    _mk("school_learn", "memory",
        "Record a learning with an outcome; returns the stored memory ID. "
        "Prefer for lessons with an outcome.",
        "learn",
        {"content": _str("Lesson learned."),
         "outcome": _str("What happened.")},
        ["content"]),
    _mk("school_search", "memory",
        "Semantic TF-IDF search across stored memories, ranked. Use when "
        "recall misses or for broad exploration.",
        "search",
        {"query": _str("Search query."),
         "limit": _num("Max results.", True)},
        ["query"]),
    _mk("school_conflict", "memory",
        "Detect conflicts between incoming content and stored memories, "
        "with similarity scores. Use BEFORE saving contradictory info.",
        "conflict",
        {"content": _str("Incoming content."),
         "limit": _num("Max conflicts.", True)},
        ["content"]),
    _mk("school_confidence", "memory",
        "Score how well-supported a claim or memory is (0-1 score, band, "
        "factors). Low score means verify before relying.",
        "confidence",
        {"claim": _str("Claim to score."),
         "similarity": _num("Similarity input.")},
        ["claim"]),
    _mk("school_deduplicate", "memory",
        "Find (and optionally merge) duplicate or near-duplicate memories, "
        "with similarity scores.",
        "deduplicate",
        {"merge": _bool("Merge duplicates."),
         "limit": _num("Max results.", True)}),
    _mk("school_knowledge", "memory",
        "Extract recurring learnings and knowledge patterns from "
        "consolidated memories.",
        "knowledge",
        {"agent_id": _str("Agent scope.")}),
    _mk("school_lifecycle", "memory",
        "Manage memory lifecycle: score, decay, promote, or archive. "
        "Maintenance only.",
        "lifecycle",
        {"action": _str("score|decay|promote|archive."),
         "memory_id": _str("Target memory."),
         "amount": _num("Amount.")},
        ["action"]),
    # Skills 1A-2Z
    _mk("school_skill_list", "skills",
        "List skills in the 1A-2Z registry with state, scope, confidence, "
        "and counters.",
        "skill_list",
        {"state": _str("Filter by state."),
         "scope": _str("Filter by scope."),
         "limit": _num("Max results.", True)}),
    _mk("school_skill_search", "skills",
        "Find reusable skills for a task query with scope-aware ranked "
        "matches. Use before solving a problem.",
        "skill_search",
        {"query": _str("Task query."),
         "limit": _num("Max results.", True)},
        ["query"]),
    _mk("school_skill_create", "skills",
        "Save a validated agent-authored skill: duplicate-checked, "
        "security-validated, self-tested before activation.",
        "skill_create",
        {"name": _str("Skill name."),
         "content": _str("SKILL.md content."),
         "description": _str("What it does.")},
        ["name", "content"]),
    _mk("school_skill_use", "skills",
        "Retrieve one skill by name (or search by query) and record the "
        "reuse. Returns scope-checked SKILL.md content.",
        "skill_use",
        {"name": _str("Skill name."),
         "query": _str("Or search query.")}),
    _mk("school_skill_feedback", "skills",
        "Report whether reusing a skill succeeded or failed, updating "
        "confidence and lifecycle.",
        "skill_feedback",
        {"name": _str("Skill name."),
         "success": _bool("Did it work?")},
        ["name", "success"]),
    _mk("school_skill_status", "skills",
        "1A-2Z counters: skills by state, model calls vs budget, recent "
        "events, registry health.",
        "skill_status"),
    _mk("school_skill_evolve", "skills",
        "Consolidate duplicate skills, revise a skill's fields with "
        "versioning, or recompute lifecycle states.",
        "skill_evolve",
        {"action": _str("consolidate|revise|recompute."),
         "name": _str("Skill name.")},
        ["action"]),
    _mk("school_skill_search_github", "skills",
        "Bounded GitHub repository searches for a capability gap; returns "
        "candidate skill sources. Read-only; network required.",
        "skill_search_github",
        {"capability_gap": _str("What capability is missing."),
         "task": _str("Current task.")}),
    _mk("school_skill_discover", "skills",
        "Scan GitHub search results for skill-like files with deterministic "
        "filtering and security classification. Never downloads repos.",
        "skill_discover",
        {"results": _str("Search results JSON.")}),
    _mk("school_skill_analyze_external", "skills",
        "Budgeted model analysis on one GitHub candidate: relevance, "
        "quality, security, local duplication. Read-only, fail-closed.",
        "skill_analyze_external",
        {"candidate": _str("Candidate JSON.")},
        ["candidate"]),
    _mk("school_skill_compare", "skills",
        "Compare a GitHub candidate against local skills for duplicates or "
        "improvement. Read-only.",
        "skill_compare",
        {"candidate": _str("Candidate JSON.")},
        ["candidate"]),
    _mk("school_skill_import", "skills",
        "Import an approved GitHub candidate into the local registry after "
        "user review. Requires approve=true.",
        "skill_import",
        {"candidate": _str("Candidate JSON."),
         "approve": _bool("Must be true to import.")},
        ["candidate", "approve"]),
    # Agent Suite S7
    _mk("school_observe", "agent",
        "Record an agent-behaviour observation and extract a pattern. "
        "Fail-open on errors.",
        "observe",
        {"observation": _str("What happened."),
         "category": _str("tool_call|error|pattern|research|execute."),
         "evidence": _str("Evidence.")},
        ["observation"]),
    _mk("school_goal", "agent",
        "Manage learning goals: set/status/complete/block/pause/resume/"
        "clear/history.",
        "goal",
        {"action": _str("Action."),
         "goal_id": _str("Goal ID."),
         "objective": _str("Objective."),
         "success_criteria": _str("Success criteria.")},
        ["action"]),
    _mk("school_research", "agent",
        "Research a query against internal knowledge first, then distill "
        "learnings. Fail-open.",
        "research",
        {"query": _str("Research query."),
         "depth": _str("quick|standard|deep."),
         "fmt": _str("summary|detailed|raw.")},
        ["query"]),
    _mk("school_explore", "agent",
        "Explore a codebase/path and extract structure, patterns, and "
        "conventions.",
        "explore",
        {"target": _str("Path to explore."),
         "depth": _num("Depth.", True),
         "focus": _str("Focus filter.")},
        ["target"]),
    _mk("school_progress", "agent",
        "Track learning progress with visual bars. Actions: write (set "
        "items), read (get bars + items).",
        "progress",
        {"action": _str("write|read."),
         "items": _arr("Progress items.")},
        ["action"]),
    _mk("school_session", "agent",
        "Manage session lifecycle: create/resume/summarize/export/list.",
        "session",
        {"action": _str("create|resume|summarize|export|list."),
         "session_id": _str("Session ID.")},
        ["action"]),
    _mk("school_execute", "agent",
        "Run a shell command and learn from its outcome. Set learn=false to "
        "skip learning.",
        "execute",
        {"cmd": _str("Command to run."),
         "learn": _bool("Learn from outcome."),
         "timeout_ms": _num("Timeout ms.", True),
         "cwd": _str("Working dir.")},
        ["cmd"]),
    _mk("school_navigate", "agent",
        "Read, list, search, or map project files. Actions: "
        "read|list|search|map.",
        "navigate",
        {"action": _str("read|list|search|map."),
         "path": _str("Path."),
         "pattern": _str("Search pattern.")},
        ["action"]),
    # Forge Suite
    _mk("school_clarion", "forge",
        "Run an adaptive Discovery Interview: scored dimensions, branching "
        "followups, every choice has a 'your own' option.",
        "clarion",
        {"title": _str("What you want to build."),
         "domain": _str("coding|writing|research|business|...|general."),
         "mode": _str("interview|batch|auto|import.")},
        ["title"]),
    _mk("school_blueprint", "forge",
        "Build the design spec (goal, non-goals, constraints, success "
        "metrics, decomposition) from a clarion interview.",
        "blueprint",
        {"title": _str("Spec title."),
         "interview": _str("Interview JSON (optional).")},
        ["title"]),
    _mk("school_edict", "forge",
        "Build ordered commands + always/never directives from the "
        "interview.",
        "edict",
        {"title": _str("Title."),
         "interview": _str("Interview JSON.")},
        ["title"]),
    _mk("school_weave", "forge",
        "Build formations: phases, dependency graph, parallel lanes, "
        "critical path.",
        "weave",
        {"title": _str("Title."),
         "interview": _str("Interview JSON.")},
        ["title"]),
    _mk("school_compass", "forge",
        "Build acceptance criteria: Given/When/Then scenarios, checklist, "
        "success metrics.",
        "compass",
        {"title": _str("Title."),
         "interview": _str("Interview JSON.")},
        ["title"]),
    _mk("school_brainstorm", "forge",
        "Multi-technique divergent→convergent brainstorming (9 techniques), "
        "scored and clustered. 10x the superpowers brainstorm.",
        "prism",
        {"topic": _str("Topic to brainstorm."),
         "domain": _str("Domain."),
         "count": _num("Target idea count.", True)},
        ["topic"]),
    # Context Engine
    _mk("school_context_status", "context",
        "Report the context engine: blocks stored, restores, tokens saved, "
        "view mode, chip one-liner.",
        "context_status"),
    _mk("school_context_compress", "context",
        "Compress session messages through the context engine, returning "
        "blocks added and tokens saved.",
        "context_compress",
        {"messages": _str("Messages JSON.")}),
    _mk("school_context_restore", "context",
        "Restore compressed blocks by block_id (empty id restores all) — "
        "idempotent.",
        "context_restore",
        {"block_id": _str("Block ID (empty = all).")},
        ["block_id"]),
    _mk("school_read", "context",
        "Read a file with the Context Optimizer: small files raw, oversized "
        "skeletonized with a token footer.",
        None,
        {"path": _str("File path."),
         "offset": _num("Start offset.", True),
         "limit": _num("Line limit.", True)},
        ["path"]),
    _mk("school_grep", "context",
        "Search files for a regular expression, returning path:line:content "
        "matches with a token footer.",
        None,
        {"pattern": _str("Regex pattern."),
         "path": _str("Search root.")},
        ["pattern"]),
    # Routing & Ops
    _mk("school_status", "ops",
        "Check School runtime status: versions and component health. Start "
        "here before deeper diagnostics.",
        "status"),
    _mk("school_dashboard", "ops",
        "One-glance dashboard: routing decision, next tools/skill, context "
        "savings, learner recall. Call once per prompt.",
        None),
    _mk("school_route", "ops",
        "Assess how much routing machinery a situation needs (assess) or "
        "store a routing lesson (report). For anything, not only coding.",
        None,
        {"mode": _str("assess|report."),
         "situation": _str("Situation."),
         "severity": _str("Severity level."),
         "lesson": _str("Lesson."),
         "outcome": _str("Outcome.")}),
    _mk("school_route_stats", "ops",
        "Aggregated routing evidence: per-tool call counts, durations, "
        "recent entries, knobs, recent routing lessons.",
        None,
        {"limit": _num("Max entries.", True)}),
    _mk("school_diagnose", "ops",
        "Full system diagnostics: health, stats, pipeline. Deeper than "
        "status, heavier to run.",
        "diagnose"),
    # Extras
    _mk("school_visualize", "visual",
        "Render any of 101 visual types (sparkline, heatmap, donut, "
        "dashboard, timeline, ...) as text art.",
        "visualize",
        {"viz_type": _str("Visual type."),
         "data": _str("Data JSON."),
         "label": _str("Label.")},
        ["viz_type"]),
    _mk("school_workflow", "workflow",
        "Run SDD workflows (tdd/debug/brainstorm/review) with phase timing "
        "and run-history learning.",
        "workflow",
        {"name": _str("Workflow name."),
         "action": _str("start|advance|status|abort|list|define|block."),
         "phase": _str("Phase."),
         "notes": _str("Notes.")},
        ["name", "action"]),
    _mk("school_docs", "docs",
        "Fetch library/framework docs with version pinning, caching, and "
        "skeletonization.",
        "docs",
        {"query": _str("Doc query."),
         "library": _str("Library name."),
         "version": _str("Version."),
         "use_cache": _bool("Use cache.")},
        ["query"]),
]


def _build_registry() -> dict:
    reg: dict[str, dict] = {}
    for name, cat, desc, bridge, schema in CATALOG:
        reg[name] = {
            "name": name,
            "category": cat,
            "description": desc,
            "bridge": bridge,
            "schema": schema,
        }
    return reg


TOOLS: dict[str, dict] = _build_registry()
TOOL_NAMES: list[str] = sorted(TOOLS)


def _safe_str(v: Any, default: str = "") -> str:
    try:
        return default if v is None else str(v)
    except Exception:  # noqa: BLE001
        return default


def _call_bridge(cmd: str, args: dict, worktree: str | None) -> dict:
    """Invoke the hardened ``school.bridge`` handler. Always returns a dict."""
    try:
        import school.bridge as bridge

        req = dict(args) if isinstance(args, dict) else {}
        req["command"] = cmd
        if worktree and not req.get("worktree"):
            req["worktree"] = worktree
        handler = getattr(bridge, "_COMMANDS", {}).get(cmd)
        if handler is None:
            return {"ok": False, "error": f"no bridge handler for {cmd}"}
        result = handler(req)
        return result if isinstance(result, dict) else {"ok": True, "result": result}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": _safe_str(exc, "bridge error")[:200]}


def _read_file(path: str, offset: int | None, limit: int | None) -> dict:
    try:
        from pathlib import Path

        text = Path(path).read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        start = max(0, int(offset or 0))
        end = len(lines) if limit in (None, 0) else start + int(limit)
        chunk = "\n".join(lines[start:end])
        return {
            "ok": True, "output": chunk,
            "lines": len(lines), "truncated": end < len(lines),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": _safe_str(exc, "read error")[:200]}


def _grep(pattern: str, path: str) -> dict:
    try:
        import re
        from pathlib import Path

        rx = re.compile(pattern)
        root = Path(path or ".")
        matches: list[str] = []
        for f in root.rglob("*"):
            if not f.is_file():
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    matches.append(f"{f}:{i}:{line.strip()}")
                    if len(matches) >= 200:
                        return {"ok": True, "matches": matches, "truncated": True}
        return {"ok": True, "matches": matches, "truncated": False}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": _safe_str(exc, "grep error")[:200]}


def _call_self(name: str, args: dict, worktree: str | None) -> dict:
    """Handle the 5 surface-native tools, fail-open."""
    try:
        if name == "school_read":
            return _read_file(
                _safe_str(args.get("path")), args.get("offset"), args.get("limit")
            )
        if name == "school_grep":
            root = _safe_str(args.get("path") or worktree or ".")
            return _grep(_safe_str(args.get("pattern")), root)
        cmd = {
            "school_dashboard": "dashboard",
            "school_route": "route",
            "school_route_stats": "route_stats",
        }[name]
        return _call_bridge(cmd, args, worktree)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": _safe_str(exc, "handler error")[:200]}


def call_tool(name: str, args: Any = None, worktree: str | None = None) -> dict:
    """Dispatch any of the 48 tools. FAIL-OPEN: never raises, always a dict."""
    try:
        meta = TOOLS.get(_safe_str(name))
        if meta is None:
            return {"ok": False, "error": f"unknown tool: {_safe_str(name, '?')[:60]}"}
        a = args if isinstance(args, dict) else {}
        if meta["bridge"]:
            return _call_bridge(meta["bridge"], a, worktree)
        return _call_self(name, a, worktree)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": _safe_str(exc, "dispatch error")[:200]}


def describe(name: str) -> dict:
    """Return {name, category, description, schema} for a tool, fail-open."""
    meta = TOOLS.get(_safe_str(name))
    if not meta:
        return {"name": _safe_str(name), "error": "unknown tool"}
    return {
        "name": meta["name"],
        "category": meta["category"],
        "description": meta["description"],
        "schema": meta["schema"],
    }
