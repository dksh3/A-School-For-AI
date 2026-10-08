# core/context/circuit.py
from __future__ import annotations

import os
import time
from collections.abc import Callable

from core.context.types import CircuitState

_TRIP_AT = 3


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


class CircuitBreaker:
    """3 consecutive Layer-1 failures -> critical + cooldown (fail open after)."""

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        cooldown: float | None = None,
    ) -> None:
        self._clock = clock
        self.cooldown = (
            cooldown if cooldown is not None else _env_float("SCHOOL_COMPRESS_COOLDOWN", 300.0)
        )
        self._failures = 0
        self._until = 0.0

    @property
    def state(self) -> CircuitState:
        if self._failures >= _TRIP_AT:
            return CircuitState.CRITICAL
        if self._failures == 2:
            return CircuitState.ERROR
        if self._failures == 1:
            return CircuitState.WARNING
        return CircuitState.OK

    def allow(self) -> bool:
        if self._failures < _TRIP_AT:
            return True
        return self._clock() >= self._until

    def record_failure(self) -> CircuitState:
        self._failures += 1
        if self._failures >= _TRIP_AT:
            self._until = self._clock() + self.cooldown
        return self.state

    def record_success(self) -> CircuitState:
        self._failures = 0
        self._until = 0.0
        return CircuitState.OK


__all__ = ["CircuitBreaker"]
