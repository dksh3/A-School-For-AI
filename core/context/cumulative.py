"""S6: Cumulative stats — reconciles telemetry events with block store."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CUMULATIVE_FILE = "cumulative.json"


@dataclass
class CumulativeStats:
    worktree: str
    total_tokens_saved: int = 0
    total_blocks: int = 0
    compressions: int = 0
    sessions: int = 0
    avg_ratio: float = 0.0
    _loaded: bool = field(default=False, repr=False)

    @property
    def _path(self) -> Path:
        return Path(self.worktree) / ".school" / "context" / CUMULATIVE_FILE

    def refresh(self) -> None:
        """Reload stats from telemetry + block store."""
        if os.environ.get("SCHOOL_TELEMETRY", "") == "0":
            return
        try:
            from core.context.telemetry import TelemetryCollector

            tc = TelemetryCollector(worktree=self.worktree)
            events = tc.events()
        except Exception:
            events = []

        ratios: list[float] = []
        for ev in events:
            if ev.get("event") == "compress":
                self.compressions += 1
                r = ev.get("ratio", 0.0)
                if isinstance(r, (int, float)):
                    ratios.append(float(r))
                saved = ev.get("tokens_saved", 0)
                if isinstance(saved, (int, float)):
                    self.total_tokens_saved += int(saved)

        self.avg_ratio = sum(ratios) / len(ratios) if ratios else 0.0

        # Reconcile with block store
        try:
            from core.context.store import BlockStore

            bs = BlockStore(worktree=self.worktree)
            self.total_blocks = len(bs.list_blocks())
        except Exception:
            pass  # fail-open

        self.sessions = len({ev.get("session", "") for ev in events if ev.get("session")})
        self._loaded = True
        self._save()

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_tokens_saved": self.total_tokens_saved,
            "total_blocks": self.total_blocks,
            "compressions": self.compressions,
            "sessions": self.sessions,
            "avg_ratio": round(self.avg_ratio, 3),
        }

    def render_chip(self) -> str:
        """Return a compact chip: ``'⚡ 12 compress · 3.4k tok saved · 8 blocks'``."""
        saved = self.total_tokens_saved
        saved_str = f"{saved / 1000:.1f}k" if saved >= 1000 else str(saved)
        return (
            f"\u26a1 {self.compressions} compress \u00b7 "
            f"{saved_str} tok saved \u00b7 {self.total_blocks} blocks"
        )

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self.to_dict(), indent=1, ensure_ascii=False), encoding="utf-8"
            )
            os.replace(tmp, self._path)
        except OSError:
            pass  # fail-open

    @classmethod
    def load(cls, worktree: str) -> CumulativeStats:
        obj = cls(worktree=worktree)
        try:
            data = json.loads(obj._path.read_text(encoding="utf-8"))
            obj.total_tokens_saved = data.get("total_tokens_saved", 0)
            obj.total_blocks = data.get("total_blocks", 0)
            obj.compressions = data.get("compressions", 0)
            obj.sessions = data.get("sessions", 0)
            obj.avg_ratio = data.get("avg_ratio", 0.0)
        except (OSError, ValueError, TypeError):
            pass
        return obj


__all__ = ["CumulativeStats"]
