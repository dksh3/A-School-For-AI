"""Diagnose tool for School V2.6 — health and stats."""

from __future__ import annotations

from core.routing.v26.memory_manager import MemoryManager
from core.routing.v26.tools.base import Tool, ToolResult, fail_open


class DiagnoseTool(Tool):
    """Return health and diagnostic information about the memory system."""

    def __init__(self, manager: MemoryManager) -> None:
        self._manager = manager

    @property
    def name(self) -> str:
        return "school_diagnose"

    @property
    def description(self) -> str:
        return "Return health and diagnostic information about the School memory system."

    @property
    def schema(self) -> dict:
        return {"type": "object", "properties": {}, "required": []}

    @fail_open
    def execute(self, **kwargs) -> ToolResult:
        stats = self._manager.stats()

        health = "healthy"
        warnings: list[str] = []

        if stats["error_count"] > 0:
            warnings.append(f"{stats['error_count']} errors encountered")
            health = "degraded"

        if stats["store_size"] == 0:
            warnings.append("Memory store is empty")

        return ToolResult(
            success=True,
            data={
                "health": health,
                "stats": stats,
                "warnings": warnings,
            },
            errors=[],
            metadata={"tool": self.name},
        )
