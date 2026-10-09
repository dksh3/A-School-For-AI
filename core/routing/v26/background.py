"""Background worker for continuous learning tasks."""
from __future__ import annotations

from typing import TYPE_CHECKING

from core.routing.v26.tools.base import ToolResult

if TYPE_CHECKING:
    from core.routing.v26.orchestrator import Orchestrator

class BackgroundWorker:
    def __init__(self, orchestrator: Orchestrator, config: dict | None = None) -> None:
        self._orchestrator = orchestrator
        self._config = config or {}
        self._memory_count = 0
        self._consolidation_threshold = self._config.get("consolidation_threshold", 10)

    def on_memory_stored(self) -> None:
        self._memory_count += 1
        if self._memory_count >= self._consolidation_threshold:
            self._orchestrator.trigger_background("school_knowledge", min_occurrences=3)
            self._memory_count = 0

    def run_cycle(self) -> list[ToolResult]:
        return self._orchestrator.process_background()
