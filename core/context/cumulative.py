"""S6: Cumulative stats — reconciles telemetry events with block store."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CUMULATIVE_FILE = "cumulative.json"


def _num(v: Any) -> int:
    try:
        return int(v)
    except Exception:  # noqa: BLE001
        return 0


def _flt(v: Any) -> float:
    try:
        f = float(v)
        return f if f == f else 0.0
    except Exception:  # noqa: BLE001
        return 0.0


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
        try:
            return Path(self.worktree) / ".school" / "context" / CUMULATIVE_FILE
        except Exception:  # noqa: BLE001
            return Path(tempfile.gettempdir()) / "school-context" / CUMULATIVE_FILE

    def refresh(self) -> None:
        """Reload stats from telemetry + block store."""
        try:
            self._refresh_inner()
        except Exception:  # noqa: BLE001 — fail-open
            self._loaded = True

    def _refresh_inner(self) -> None:
        if os.environ.get("SCHOOL_TELEMETRY", "") == "0":
            return
        try:
            from core.context.telemetry import TelemetryCollector

            tc = TelemetryCollector(worktree=self.worktree)
            events = tc.events()
        except Exception:
            events = []

        # Reset counters before accumulating (idempotent refresh)
        self.compressions = 0
        self.total_tokens_saved = 0
        ratios: list[float] = []
        for ev in events:
            if not isinstance(ev, dict):
                continue
            try:
                if ev.get("event") == "compress":
                    self.compressions += 1
                    r = ev.get("ratio", 0.0)
                    if isinstance(r, (int, float)) and r == r:
                        ratios.append(float(r))
                    saved = ev.get("tokens_saved", 0)
                    if isinstance(saved, (int, float)):
                        self.total_tokens_saved += int(saved)
            except Exception:  # noqa: BLE001
                continue

        self.avg_ratio = sum(ratios) / len(ratios) if ratios else 0.0

        # Reconcile with block store
        try:
            from core.context.store import BlockStore

            bs = BlockStore(worktree=self.worktree)
            self.total_blocks = len(bs.load())
        except Exception:
            pass  # fail-open

        try:
            self.sessions = len({
                ev.get("session", "")
                for ev in events
                if isinstance(ev, dict) and ev.get("session")
            })
        except Exception:  # noqa: BLE001
            self.sessions = 0
        self._loaded = True
        self._save()

    def to_dict(self) -> dict[str, Any]:
        try:
            return {
                "total_tokens_saved": _num(self.total_tokens_saved),
                "total_blocks": _num(self.total_blocks),
                "compressions": _num(self.compressions),
                "sessions": _num(self.sessions),
                "avg_ratio": round(_flt(self.avg_ratio), 3),
            }
        except Exception:  # noqa: BLE001 — fail-open
            return {
                "total_tokens_saved": 0,
                "total_blocks": 0,
                "compressions": 0,
                "sessions": 0,
                "avg_ratio": 0.0,
            }

    def render_chip(self) -> str:
        """Return a compact chip: ``'⚡ 12 compress · 3.4k tok saved · 8 blocks'``."""
        try:
            saved = _num(self.total_tokens_saved)
            saved_str = f"{saved / 1000:.1f}k" if saved >= 1000 else str(saved)
            return (
                f"\u26a1 {_num(self.compressions)} compress \u00b7 "
                f"{saved_str} tok saved \u00b7 {_num(self.total_blocks)} blocks"
            )
        except Exception:  # noqa: BLE001 — fail-open
            return "\u26a1 0 compress \u00b7 0 tok saved \u00b7 0 blocks"

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self.to_dict(), indent=1, ensure_ascii=False), encoding="utf-8"
            )
            os.replace(tmp, self._path)
        except Exception:  # noqa: BLE001 — fail-open
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
        except Exception:  # noqa: BLE001 — fail-open
            pass
        return obj


__all__ = ["CumulativeStats"]
