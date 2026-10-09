"""V2.6 memory type definitions.

Defines the semantic memory types, memory entries, and request/response
contracts for the V2.6 long-term memory layer.

Design principles:
- Explicit memory semantics (WORKING, EPISODIC, LEARNED)
- Immutable memory entries for safety
- Validated requests/responses
- Bounded metadata
- Scope-aware
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from typing import Any

from core.routing.v26.identity import AgentIdentity, MemoryScope, ProjectIdentity, SessionIdentity

# ---------------------------------------------------------------------------
# Memory kinds
# ---------------------------------------------------------------------------


class MemoryKind(Enum):
    """Classification of memory semantics.

    WORKING: Short-lived working memory (current context).
    EPISODIC: Events, observations, experiences (may be promoted later).
    LEARNED: Verified learned knowledge (passed promotion boundary).
    """

    WORKING = auto()
    EPISODIC = auto()
    LEARNED = auto()


# ---------------------------------------------------------------------------
# Memory entry
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MemoryEntry:
    """A single memory stored in V2.6 long-term memory.

    Attributes:
        memory_id: Unique identifier.
        content: The memory content (text).
        kind: Memory semantics.
        scope: Full scope hierarchy.
        timestamp: When this memory was created.
        source: Source of this memory (agent, evo, user, external).
        tags: Optional tags for filtering.
        confidence: Confidence in this memory [0, 1].
        metadata: Additional metadata (bounded).
        parent_id: Optional parent memory reference.
        promoted_from: Original episodic memory ID if promoted.
    """

    memory_id: str
    content: str
    kind: MemoryKind
    scope: MemoryScope
    timestamp: float
    source: str = "agent"
    tags: frozenset[str] = field(default_factory=frozenset)
    confidence: float = 0.5
    metadata: dict[str, str | int | float | bool] = field(default_factory=dict)
    parent_id: str | None = None
    promoted_from: str | None = None

    @classmethod
    def create(
        cls,
        content: str,
        kind: MemoryKind,
        scope: MemoryScope,
        source: str = "agent",
        **kwargs: Any,
    ) -> MemoryEntry:
        """Create a MemoryEntry with auto-generated ID and timestamp."""
        memory_id = uuid.uuid4().hex[:16]
        timestamp = datetime.now(UTC).timestamp()
        return cls(
            memory_id=memory_id,
            content=content,
            kind=kind,
            scope=scope,
            timestamp=timestamp,
            source=source,
            **kwargs,
        )

    @property
    def content_length(self) -> int:
        """Character length of content."""
        return len(self.content)

    @property
    def estimated_tokens(self) -> int:
        """Rough token estimate (chars / 4)."""
        return max(1, self.content_length // 4)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-safe dictionary."""
        return {
            "memory_id": self.memory_id,
            "content": self.content,
            "kind": self.kind.name,
            "scope": self.scope.to_dict(),
            "timestamp": self.timestamp,
            "source": self.source,
            "tags": sorted(self.tags, key=str),
            "confidence": self.confidence,
            "metadata": dict(self.metadata),
            "parent_id": self.parent_id,
            "promoted_from": self.promoted_from,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryEntry:
        """Deserialize from dictionary."""
        kind_str = data.get("kind", "EPISODIC")
        try:
            kind = MemoryKind[kind_str]
        except KeyError:
            kind = MemoryKind.EPISODIC

        return cls(
            memory_id=str(data.get("memory_id", "")),
            content=str(data.get("content", "")),
            kind=kind,
            scope=MemoryScope.from_dict(data.get("scope", {})),
            timestamp=float(data.get("timestamp", 0.0)),
            source=str(data.get("source", "agent")),
            tags=frozenset(data.get("tags", [])),
            confidence=float(data.get("confidence", 0.5)),
            metadata=dict(data.get("metadata", {})),
            parent_id=data.get("parent_id"),
            promoted_from=data.get("promoted_from"),
        )


# ---------------------------------------------------------------------------
# Memory request
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MemoryRequest:
    """Request to retrieve memories from V2.6 long-term memory.

    Attributes:
        agent: Requesting agent identity.
        project: Optional project scope.
        session: Optional session scope.
        query: Search query text.
        limit: Maximum memories to return.
        minimum_confidence: Minimum confidence threshold.
        context_budget: Maximum tokens for returned memories.
        kinds: Memory kinds to search (empty = all).
        tags: Required tags filter.
    """

    agent: AgentIdentity
    query: str
    project: ProjectIdentity | None = None
    session: SessionIdentity | None = None
    limit: int = 10
    minimum_confidence: float = 0.0
    context_budget: int = 4096
    kinds: tuple[MemoryKind, ...] = ()
    tags: frozenset[str] = field(default_factory=frozenset)

    def to_scope(self) -> MemoryScope:
        """Convert request parameters to a MemoryScope."""
        return MemoryScope(agent=self.agent, project=self.project, session=self.session)

    def validate(self) -> tuple[bool, str]:
        """Validate the request. Returns (is_valid, reason)."""
        if not self.query:
            return False, "query must not be empty"
        if self.limit < 0:
            return False, "limit must be non-negative"
        if self.limit > 1000:
            return False, "limit must not exceed 1000"
        if not (0.0 <= self.minimum_confidence <= 1.0):
            return False, "minimum_confidence must be in [0, 1]"
        if self.context_budget < 0:
            return False, "context_budget must be non-negative"
        return True, ""


# ---------------------------------------------------------------------------
# Memory response
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MemoryResponse:
    """Response from V2.6 long-term memory retrieval.

    Attributes:
        memories: Retrieved memory entries.
        total: Total memories matching criteria (before limit).
        truncated: Whether results were truncated by limit or budget.
        context_cost: Total tokens consumed by returned memories.
        provenance: Memory IDs included in response.
    """

    memories: tuple[MemoryEntry, ...] = ()
    total: int = 0
    truncated: bool = False
    context_cost: int = 0
    provenance: tuple[str, ...] = ()

    @property
    def count(self) -> int:
        """Number of memories returned."""
        return len(self.memories)

    @property
    def is_empty(self) -> bool:
        """Check if response contains no memories."""
        return len(self.memories) == 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-safe dictionary."""
        return {
            "memories": [m.to_dict() for m in self.memories],
            "total": self.total,
            "truncated": self.truncated,
            "context_cost": self.context_cost,
            "provenance": list(self.provenance),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryResponse:
        """Deserialize from dictionary."""
        return cls(
            memories=tuple(MemoryEntry.from_dict(m) for m in data.get("memories", [])),
            total=int(data.get("total", 0)),
            truncated=bool(data.get("truncated", False)),
            context_cost=int(data.get("context_cost", 0)),
            provenance=tuple(data.get("provenance", [])),
        )
