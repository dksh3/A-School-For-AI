"""Deduplication tool for School V2.6."""

from __future__ import annotations

from core.learner.feature_extractor import FeatureExtractor
from core.learner.similarity import cosine_similarity
from core.routing.v26.identity import (
    AgentIdentity,
    MemoryScope,
    coerce_float,
    coerce_int,
    coerce_text,
)
from core.routing.v26.memory_store import MemoryStore
from core.routing.v26.semantic_retrieval import scored_query
from core.routing.v26.tools.base import (
    Tool,
    ToolResult,
    error_result,
    fail_open,
    fail_open_validate,
)


class DeduplicateTool(Tool):
    """Find duplicate or near-duplicate memories."""

    def __init__(self, store: MemoryStore, extractor: FeatureExtractor) -> None:
        self._store = store
        self._extractor = extractor

    @property
    def name(self) -> str:
        return "school_deduplicate"

    @property
    def description(self) -> str:
        return "Find duplicate or near-duplicate memories using semantic similarity."

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Content to check for duplicates."},
                "limit": {
                    "type": "integer",
                    "description": "Maximum similar memories to check.",
                    "default": 20,
                },
                "similarity_threshold": {
                    "type": "number",
                    "description": "Minimum similarity to consider a duplicate [0,1].",
                    "default": 0.8,
                },
                "agent_id": {
                    "type": "string",
                    "description": "Agent scope filter.",
                    "default": "default",
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

        limit = max(0, coerce_int(kwargs.get("limit", 20), 20))
        similarity_threshold = _resolve_threshold(kwargs.get("similarity_threshold"))
        agent_id = coerce_text(kwargs.get("agent_id", "default"), "default") or "default"

        agent = AgentIdentity.create(agent_id=agent_id)
        scope = MemoryScope(agent=agent)

        entries = self._store.query(scope=scope, limit=10000)

        candidates = scored_query(entries, content, self._extractor, limit=limit)

        duplicates: list[dict] = []
        try:
            content_vec = self._extractor.transform(content)
        except Exception as exc:  # noqa: BLE001 - fail-open
            return error_result(self.name, f"content not processable: {type(exc).__name__}")

        for entry in candidates:
            try:
                entry_vec = self._extractor.transform(entry.content)
                sim = cosine_similarity(content_vec, entry_vec, self._extractor)
                if sim >= similarity_threshold:
                    duplicates.append({
                        "memory_id": entry.memory_id,
                        "content": entry.content,
                        "similarity": sim,
                        "confidence": entry.confidence,
                    })
            except Exception:  # noqa: BLE001 - skip unreadable entries
                continue

        return ToolResult(
            success=True,
            data={
                "has_duplicates": len(duplicates) > 0,
                "duplicate_count": len(duplicates),
                "duplicates": duplicates,
                "similarity_threshold": similarity_threshold,
            },
            errors=[],
            metadata={"tool": self.name},
        )


def _resolve_threshold(raw: object) -> float:
    """Resolve similarity_threshold fail-open: garbage/NaN -> default 0.8, clamp [0,1]."""
    if raw is None:
        return 0.8
    value = coerce_float(raw, 0.8)
    return max(0.0, min(1.0, value))
