"""S7: school_progress — track learning progress with visual bars."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from core.agent.observer import safe_str
from core.context.progress import render_bar


@dataclass
class ProgressResult:
    ok: bool = True
    action: str = ""
    items: list[dict[str, Any]] = field(default_factory=list)
    bars: str = ""
    error: str = ""


_STORE: dict[str, list[dict[str, Any]]] = {}
_KEY_LIMIT = 200


def _norm_item(item: Any) -> dict[str, str]:
    """Coerce one progress item into a str->str dict; never raises."""
    if isinstance(item, dict):
        try:
            pairs = list(item.items())
        except Exception:
            pairs = []
        return {safe_str(k, 100): safe_str(v) for k, v in pairs}
    return {"content": safe_str(item), "status": ""}


def _norm_items(items: Any) -> list[dict[str, Any]]:
    """Coerce a hostile-or-valid items payload into a list of safe dicts."""
    if items is None:
        return []
    if isinstance(items, dict):
        return [_norm_item(items)]
    try:
        raw = list(items)
    except Exception:
        raw = [items]
    return [_norm_item(i) for i in raw]


def _ratio(item: dict[str, Any]) -> float:
    s = item.get("status", "") if isinstance(item, dict) else ""
    return 1.0 if s == "completed" else 0.5 if s == "in_progress" else 0.0


def _bars(items: list[dict[str, Any]]) -> str:
    return "\n".join(
        render_bar(_ratio(i), label=safe_str(i.get("content", ""))[:30])
        for i in items
    )


def progress(
    worktree: str,
    action: str,
    items: list[dict[str, Any]] | None = None,
    context: str = "",
) -> ProgressResult:
    """Track learning progress: write / read / render bars."""
    action_s = safe_str(action)
    if os.environ.get("SCHOOL_PROGRESS", "") == "0":
        return ProgressResult(ok=True, action=action_s)

    key = safe_str(worktree, _KEY_LIMIT)
    try:
        if action_s == "write":
            stored = _norm_items(items)
            _STORE[key] = stored
            return ProgressResult(ok=True, action=action_s, items=stored, bars=_bars(stored))
        if action_s == "read":
            stored = _STORE.get(key, [])
            return ProgressResult(ok=True, action=action_s, items=stored, bars=_bars(stored))
    except Exception as exc:
        return ProgressResult(
            ok=False, action=action_s, error=safe_str(exc, 300) or type(exc).__name__
        )
    return ProgressResult(ok=False, action=action_s, error=f"unknown action: {action_s}")


__all__ = ["ProgressResult", "progress"]
