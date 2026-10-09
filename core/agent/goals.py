"""S7: school_goal — track learning objectives and milestones."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.agent.observer import safe_str

GOAL_FILE = "goals.json"
ACTIONS = frozenset({"set", "status", "complete", "block", "pause", "resume", "clear", "history"})


@dataclass
class GoalResult:
    ok: bool = True
    action: str = ""
    goal_id: str = ""
    state: str = ""
    objective: str = ""
    progress: float = 0.0
    goals: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def _goal_path(worktree: str) -> Path:
    return Path(worktree) / ".school" / "agent" / GOAL_FILE


def _load(worktree: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(_goal_path(worktree).read_text(encoding="utf-8"))
        return [g for g in data if isinstance(g, dict)] if isinstance(data, list) else []
    except Exception:
        return []


def _save(worktree: str, goals: list[dict[str, Any]]) -> None:
    path = _goal_path(worktree)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(goals, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _as_int(value: Any, default: int = 0) -> int:
    """Coerce any value to int; never raises."""
    try:
        return int(value)
    except Exception:
        return default


def _apply(
    worktree: str,
    action: str,
    goal_id: str,
    objective: str,
    success_criteria: str,
    max_turns: int,
    constraints: str,
) -> GoalResult:
    goals = _load(worktree)

    if action == "set":
        gid = goal_id or f"g{len(goals) + 1}"
        entry = {
            "id": gid,
            "objective": objective,
            "success_criteria": success_criteria,
            "max_turns": max_turns,
            "constraints": constraints,
            "state": "active",
            "evidence": [],
        }
        goals.append(entry)
        _save(worktree, goals)
        return GoalResult(ok=True, action=action, goal_id=gid, state="active", objective=objective)

    if action == "status":
        return GoalResult(ok=True, action=action, goals=goals)

    if action == "history":
        done = [g for g in goals if g.get("state") in {"complete", "blocked"}]
        return GoalResult(ok=True, action=action, goals=done)

    if action == "clear":
        _save(worktree, [])
        return GoalResult(ok=True, action=action)

    for g in goals:
        if safe_str(g.get("id", "")) == goal_id:
            if action == "complete":
                g["state"] = "complete"
            elif action == "block":
                g["state"] = "blocked"
                g["blocker"] = constraints
            elif action == "pause":
                g["state"] = "paused"
            elif action == "resume":
                g["state"] = "active"
            _save(worktree, goals)
            return GoalResult(
                ok=True,
                action=action,
                goal_id=goal_id,
                state=safe_str(g.get("state", "")),
                objective=safe_str(g.get("objective", "")),
            )

    return GoalResult(ok=False, action=action, goal_id=goal_id, error="goal not found")


def goal(
    worktree: str,
    action: str,
    goal_id: str = "",
    objective: str = "",
    success_criteria: str = "",
    max_turns: int = 0,
    constraints: str = "",
) -> GoalResult:
    """Manage learning goals: set / status / complete / block / pause / resume / clear / history."""
    action_s = safe_str(action)
    goal_id_s = safe_str(goal_id)
    if os.environ.get("SCHOOL_GOAL", "") == "0":
        return GoalResult(ok=True, action=action_s)

    if action_s not in ACTIONS:
        return GoalResult(ok=False, action=action_s, error=f"unknown action: {action_s}")

    try:
        return _apply(
            worktree,
            action_s,
            goal_id_s,
            safe_str(objective),
            safe_str(success_criteria),
            _as_int(max_turns),
            safe_str(constraints),
        )
    except Exception as exc:
        return GoalResult(
            ok=False,
            action=action_s,
            goal_id=goal_id_s,
            error=safe_str(exc, 300) or type(exc).__name__,
        )


__all__ = ["GoalResult", "goal"]
