"""Semantic search tool for School V2.6."""

from __future__ import annotations

from core.learner.feature_extractor import FeatureExtractor
from core.routing.v26.identity import (
    AgentIdentity,
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
    safe_memory_dict,
)


class SemanticSearchTool(Tool):
    """Search memories using TF-IDF semantic similarity."""

    def __init__(self, store: MemoryStore, extractor: FeatureExtractor) -> None:
        self._store = store
        self._extractor = extractor

    @property
    def name(self) -> str:
        return "school_search"

    @property
    def description(self) -> str:
        return "Search memories using TF-IDF semantic similarity ranking."

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query text."},
                "limit": {"type": "integer", "description": "Maximum results.", "default": 10},
                "agent_id": {
                    "type": "string",
                    "description": "Agent scope filter.",
                    "default": "default",
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

        limit = max(0, coerce_int(kwargs.get("limit", 10), 10))
        agent_id = coerce_text(kwargs.get("agent_id", "default"), "default") or "default"

        agent = AgentIdentity.create(agent_id=agent_id)
        scope = _make_scope(agent)

        entries = self._store.query(scope=scope, limit=10000)

        results = scored_query(entries, query, self._extractor, limit=limit)

        return ToolResult(
            success=True,
            data={
                "memories": [safe_memory_dict(e) for e in results],
                "count": len(results),
                "query": query,
            },
            errors=[],
            metadata={"tool": self.name},
        )


def _make_scope(agent: AgentIdentity):
    """Create a MemoryScope from an AgentIdentity."""
    from core.routing.v26.identity import MemoryScope
    return MemoryScope(agent=agent)
