"""S6 tests: watchdog."""

from __future__ import annotations

from core.context.watchdog import watchdog


class TestWatchdog:
    def test_passes_through_success(self) -> None:
        result = watchdog(lambda x, y: x + y, 2, 3)
        assert result == 5

    def test_retries_once_on_error(self) -> None:
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) == 1:
                raise ValueError("first call fails")
            return "ok"

        result = watchdog(flaky)
        assert result == "ok"
        assert len(calls) == 2

    def test_fails_open_after_retry(self) -> None:
        result = watchdog(lambda: 1 / 0)
        assert result is None

    def test_kill_switch_no_retry(self) -> None:
        import os

        os.environ["SCHOOL_WATCHDOG"] = "0"
        try:
            calls = []

            def always_fail():
                calls.append(1)
                raise RuntimeError("fail")

            result = watchdog(always_fail)
            assert result is None
            assert len(calls) == 1
        finally:
            del os.environ["SCHOOL_WATCHDOG"]

    def test_returns_kwargs(self) -> None:
        result = watchdog(lambda a, b: f"{a}-{b}", a="x", b="y")
        assert result == "x-y"
