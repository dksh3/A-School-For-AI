from __future__ import annotations

from core.context.circuit import CircuitBreaker
from core.context.types import CircuitState


def make(clock_val: list[float], cooldown: float = 100.0) -> CircuitBreaker:
    return CircuitBreaker(clock=lambda: clock_val[0], cooldown=cooldown)


def test_ok_warning_error_critical_ladder() -> None:
    clk = [0.0]
    cb = make(clk)
    assert cb.state is CircuitState.OK
    assert cb.allow() is True
    assert cb.record_failure() is CircuitState.WARNING
    assert cb.record_failure() is CircuitState.ERROR
    assert cb.record_failure() is CircuitState.CRITICAL
    assert cb.allow() is False


def test_cooldown_reopens_after_elapsed_time() -> None:
    clk = [0.0]
    cb = make(clk, cooldown=100.0)
    for _ in range(3):
        cb.record_failure()
    assert cb.allow() is False
    clk[0] = 99.0
    assert cb.allow() is False
    clk[0] = 100.5
    assert cb.allow() is True  # cooldown elapsed -> Layer 1 may be attempted again


def test_success_resets_ladder() -> None:
    clk = [0.0]
    cb = make(clk)
    cb.record_failure()
    cb.record_failure()
    assert cb.state is CircuitState.ERROR
    assert cb.record_success() is CircuitState.OK
    assert cb.record_failure() is CircuitState.WARNING


def test_env_cooldown_default(monkeypatch) -> None:
    monkeypatch.delenv("SCHOOL_COMPRESS_COOLDOWN", raising=False)
    cb = CircuitBreaker(clock=lambda: 0.0)
    assert cb.cooldown == 300.0
    monkeypatch.setenv("SCHOOL_COMPRESS_COOLDOWN", "42")
    cb2 = CircuitBreaker(clock=lambda: 0.0)
    assert cb2.cooldown == 42.0
