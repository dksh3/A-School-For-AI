"""S7: school_goal — track learning objectives and milestones."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

GOAL_FILE = "goals.json"


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
        return data if isinstance(data, list) else []
    except (OSError, ValueError, TypeError):
        return []


def _save(worktree: str, goals: list[dict[str, Any]]) -> None:
    path = _goal_path(worktree)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(goals, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


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
    if os.environ.get("SCHOOL_GOAL", "") == "0":
        return GoalResult(ok=True, action=action)

    valid = {"set", "status", "complete", "block", "pause", "resume", "clear", "history"}
    if action not in valid:
        return GoalResult(ok=False, action=action, error=f"unknown action: {action}")

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
        if g.get("id") == goal_id:
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
                state=g["state"],
                objective=g.get("objective", ""),
            )

    return GoalResult(ok=False, action=action, goal_id=goal_id, error="goal not found")


__all__ = ["GoalResult", "goal"]
