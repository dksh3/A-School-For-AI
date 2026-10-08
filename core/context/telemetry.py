"""S6: Telemetry collector — bounded JSONL event log with atomic flush."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TELEMETRY_FILE = "telemetry.jsonl"
MAX_EVENTS = 200
FLUSH_THRESHOLD = 20


@dataclass
class TelemetryCollector:
    worktree: str
    session: str = ""
    _buffer: list[dict[str, Any]] = field(default_factory=list, repr=False)

    @property
    def _path(self) -> Path:
        return Path(self.worktree) / ".school" / "context" / TELEMETRY_FILE

    def record(self, event: str, **kwargs: Any) -> None:
        """Buffer an event.  No-op when kill switch is set."""
        if os.environ.get("SCHOOL_TELEMETRY", "") == "0":
            return
        entry: dict[str, Any] = {
            "ts": int(time.time() * 1000),
            "event": event,
            "session": self.session,
            **kwargs,
        }
        self._buffer.append(entry)
        if len(self._buffer) >= FLUSH_THRESHOLD:
            self.flush()

    def events(self) -> list[dict[str, Any]]:
        """Return all events (on-disk + buffered), bounded to MAX_EVENTS."""
        on_disk = self._read_disk()
        return (on_disk + self._buffer)[-MAX_EVENTS:]

    def flush(self) -> None:
        """Atomically append buffered events to disk."""
        if not self._buffer:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "a", encoding="utf-8") as fh:
                for entry in self._buffer:
                    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass  # fail-open
        self._buffer.clear()

    def _read_disk(self) -> list[dict[str, Any]]:
        try:
            raw = self._path.read_text(encoding="utf-8")
        except OSError:
            return []
        out: list[dict[str, Any]] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except (ValueError, TypeError):
                continue  # corrupt line skipped
            if isinstance(obj, dict):
                out.append(obj)
        return out[-MAX_EVENTS:]


__all__ = ["TelemetryCollector"]
