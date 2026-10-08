"""S6 tests: cumulative stats."""

from __future__ import annotations

import json
from pathlib import Path

from core.context.cumulative import CumulativeStats


class TestCumulativeStats:
    def test_default_stats(self, tmp_path: Path) -> None:
        cs = CumulativeStats(worktree=str(tmp_path))
        d = cs.to_dict()
        assert d["total_tokens_saved"] == 0
        assert d["total_blocks"] == 0
        assert d["compressions"] == 0

    def test_refresh_from_events(self, tmp_path: Path) -> None:
        from core.context.telemetry import TelemetryCollector

        tc = TelemetryCollector(worktree=str(tmp_path), session="s1")
        tc.record("compress", ratio=0.5, tokens_saved=100)
        tc.record("compress", ratio=0.3, tokens_saved=200)
        tc.flush()

        cs = CumulativeStats(worktree=str(tmp_path))
        cs.refresh()
        assert cs.compressions == 2
        assert cs.total_tokens_saved == 300
        assert abs(cs.avg_ratio - 0.4) < 0.01

    def test_render_chip_format(self, tmp_path: Path) -> None:
        cs = CumulativeStats(
            worktree=str(tmp_path), compressions=5,
            total_tokens_saved=3400, total_blocks=8,
        )
        chip = cs.render_chip()
        assert "5 compress" in chip
        assert "3.4k" in chip
        assert "8 blocks" in chip

    def test_atomic_write(self, tmp_path: Path) -> None:
        cs = CumulativeStats(worktree=str(tmp_path), compressions=3)
        cs.refresh()
        path = tmp_path / ".school" / "context" / "cumulative.json"
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["compressions"] >= 0

    def test_load_roundtrip(self, tmp_path: Path) -> None:
        cs = CumulativeStats(worktree=str(tmp_path), compressions=7, total_tokens_saved=500)
        cs._save()
        loaded = CumulativeStats.load(str(tmp_path))
        assert loaded.compressions == 7
        assert loaded.total_tokens_saved == 500
