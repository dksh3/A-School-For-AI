"""S6 integration tests: telemetry end-to-end."""

from __future__ import annotations

from pathlib import Path

from core.context.cumulative import CumulativeStats
from core.context.telemetry import TelemetryCollector
from core.context.watchdog import watchdog


class TestTelemetryEndToEnd:
    def test_telemetry_end_to_end(self, tmp_path: Path) -> None:
        tc = TelemetryCollector(worktree=str(tmp_path), session="e2e")
        tc.record("compress", ratio=0.5, tokens_saved=100)
        tc.record("restore", ratio=1.0)
        tc.flush()

        cs = CumulativeStats(worktree=str(tmp_path))
        cs.refresh()
        assert cs.compressions == 1
        assert cs.total_tokens_saved == 100

    def test_watchdog_over_bridge(self) -> None:
        """Watchdog wraps a function and returns result on success."""
        r = watchdog(lambda: "bridge_ok")
        assert r == "bridge_ok"

    def test_watchdog_fails_open(self) -> None:
        r = watchdog(lambda: 1 / 0)
        assert r is None

    def test_cumulative_reconciles(self, tmp_path: Path) -> None:
        tc = TelemetryCollector(worktree=str(tmp_path), session="s1")
        for _ in range(5):
            tc.record("compress", ratio=0.4, tokens_saved=50)
        tc.flush()

        cs = CumulativeStats(worktree=str(tmp_path))
        cs.refresh()
        assert cs.compressions == 5
        assert cs.total_tokens_saved == 250

    def test_telemetry_survives_flush(self, tmp_path: Path) -> None:
        tc1 = TelemetryCollector(worktree=str(tmp_path), session="a")
        tc1.record("ev1", data="hello")
        tc1.flush()

        tc2 = TelemetryCollector(worktree=str(tmp_path), session="b")
        events = tc2.events()
        assert any(e.get("data") == "hello" for e in events)
