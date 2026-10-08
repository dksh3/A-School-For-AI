"""Model-call budget for 1A-2Z: the model is a limited resource.

Deterministic filtering happens first (candidate.py); this module caps how
many judgment calls a task/session may spend. Counters persist in the
registry file so a restart does not reset the budget.
"""

from __future__ import annotations

import os
from typing import Any


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


DEFAULT_MAX_CALLS_PER_TASK = _env_int("SCHOOL_SKILLGEN_MAX_CALLS_PER_TASK", 8)


class ModelCallBudget:
    """Tracks and limits model judgment calls (persisted counters)."""

    def __init__(
        self,
        stats: dict[str, Any],
        max_per_task: int | None = None,
    ) -> None:
        self._stats = stats
        self.max_per_task = (
            max_per_task
            if max_per_task is not None
            else _env_int("SCHOOL_SKILLGEN_MAX_CALLS_PER_TASK", DEFAULT_MAX_CALLS_PER_TASK)
        )

    @property
    def calls(self) -> dict[str, int]:
        raw = self._stats.setdefault("model_calls_by_task", {})
        if not isinstance(raw, dict):
            raw = {}
            self._stats["model_calls_by_task"] = raw
        return {str(k): int(v) for k, v in raw.items()}

    @property
    def total(self) -> int:
        return int(self._stats.get("model_calls_total", 0))

    def used(self, task_key: str) -> int:
        return self.calls.get(task_key, 0)

    def remaining(self, task_key: str) -> int:
        return max(0, self.max_per_task - self.used(task_key))

    def allow(self, task_key: str) -> bool:
        return self.remaining(task_key) > 0

    def record(self, task_key: str) -> int:
        """Consume one call; returns calls used for this task after record."""
        calls = self.calls
        calls[task_key] = calls.get(task_key, 0) + 1
        # Keep the persisted map bounded (last 100 tasks by insertion order).
        if len(calls) > 100:
            for key in list(calls)[:-100]:
                del calls[key]
        self._stats["model_calls_by_task"] = calls
        self._stats["model_calls_total"] = int(self._stats.get("model_calls_total", 0)) + 1
        return calls[task_key]

    def report(self, task_key: str) -> dict[str, int]:
        return {
            "used": self.used(task_key),
            "max": self.max_per_task,
            "remaining": self.remaining(task_key),
            "total": self.total,
        }
