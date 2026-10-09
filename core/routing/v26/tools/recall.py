"""Recall tool for School V2.6 — retrieve memories by query."""

from __future__ import annotations

from core.routing.v26.identity import (
    AgentIdentity,
    coerce_float,
    coerce_int,
    coerce_tag_set,
    coerce_text,
)
from core.routing.v26.memory_manager import MemoryManager
from core.routing.v26.memory_types import MemoryRequest
from core.routing.v26.tools.base import (
    Tool,
    ToolResult,
    error_result,
    fail_open,
    fail_open_validate,
    safe_memory_dict,
)


class RecallTool(Tool):
    """Retrieve memories from School long-term memory by query."""

    def __init__(self, manager: MemoryManager) -> None:
        self._manager = manager

    @property
    def name(self) -> str:
        return "school_recall"

    @property
    def description(self) -> str:
        return "Retrieve memories from School long-term memory by query."

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query text."},
                "agent_id": {
                    "type": "string",
                    "description": "Agent identifier.",
                    "default": "default",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum memories to return.",
                    "default": 10,
                },
                "minimum_confidence": {
                    "type": "number",
                    "description": "Minimum confidence threshold [0,1].",
                    "default": 0.0,
                },
                "context_budget": {
                    "type": "integer",
                    "description": "Maximum tokens for returned memories.",
                    "default": 4096,
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Required tags filter.",
                    "default": [],
                },
            },
            "required": ["query"],
        }

    @fail_open_validate
    def validate(self, **kwargs) -> list[str]:
        errors: list[str] = []
        raw = kwargs.get("query", "")
        try:
            empty = not raw
        except Exception:  # noqa: BLE001 - hostile query is a validation error
            empty = True
        if empty or not coerce_text(raw):
            errors.append("query is required and must not be empty")
        return errors

    @fail_open
    def execute(self, **kwargs) -> ToolResult:
        raw_query = kwargs.get("query", "")
        try:
            query_empty = not raw_query
        except Exception:  # noqa: BLE001
            query_empty = True
        query = coerce_text(raw_query)
        if query_empty or not query:
            return error_result(self.name, "query is required and must not be empty")

        agent_id = coerce_text(kwargs.get("agent_id", "default"), "default") or "default"
        limit = coerce_int(kwargs.get("limit", 10), 10)
        # NaN/inf flow through so request validation rejects them gracefully
        minimum_confidence = coerce_float(
            kwargs.get("minimum_confidence", 0.0), 0.0, finite=False
        )
        context_budget = coerce_int(kwargs.get("context_budget", 4096), 4096)
        tags = coerce_tag_set(kwargs.get("tags", []))

        agent = AgentIdentity.create(agent_id=agent_id)
        request = MemoryRequest(
            agent=agent,
            query=query,
            limit=limit,
            minimum_confidence=minimum_confidence,
            context_budget=context_budget,
            tags=tags,
        )

        response = self._manager.request_memory(request)

        return ToolResult(
            success=True,
            data={
                "memories": [safe_memory_dict(m) for m in response.memories],
                "total": response.total,
                "truncated": response.truncated,
                "context_cost": response.context_cost,
                "count": response.count,
            },
            errors=[],
            metadata={"tool": self.name, "provenance": list(response.provenance)},
        )
