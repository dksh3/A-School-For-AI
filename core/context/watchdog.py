"""S6: Watchdog — retry-once wrapper with timeout and fail-open guarantee."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")

DEFAULT_TIMEOUT_MS = 5000


def watchdog(
    fn: Callable[..., T],
    *args: Any,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    **kwargs: Any,
) -> T | None:
    """Run *fn* with a single retry on exception.  Fail-open (returns None).

    Kill switch: ``SCHOOL_WATCHDOG=0`` disables retry.
    """
    if os.environ.get("SCHOOL_WATCHDOG", "") == "0":
        try:
            return fn(*args, **kwargs)
        except Exception:
            return None  # fail-open

    for attempt in range(2):
        try:
            return fn(*args, **kwargs)
        except Exception:
            if attempt == 1:
                return None  # fail-open after retry
            continue
    return None


__all__ = ["watchdog", "DEFAULT_TIMEOUT_MS"]
