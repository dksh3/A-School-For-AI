"""Conflict detection tool for School V2.6."""

from __future__ import annotations

from core.routing.v26.identity import (
    AgentIdentity,
    coerce_float,
    coerce_int,
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
)

# Default minimum similarity for a conflict (legacy behavior).
_DEFAULT_SIMILARITY_THRESHOLD = 0.3


class ConflictDetectionTool(Tool):
    """Detect conflicts between new content and existing memories."""

    def __init__(self, manager: MemoryManager) -> None:
        self._manager = manager

    @property
    def name(self) -> str:
        return "school_conflict"

    @property
    def description(self) -> str:
        return "Detect conflicts between new content and existing memories."

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "New content to check for conflicts."},
                "agent_id": {
                    "type": "string",
                    "description": "Agent identifier.",
                    "default": "default",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum similar memories to retrieve.",
                    "default": 5,
                },
                "similarity_threshold": {
                    "type": "number",
                    "description": "Minimum similarity to consider a conflict [0,1].",
                    "default": 0.5,
                },
            },
            "required": ["content"],
        }

    @fail_open_validate
    def validate(self, **kwargs) -> list[str]:
        errors: list[str] = []
        raw = kwargs.get("content", "")
        try:
            empty = not raw
        except Exception:  # noqa: BLE001 - hostile content is a validation error
            empty = True
        if empty or not coerce_text(raw):
            errors.append("content is required and must not be empty")
        return errors

    @fail_open
    def execute(self, **kwargs) -> ToolResult:
        raw_content = kwargs.get("content", "")
        try:
            content_empty = not raw_content
        except Exception:  # noqa: BLE001
            content_empty = True
        content = coerce_text(raw_content)
        if content_empty or not content:
            return error_result(self.name, "content is required and must not be empty")

        agent_id = coerce_text(kwargs.get("agent_id", "default"), "default") or "default"
        limit = max(0, coerce_int(kwargs.get("limit", 5), 5))
        threshold = _resolve_threshold(kwargs.get("similarity_threshold"))

        agent = AgentIdentity.create(agent_id=agent_id)
        request = MemoryRequest(
            agent=agent,
            query=content,
            limit=limit,
            minimum_confidence=0.0,
        )

        response = self._manager.request_memory(request)

        conflicts: list[dict] = []
        content_lower = content.lower()
        content_words = set(content_lower.split())
        for mem in response.memories:
            # Simple overlap-based conflict detection
            try:
                mem_lower = coerce_text(mem.content).lower()
                mem_words = set(mem_lower.split())
                overlap = content_words & mem_words

                if len(overlap) > 2:
                    # If significant overlap but not identical, potential conflict
                    similarity = len(overlap) / max(
                        len(content_words), len(mem_words), 1
                    )
                    if similarity > threshold:
                        conflicts.append({
                            "memory_id": mem.memory_id,
                            "content": mem.content,
                            "similarity": similarity,
                            "overlap_count": len(overlap),
                            "confidence": mem.confidence,
                        })
            except Exception:  # noqa: BLE001 - skip unreadable memories
                continue

        return ToolResult(
            success=True,
            data={
                "has_conflicts": len(conflicts) > 0,
                "conflict_count": len(conflicts),
                "conflicts": conflicts,
                "similar_memories_count": response.count,
            },
            errors=[],
            metadata={"tool": self.name},
        )


def _resolve_threshold(raw: object) -> float:
    """Resolve similarity_threshold fail-open: garbage/NaN -> legacy default."""
    if raw is None:
        return _DEFAULT_SIMILARITY_THRESHOLD
    value = coerce_float(raw, _DEFAULT_SIMILARITY_THRESHOLD)
    return max(0.0, min(1.0, value))
