"""S7: school_workflow — SDD workflow engine with persisted state and phase timing."""

from __future__ import annotations

import contextlib
import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.agent.observer import observe, safe_str

WORKFLOW_FILE = "workflows.json"
WORKFLOW_DEFS_FILE = "workflow_defs.json"

#: Built-in SDD workflows: name -> ordered phase names.
BUILTINS: dict[str, list[str]] = {
    "tdd": ["red", "green", "refactor", "commit"],
    "debug": ["reproduce", "isolate", "fix", "verify"],
    "brainstorm": ["diverge", "evaluate", "select", "plan"],
    "review": ["read", "analyze", "report", "fix"],
}

#: Per-phase guidance. Unknown (custom) phases get generic guidance.
GUIDANCE: dict[str, str] = {
    "red": (
        "Write ONE failing test that captures the desired behaviour; "
        "run it and watch it fail for the right reason."
    ),
    "green": (
        "Make the test pass with the simplest implementation that works; "
        "no premature optimisation."
    ),
    "refactor": "Clean up names and duplication while keeping every test green.",
    "commit": "Commit with a message that references the test guarding the change.",
    "reproduce": "Reproduce the bug with a minimal failing case before changing code.",
    "isolate": "Narrow the root cause: bisect, instrument, or shrink the input.",
    "fix": "Fix the root cause, not the symptom; keep a test that guards the fix.",
    "verify": "Run the reproducer and the full suite to prove there is no regression.",
    "diverge": "Generate as many candidate ideas as possible; defer judgement.",
    "evaluate": "Score every candidate on impact, effort and risk.",
    "select": "Pick the single best candidate and record why the others lost.",
    "plan": "Break the winner into concrete steps with a clear definition of done.",
    "read": "Read the diff end-to-end before forming opinions; understand intent.",
    "analyze": "Hunt for correctness, clarity, missing tests and edge cases.",
    "report": "Report findings ordered by severity with file and line references.",
}

VALID_ACTIONS = frozenset(
    {"start", "advance", "status", "abort", "list", "define", "block"}
)

#: Process-level custom workflows (worktree-persisted defs live in the defs file).
_CUSTOM: dict[str, list[str]] = {}


@dataclass
class WorkflowResult:
    ok: bool
    workflow: str
    phase: str
    phases: list[dict[str, Any]]
    guidance: str
    state: str
    error: str | None = None


def register_workflow(name: str, phases: list[str]) -> bool:
    """Register a custom workflow for this process. Returns False if invalid."""
    if not isinstance(name, str) or not name.strip():
        return False
    try:
        cleaned = [p.strip() for p in phases if isinstance(p, str) and p.strip()]
    except Exception:
        return False
    if not cleaned:
        return False
    _CUSTOM[name] = cleaned
    return True


# ---------------------------------------------------------------------------
# persistence helpers
# ---------------------------------------------------------------------------


def _state_path(worktree: Path) -> Path:
    return worktree / ".school" / "agent" / WORKFLOW_FILE


def _defs_path(worktree: Path) -> Path:
    return worktree / ".school" / "agent" / WORKFLOW_DEFS_FILE


def _load_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError, TypeError):
        return dict(fallback)
    return data if isinstance(data, dict) else dict(fallback)


def _save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _new_key(name: str, state: dict[str, Any]) -> str:
    stamp = _now_iso()
    key = f"{name}@{stamp}"
    n = 2
    while key in state:
        key = f"{name}@{stamp}#{n}"
        n += 1
    return key


def _record(worktree: Path, message: str) -> None:
    """Feed the observer learning trail; never allowed to raise."""
    with contextlib.suppress(Exception):
        observe(str(worktree), message, category="workflow")


# ---------------------------------------------------------------------------
# workflow registry
# ---------------------------------------------------------------------------


def _definitions(worktree: Path) -> dict[str, list[str]]:
    raw = _load_json(_defs_path(worktree), {})
    out: dict[str, list[str]] = {}
    for name, phases in raw.items():
        if isinstance(name, str) and isinstance(phases, list):
            cleaned = [str(p) for p in phases if str(p).strip()]
            if cleaned:
                out[name] = cleaned
    return out


def _workflows(worktree: Path) -> dict[str, list[str]]:
    merged = dict(_definitions(worktree))
    merged.update(_CUSTOM)
    merged.update(BUILTINS)
    return merged


def _names(worktree: Path) -> list[str]:
    extra = sorted(n for n in _workflows(worktree) if n not in BUILTINS)
    return [*BUILTINS, *extra]


# ---------------------------------------------------------------------------
# run lookup helpers
# ---------------------------------------------------------------------------


def _runs_for(state: dict[str, Any], name: str) -> list[tuple[str, dict[str, Any]]]:
    items = [
        (key, val)
        for key, val in state.items()
        if isinstance(val, dict) and val.get("name") == name
    ]
    items.sort(key=lambda kv: str(kv[1].get("started_at", "")))
    return items


def _latest(state: dict[str, Any], name: str) -> dict[str, Any] | None:
    runs = _runs_for(state, name)
    return runs[-1][1] if runs else None


def _latest_active(state: dict[str, Any], name: str) -> dict[str, Any] | None:
    for _key, entry in reversed(_runs_for(state, name)):
        if entry.get("state") in {"running", "blocked"}:
            return entry
    return None


def _phase_list(entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Phases of a run entry, keeping only dict-shaped phase records."""
    raw = entry.get("phases", [])
    if not isinstance(raw, list):
        return []
    return [p for p in raw if isinstance(p, dict)]


def _as_int(value: Any, default: int = 0) -> int:
    """Coerce any value to int; never raises."""
    try:
        return int(value)
    except Exception:
        return default


def _current_index(entry: dict[str, Any]) -> int:
    phases = _phase_list(entry)
    for i, phase in enumerate(phases):
        if phase.get("status") == "active":
            return i
    for i, phase in enumerate(phases):
        if phase.get("status") != "done":
            return i
    return len(phases)


def _completed(entry: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for phase in _phase_list(entry):
        if phase.get("status") != "done":
            continue
        out.append(
            {
                "name": safe_str(phase.get("name", "")),
                "duration_ms": _as_int(phase.get("duration_ms", 0)),
                "status": "done",
            }
        )
    return out


def _elapsed_ms(entry: dict[str, Any]) -> int:
    started = entry.get("phase_started_at")
    if isinstance(started, (int, float)):
        return max(0, int((time.time() - float(started)) * 1000))
    return 0


def _phase_guidance(workflow_name: str, phase: str) -> str:
    if phase in GUIDANCE:
        return GUIDANCE[phase]
    return f"Work the '{phase}' phase of '{workflow_name}', then advance."


def _history_note(state: dict[str, Any], name: str, skip_key: str) -> str:
    """Learning from outcomes: summarize finished runs of this workflow."""
    counts: dict[str, int] = {}
    for key, entry in _runs_for(state, name):
        if key == skip_key:
            continue
        run_state = str(entry.get("state", ""))
        if run_state in {"complete", "aborted", "blocked"}:
            counts[run_state] = counts.get(run_state, 0) + 1
    if not counts:
        return ""
    parts = [f"{counts[s]} {s}" for s in sorted(counts)]
    return f" [run history: {', '.join(parts)}]"


def _err(name: str, message: str) -> WorkflowResult:
    return WorkflowResult(
        ok=False,
        workflow=name,
        phase="",
        phases=[],
        guidance="",
        state="error",
        error=message,
    )


# ---------------------------------------------------------------------------
# actions
# ---------------------------------------------------------------------------


def _do_start(
    worktree: Path,
    state: dict[str, Any],
    name: str,
    phases: list[str],
    phase: str | None,
) -> WorkflowResult:
    idx = phases.index(phase) if phase in phases else 0
    entries = [
        {
            "name": p,
            "status": "active" if i == idx else "pending",
            "duration_ms": 0,
            "notes": "",
        }
        for i, p in enumerate(phases)
    ]
    key = _new_key(name, state)
    state[key] = {
        "name": name,
        "key": key,
        "phases": entries,
        "current_phase": phases[idx],
        "state": "running",
        "started_at": _now_iso(),
        "finished_at": "",
        "phase_started_at": time.time(),
    }
    _save_json(_state_path(worktree), state)
    _record(worktree, f"workflow started: {name}")
    guidance = _phase_guidance(name, phases[idx]) + _history_note(state, name, key)
    return WorkflowResult(
        ok=True,
        workflow=name,
        phase=phases[idx],
        phases=[],
        guidance=guidance,
        state="running",
    )


def _do_advance(
    worktree: Path,
    state: dict[str, Any],
    name: str,
    notes: str | None,
) -> WorkflowResult:
    entry = _latest_active(state, name)
    if entry is None:
        latest = _latest(state, name)
        if latest is not None and latest.get("state") == "complete":
            return _err(name, "workflow already complete")
        if latest is not None and latest.get("state") == "aborted":
            return _err(name, "workflow already aborted")
        return _err(name, f"workflow not started: {name}")

    phases: list[dict[str, Any]] = _phase_list(entry)
    idx = _current_index(entry)
    if idx >= len(phases):
        entry["state"] = "complete"
        entry["finished_at"] = entry.get("finished_at") or _now_iso()
        _save_json(_state_path(worktree), state)
        return _err(name, "workflow already complete")

    done = phases[idx]
    done["status"] = "done"
    done["duration_ms"] = _elapsed_ms(entry)
    if notes:
        done["notes"] = str(notes)[:500]
    completed = _completed(entry)

    if idx + 1 < len(phases):
        nxt = phases[idx + 1]
        nxt["status"] = "active"
        entry["current_phase"] = nxt["name"]
        entry["state"] = "running"
        entry["phase_started_at"] = time.time()
        _save_json(_state_path(worktree), state)
        _record(worktree, f"workflow phase done: {name}:{done['name']}")
        return WorkflowResult(
            ok=True,
            workflow=name,
            phase=str(nxt["name"]),
            phases=completed,
            guidance=_phase_guidance(name, str(nxt["name"])),
            state="running",
        )

    entry["current_phase"] = ""
    entry["state"] = "complete"
    entry["finished_at"] = _now_iso()
    _save_json(_state_path(worktree), state)
    total_ms = sum(_as_int(p.get("duration_ms", 0)) for p in phases)
    _record(worktree, f"workflow complete: {name} in {total_ms}ms")
    guidance = f"workflow '{name}' complete in {total_ms}ms — record the outcome."
    return WorkflowResult(
        ok=True,
        workflow=name,
        phase="",
        phases=completed,
        guidance=guidance,
        state="complete",
    )


def _do_stop(
    worktree: Path,
    state: dict[str, Any],
    name: str,
    stop_state: str,
) -> WorkflowResult:
    entry = _latest_active(state, name)
    if entry is None:
        latest = _latest(state, name)
        if latest is not None:
            return _err(name, f"workflow already {latest.get('state', 'stopped')}")
        return _err(name, f"workflow not started: {name}")
    entry["state"] = stop_state
    entry["finished_at"] = _now_iso()
    _save_json(_state_path(worktree), state)
    _record(worktree, f"workflow {stop_state}: {name}")
    verb = "aborted" if stop_state == "aborted" else "blocked"
    guidance = f"workflow '{name}' {verb}"
    if stop_state == "blocked":
        guidance += " — resolve the blocker, then advance to resume."
    return WorkflowResult(
        ok=True,
        workflow=name,
        phase=str(entry.get("current_phase", "")),
        phases=_completed(entry),
        guidance=guidance,
        state=stop_state,
    )


def _do_status(state: dict[str, Any], name: str) -> WorkflowResult:
    entry = _latest(state, name)
    if entry is None:
        return WorkflowResult(
            ok=True,
            workflow=name,
            phase="",
            phases=[],
            guidance=f"no runs recorded for '{name}'",
            state="idle",
        )
    completed = _completed(entry)
    total = len(_phase_list(entry))
    current = str(entry.get("current_phase", ""))
    state_str = str(entry.get("state", "idle"))
    shown = current or "-"
    guidance = f"'{name}' is {state_str}: phase {shown} ({len(completed)}/{total} done)"
    return WorkflowResult(
        ok=True,
        workflow=name,
        phase=current,
        phases=completed,
        guidance=guidance,
        state=state_str,
    )


def _do_list(worktree: Path, name: str) -> WorkflowResult:
    names = _names(worktree)
    return WorkflowResult(
        ok=True,
        workflow=name,
        phase="",
        phases=[{"name": n, "status": "available", "duration_ms": 0} for n in names],
        guidance="available workflows: " + ", ".join(names),
        state="idle",
    )


def _do_define(
    worktree: Path,
    name: str,
    phase: str | None,
) -> WorkflowResult:
    phases = [p.strip() for p in (phase or "").split(",") if p.strip()]
    if not name.strip():
        return _err(name, "workflow name required")
    if not phases:
        return _err(name, "define requires phases (comma-separated in phase)")
    defs = _definitions(worktree)
    defs[name] = phases
    _save_json(_defs_path(worktree), defs)
    guidance = f"custom workflow '{name}' defined: {' -> '.join(phases)}"
    return WorkflowResult(
        ok=True,
        workflow=name,
        phase="",
        phases=[{"name": p, "status": "pending", "duration_ms": 0} for p in phases],
        guidance=guidance,
        state="defined",
    )


def _dispatch(
    worktree: Path,
    name: str,
    action: str,
    phase: str | None,
    notes: str | None,
) -> WorkflowResult:
    if action not in VALID_ACTIONS:
        return _err(name, f"unknown action: {action}")
    if action == "list":
        return _do_list(worktree, name)
    if action == "define":
        return _do_define(worktree, name, phase)

    phases = _workflows(worktree).get(name)
    if phases is None:
        return _err(name, f"unknown workflow: {name}")

    state = _load_json(_state_path(worktree), {})
    if action == "start":
        return _do_start(worktree, state, name, phases, phase)
    if action == "advance":
        return _do_advance(worktree, state, name, notes)
    if action == "abort":
        return _do_stop(worktree, state, name, "aborted")
    if action == "block":
        return _do_stop(worktree, state, name, "blocked")
    return _do_status(state, name)


def workflow(
    worktree: Path | str,
    name: str,
    action: str = "start",
    phase: str | None = None,
    notes: str | None = None,
) -> WorkflowResult:
    """Run an SDD workflow: start / advance / status / abort / list / define / block.

    State persists in ``.school/agent/workflows.json`` so runs survive across
    calls and processes. Phase durations are recorded on every advance and
    finished runs feed the guidance of future runs ("run history").
    """
    if os.environ.get("SCHOOL_WORKFLOW", "") == "0":
        return WorkflowResult(
            ok=True,
            workflow=safe_str(name),
            phase="",
            phases=[],
            guidance="workflow disabled",
            state="disabled",
        )
    name_s = safe_str(name)
    action_s = safe_str(action)
    phase_s = None if phase is None else safe_str(phase)
    notes_s = None if notes is None else safe_str(notes)
    try:
        return _dispatch(Path(worktree), name_s, action_s, phase_s, notes_s)
    except Exception as exc:
        return _err(name_s, safe_str(exc, 300) or type(exc).__name__)


__all__ = ["BUILTINS", "WorkflowResult", "register_workflow", "workflow"]
