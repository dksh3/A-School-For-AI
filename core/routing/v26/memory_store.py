"""In-memory store for V2.6 long-term memory.

Provides fast, scope-isolated in-memory storage for memory entries.
This is the primary working store; persistence.py handles durability.

Design principles:
- No global mutable state
- Scope-isolated retrieval
- Bounded size
- Thread-safe operations (via immutable entries)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.routing.v26.identity import MemoryScope
from core.routing.v26.memory_types import MemoryEntry, MemoryKind

if TYPE_CHECKING:
    from core.learner.feature_extractor import FeatureExtractor
    from core.learner.semantic_encoder import SemanticEncoder


class MemoryStore:
    """In-memory store for V2.6 memory entries.

    Provides fast insertion and scope-filtered retrieval.
    Persistence is handled separately by ScopeIsolatedStorage.

    No global mutable state — store is per-instance.
    """

    def __init__(self, max_entries: int = 100_000) -> None:
        """Initialize the memory store.

        Args:
            max_entries: Maximum entries before eviction triggers.
        """
        self._max_entries = max_entries
        self._entries: dict[str, MemoryEntry] = {}
        self._insert_order: list[str] = []

    def store(self, entry: MemoryEntry) -> None:
        """Store a memory entry (create or update)."""
        if entry.memory_id not in self._entries:
            self._insert_order.append(entry.memory_id)
        self._entries[entry.memory_id] = entry

        # Evict oldest if over capacity
        if len(self._entries) > self._max_entries:
            excess = len(self._entries) - self._max_entries
            to_remove = self._insert_order[:excess]
            for mid in to_remove:
                self._entries.pop(mid, None)
            self._insert_order = self._insert_order[excess:]

    def get(self, memory_id: str) -> MemoryEntry | None:
        """Retrieve a memory entry by ID."""
        return self._entries.get(memory_id)

    def remove(self, memory_id: str) -> bool:
        """Remove a memory entry by ID."""
        if memory_id not in self._entries:
            return False
        del self._entries[memory_id]
        if memory_id in self._insert_order:
            self._insert_order.remove(memory_id)
        return True

    def query(
        self,
        scope: MemoryScope | None = None,
        kind: MemoryKind | None = None,
        limit: int = 100,
        minimum_confidence: float = 0.0,
        tags: frozenset[str] | None = None,
        query_text: str = "",
        extractor: FeatureExtractor | None = None,
        encoder: SemanticEncoder | None = None,
    ) -> list[MemoryEntry]:
        """Query memory entries with filtering.

        Args:
            scope: If provided, filter by scope.
            kind: If provided, filter by memory kind.
            limit: Maximum results.
            minimum_confidence: Minimum confidence threshold.
            tags: Required tags (all must match).
            query_text: Simple substring match on content.
            extractor: TF-IDF feature extractor for semantic ranking.
                When provided with a non-empty query_text, entries are
                ranked by TF-IDF cosine similarity instead of substring
                matching.
            encoder: Optional semantic encoder for blended ranking.

        Returns:
            List of matching entries. When extractor is provided with a
            non-empty query_text, results are ranked by relevance
            descending. Otherwise, most recent first.
        """
        # Collect candidates matching scope/kind/confidence/tags filters
        candidates: list[MemoryEntry] = []
        for entry in reversed(self._entries.values()):
            # Scope filter
            if scope is not None:
                if entry.scope.agent.agent_id != scope.agent.agent_id:
                    continue
                if scope.project and scope.project.project_id and (
                    entry.scope.project is None
                    or entry.scope.project.project_id != scope.project.project_id
                ):
                    continue
                if scope.session and scope.session.session_id and (
                    entry.scope.session is None
                    or entry.scope.session.session_id != scope.session.session_id
                ):
                    continue

            # Kind filter
            if kind is not None and entry.kind != kind:
                continue

            # Confidence filter
            if entry.confidence < minimum_confidence:
                continue

            # Tags filter
            if tags and not tags.issubset(entry.tags):
                continue

            candidates.append(entry)

        if not candidates:
            return []

        # Apply text filtering/ranking
        if query_text and extractor is not None:
            from core.routing.v26.semantic_retrieval import scored_query

            # Semantic ranking: score candidates by TF-IDF similarity
            results = scored_query(
                candidates, query_text, extractor, encoder=encoder, limit=limit
            )
        elif query_text:
            # Fallback: substring matching (legacy behavior)
            query_lower = query_text.lower()
            results = [
                e for e in candidates if query_lower in e.content.lower()
            ][:limit]
        else:
            # No query text: return filtered candidates, most recent first
            results = candidates[:limit]

        return results

    def count(
        self,
        scope: MemoryScope | None = None,
        kind: MemoryKind | None = None,
    ) -> int:
        """Count entries with optional filtering."""
        count = 0
        for entry in self._entries.values():
            if scope is not None:
                if entry.scope.agent.agent_id != scope.agent.agent_id:
                    continue
                if scope.project and scope.project.project_id and (
                    entry.scope.project is None
                    or entry.scope.project.project_id != scope.project.project_id
                ):
                    continue
            if kind is not None and entry.kind != kind:
                continue
            count += 1
        return count

    def clear(self, scope: MemoryScope | None = None) -> int:
        """Clear entries, optionally scoped.

        Returns:
            Number of entries cleared.
        """
        if scope is None:
            count = len(self._entries)
            self._entries.clear()
            self._insert_order.clear()
            return count

        to_remove: list[str] = []
        for mid, entry in self._entries.items():
            if entry.scope.agent.agent_id != scope.agent.agent_id:
                continue
            if scope.project and scope.project.project_id and (
                entry.scope.project is None
                or entry.scope.project.project_id != scope.project.project_id
            ):
                continue
            if scope.session and scope.session.session_id and (
                entry.scope.session is None
                or entry.scope.session.session_id != scope.session.session_id
            ):
                continue
            to_remove.append(mid)

        for mid in to_remove:
            self._entries.pop(mid, None)
            if mid in self._insert_order:
                self._insert_order.remove(mid)

        return len(to_remove)

    @property
    def size(self) -> int:
        """Current number of entries."""
        return len(self._entries)

    @property
    def is_empty(self) -> bool:
        """Check if store is empty."""
        return len(self._entries) == 0

    def all_ids(self) -> list[str]:
        """Return all memory IDs in insertion order."""
        return list(self._insert_order)
