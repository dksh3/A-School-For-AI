"""Knowledge extraction tool for School V2.6."""

from __future__ import annotations

from core.routing.v26.identity import MemoryScope, coerce_text
from core.routing.v26.memory_manager import MemoryManager
from core.routing.v26.tools.base import (
    Tool,
    ToolResult,
    fail_open,
    safe_memory_dict,
)


class KnowledgeExtractionTool(Tool):
    """Consolidate experiences into learned knowledge."""

    def __init__(self, manager: MemoryManager) -> None:
        self._manager = manager

    @property
    def name(self) -> str:
        return "school_knowledge"

    @property
    def description(self) -> str:
        return "Consolidate episodic experiences into learned knowledge."

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "Agent scope for consolidation.",
                    "default": "default",
                },
            },
            "required": [],
        }

    @fail_open
    def execute(self, **kwargs) -> ToolResult:
        agent_id = coerce_text(kwargs.get("agent_id", "default"), "default") or "default"

        from core.routing.v26.identity import AgentIdentity
        agent = AgentIdentity.create(agent_id=agent_id)
        scope = MemoryScope(agent=agent)

        result = self._manager.consolidate([], scope=scope)

        return ToolResult(
            success=True,
            data={
                "promoted_count": result.promoted_count,
                "retained_count": result.retained_count,
                "discarded_count": result.discarded_count,
                "promoted": [safe_memory_dict(e) for e in result.promoted],
                "provenance": {
                    coerce_text(k): [coerce_text(i) for i in v]
                    for k, v in result.provenance.items()
                },
            },
            errors=[],
            metadata={"tool": self.name},
        )
