"""S7: school_progress — track learning progress with visual bars."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from core.context.progress import render_bar


@dataclass
class ProgressResult:
    ok: bool = True
    action: str = ""
    items: list[dict[str, Any]] = field(default_factory=list)
    bars: str = ""
    error: str = ""


_STORE: dict[str, list[dict[str, Any]]] = {}


def _ratio(item: dict[str, Any]) -> float:
    s = item.get("status", "")
    return 1.0 if s == "completed" else 0.5 if s == "in_progress" else 0.0


def progress(
    worktree: str,
    action: str,
    items: list[dict[str, Any]] | None = None,
    context: str = "",
) -> ProgressResult:
    """Track learning progress: write / read / render bars."""
    if os.environ.get("SCHOOL_PROGRESS", "") == "0":
        return ProgressResult(ok=True, action=action)

    if action == "write":
        _STORE[worktree] = items or []
        bars = "\n".join(
            render_bar(
                _ratio(i),
                label=str(i.get("content", ""))[:30],
            )
            for i in (items or [])
        )
        return ProgressResult(ok=True, action=action, items=items or [], bars=bars)

    if action == "read":
        stored = _STORE.get(worktree, [])
        bars = "\n".join(
            render_bar(
                _ratio(i),
                label=str(i.get("content", ""))[:30],
            )
            for i in stored
        )
        return ProgressResult(ok=True, action=action, items=stored, bars=bars)

    return ProgressResult(ok=False, action=action, error=f"unknown action: {action}")


__all__ = ["ProgressResult", "progress"]
