"""Model-call budget for 1A-2Z: the model is a limited resource.

Deterministic filtering happens first (candidate.py); this module caps how
many judgment calls a task/session may spend. Counters persist in the
registry file so a restart does not reset the budget.
"""

from __future__ import annotations

import os
from typing import Any

from core.skillgen.types import safe_int, safe_str


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


DEFAULT_MAX_CALLS_PER_TASK = _env_int("SCHOOL_SKILLGEN_MAX_CALLS_PER_TASK", 8)


class ModelCallBudget:
    """Tracks and limits model judgment calls (persisted counters).

    Fail-open: corrupt persisted stats or hostile task keys never raise.
    """

    def __init__(
        self,
        stats: dict[str, Any],
        max_per_task: int | None = None,
    ) -> None:
        self._stats = stats if isinstance(stats, dict) else {}
        if max_per_task is not None:
            self.max_per_task = max(0, safe_int(max_per_task, DEFAULT_MAX_CALLS_PER_TASK))
        else:
            self.max_per_task = _env_int(
                "SCHOOL_SKILLGEN_MAX_CALLS_PER_TASK", DEFAULT_MAX_CALLS_PER_TASK
            )

    @property
    def calls(self) -> dict[str, int]:
        raw = self._stats.setdefault("model_calls_by_task", {})
        if not isinstance(raw, dict):
            raw = {}
            self._stats["model_calls_by_task"] = raw
        try:
            return {safe_str(k, 100): safe_int(v) for k, v in list(raw.items())[:500]}
        except Exception:  # noqa: BLE001 - hostile mapping
            return {}

    @property
    def total(self) -> int:
        return safe_int(self._stats.get("model_calls_total", 0))

    def used(self, task_key: Any) -> int:
        return self.calls.get(safe_str(task_key, 100), 0)

    def remaining(self, task_key: Any) -> int:
        return max(0, self.max_per_task - self.used(task_key))

    def allow(self, task_key: Any) -> bool:
        return self.remaining(task_key) > 0

    def record(self, task_key: Any) -> int:
        """Consume one call; returns calls used for this task after record."""
        key = safe_str(task_key, 100)
        calls = self.calls
        calls[key] = calls.get(key, 0) + 1
        # Keep the persisted map bounded (last 100 tasks by insertion order).
        if len(calls) > 100:
            for old_key in list(calls)[:-100]:
                del calls[old_key]
        self._stats["model_calls_by_task"] = calls
        self._stats["model_calls_total"] = self.total + 1
        return calls[key]

    def report(self, task_key: Any) -> dict[str, int]:
        return {
            "used": self.used(task_key),
            "max": self.max_per_task,
            "remaining": self.remaining(task_key),
            "total": self.total,
        }
