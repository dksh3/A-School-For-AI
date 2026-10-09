"""Central memory manager for School V2.6.

Coordinates the V2.6 read/write paths:
- Memory request validation and scope enforcement
- Retrieval coordination (via existing School systems)
- Confidence filtering
- Context budget enforcement
- Experience capture
- Lifecycle coordination
- Provenance tracking

Design principles:
- Does NOT replace V2.3 confidence, V2.2 conflict, V2.4.2 lifecycle, V2.5 routing
- Coordinates existing School systems rather than rebuilding them
- No global mutable state
- Deterministic and auditable
"""

from __future__ import annotations

import contextlib
from typing import Any

from core.learner.feature_extractor import FeatureExtractor
from core.routing.v26.consolidation import ConsolidationResult, consolidate_experiences
from core.routing.v26.experience import (
    Experience,
    is_promotable,
    validate_experience_content,
)
from core.routing.v26.identity import (
    AgentIdentity,
    MemoryScope,
    coerce_float,
    coerce_int,
    coerce_tag_set,
    coerce_text,
)
from core.routing.v26.memory_store import MemoryStore
from core.routing.v26.memory_types import (
    MemoryEntry,
    MemoryKind,
    MemoryRequest,
    MemoryResponse,
)
from core.routing.v26.persistence import PersistenceError, ScopeIsolatedStorage
from core.routing.v26.security import (
    V26SecurityPolicy,
    enforce_instruction_boundary,
    validate_memory_content,
    validate_memory_request,
)


def _err(exc: BaseException) -> str:
    """Format an exception safely (hostile __str__ must not raise)."""
    detail = coerce_text(exc, "<unprintable>")
    if len(detail) > 200:
        detail = detail[:200] + "..."
    return f"{type(exc).__name__}: {detail}"


class MemoryManager:
    """Central coordinator for V2.6 long-term memory.

    Manages the full lifecycle of memory: storage, retrieval,
    experience capture, consolidation, and persistence.

    No global mutable state — manager is per-instance.
    """

    def __init__(
        self,
        storage: ScopeIsolatedStorage | None = None,
        policy: V26SecurityPolicy | None = None,
        store: MemoryStore | None = None,
        extractor: FeatureExtractor | None = None,
    ) -> None:
        """Initialize the memory manager.

        Args:
            storage: Persistent storage backend (optional, for durability).
            policy: Security policy (optional, uses defaults if None).
            store: In-memory store (optional, creates default if None).
            extractor: TF-IDF feature extractor for semantic recall
                ranking (optional, creates default if None).
        """
        self._storage = storage
        self._policy = policy or V26SecurityPolicy()
        self._store = store or MemoryStore()
        self._extractor = extractor if extractor is not None else FeatureExtractor()
        self._consolidation_history: list[ConsolidationResult] = []
        self._operation_count = 0
        self._error_count = 0

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------

    def request_memory(self, request: MemoryRequest) -> MemoryResponse:
        """Process a memory retrieval request.

        The read path:
        1. Validate request and security policy
        2. Validate scope access
        3. Query in-memory store with scope filtering
           and semantic (TF-IDF) ranking via the feature extractor
        4. Filter by confidence
        5. Apply context budget
        6. Return bounded response

        Fail-open: any hostile or malformed request yields an empty
        MemoryResponse (and bumps the error counter), never a raise.

        Args:
            request: The memory retrieval request.

        Returns:
            MemoryResponse with matching memories.
        """
        self._operation_count += 1
        try:
            return self._request_memory_impl(request)
        except Exception:  # noqa: BLE001 - fail-open at the manager boundary
            self._error_count += 1
            return MemoryResponse()

    def _request_memory_impl(self, request: MemoryRequest) -> MemoryResponse:
        """Inner read path; hostile fields are coerced or rejected."""
        if not isinstance(request, MemoryRequest):
            self._error_count += 1
            return MemoryResponse()

        # Step 1: Validate request
        is_valid, reason = validate_memory_request(request, self._policy)
        if not is_valid:
            self._error_count += 1
            return MemoryResponse(
                memories=(),
                total=0,
                truncated=False,
                context_cost=0,
                provenance=(),
            )

        # Sanitize fields (dataclass construction does not type-check)
        limit = max(0, coerce_int(request.limit, 10))
        context_budget = max(0, coerce_int(request.context_budget, 4096))
        minimum_confidence = coerce_float(request.minimum_confidence, 0.0)
        tags = coerce_tag_set(request.tags)
        query_text = (
            request.query if isinstance(request.query, str) else coerce_text(request.query)
        )

        # Step 2: Build scope
        scope = request.to_scope()

        # Step 3: Query store
        kinds = tuple(k for k in (request.kinds or ()) if isinstance(k, MemoryKind))
        entries = self._store.query(
            scope=scope,
            kind=kinds[0] if len(kinds) == 1 else None,
            limit=limit + 100,  # Extra for budget filtering
            minimum_confidence=minimum_confidence,
            tags=tags if tags else None,
            query_text=query_text,
            extractor=self._extractor,
        )

        # Step 4: Filter by instruction boundary (security)
        safe_entries: list[MemoryEntry] = []
        for entry in entries:
            is_safe, _ = enforce_instruction_boundary(entry)
            if is_safe:
                safe_entries.append(entry)

        # Step 5: Apply context budget
        total_tokens = 0
        selected: list[MemoryEntry] = []
        truncated = False

        for entry in safe_entries:
            try:
                entry_tokens = entry.estimated_tokens
            except Exception:  # noqa: BLE001 - unreadable entries are skipped
                self._error_count += 1
                continue
            if total_tokens + entry_tokens > context_budget:
                truncated = True
                break
            if len(selected) >= limit:
                truncated = True
                break
            selected.append(entry)
            total_tokens += entry_tokens

        # Step 6: Build response
        provenance = tuple(e.memory_id for e in selected)
        return MemoryResponse(
            memories=tuple(selected),
            total=len(safe_entries),
            truncated=truncated,
            context_cost=total_tokens,
            provenance=provenance,
        )

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    def store_memory(
        self,
        entry: MemoryEntry,
        agent: AgentIdentity | None = None,
    ) -> tuple[bool, str]:
        """Store a memory entry.

        Validates content and scope before storage.

        Args:
            entry: The memory entry to store.
            agent: If provided, validates agent ownership.

        Returns:
            Tuple of (success, reason).
        """
        self._operation_count += 1

        if not isinstance(entry, MemoryEntry):
            self._error_count += 1
            return False, "invalid memory entry"

        # Reject entries that would poison in-memory queries (non-numeric
        # confidence breaks ordering/ranking in the shared store).
        if not isinstance(entry.confidence, (int, float)):
            self._error_count += 1
            return False, "invalid memory entry: confidence must be numeric"

        # Validate content (hostile entries -> graceful rejection)
        try:
            is_valid, reason = validate_memory_content(entry, self._policy)
        except Exception:  # noqa: BLE001
            self._error_count += 1
            return False, "invalid memory entry"
        if not is_valid:
            self._error_count += 1
            return False, reason

        # Validate agent ownership
        if agent is not None:
            try:
                if not isinstance(agent, AgentIdentity) or (
                    entry.scope.agent.agent_id != agent.agent_id
                ):
                    self._error_count += 1
                    return False, "agent ownership mismatch"
            except Exception:  # noqa: BLE001
                self._error_count += 1
                return False, "agent ownership mismatch"

        # Store in memory
        try:
            self._store.store(entry)
        except Exception as e:  # noqa: BLE001
            self._error_count += 1
            return False, f"storage error: {_err(e)}"

        # Persist if storage backend available
        if self._storage is not None:
            try:
                self._storage.store(entry)
            except Exception as e:
                self._error_count += 1
                return False, f"persistence error: {_err(e)}"

        return True, ""

    def store_experience(self, experience: Experience) -> tuple[bool, str]:
        """Store an experience as episodic memory.

        Validates the experience, converts to MemoryEntry, and stores.

        Args:
            experience: The experience to store.

        Returns:
            Tuple of (success, reason).
        """
        self._operation_count += 1

        if not isinstance(experience, Experience):
            self._error_count += 1
            return False, "invalid experience"

        try:
            # Validate experience
            is_valid, reason = experience.validate()
            if not is_valid:
                self._error_count += 1
                return False, reason

            # Validate content
            is_valid, reason = validate_experience_content(experience)
            if not is_valid:
                self._error_count += 1
                return False, reason

            # Convert to memory entry
            entry = experience.to_memory_entry()

            # Validate content
            is_valid, reason = validate_memory_content(entry, self._policy)
            if not is_valid:
                self._error_count += 1
                return False, reason
        except Exception as e:  # noqa: BLE001 - hostile experiences degrade to rejection
            self._error_count += 1
            return False, f"invalid experience: {_err(e)}"

        # Store
        try:
            self._store.store(entry)
        except Exception as e:  # noqa: BLE001
            self._error_count += 1
            return False, f"storage error: {_err(e)}"

        # Persist if storage backend available
        if self._storage is not None:
            try:
                self._storage.store(entry)
            except Exception as e:
                self._error_count += 1
                return False, f"persistence error: {_err(e)}"

        return True, ""

    # ------------------------------------------------------------------
    # Experience promotion
    # ------------------------------------------------------------------

    def check_promotion(
        self,
        experience: Experience,
    ) -> tuple[bool, str]:
        """Check if an experience is a candidate for promotion.

        Uses existing School mechanisms (confidence, evidence, lifecycle)
        to determine promotion readiness.

        Args:
            experience: The experience to evaluate.

        Returns:
            Tuple of (promotable, reason).
        """
        try:
            return is_promotable(experience)
        except Exception as e:  # noqa: BLE001 - hostile experiences are not promotable
            return False, f"experience cannot be evaluated: {_err(e)}"

    def promote_experience(
        self,
        experience: Experience,
    ) -> tuple[bool, str, MemoryEntry | None]:
        """Promote an experience to learned knowledge.

        Only promotes if the experience passes promotion criteria.

        Args:
            experience: The experience to promote.

        Returns:
            Tuple of (success, reason, created_entry).
        """
        self._operation_count += 1

        if not isinstance(experience, Experience):
            return False, "invalid experience", None

        try:
            is_promotable_result, reason = is_promotable(experience)
            if not is_promotable_result:
                return False, reason, None

            # Create learned memory entry
            entry = MemoryEntry(
                memory_id=experience.experience_id,
                content=experience.observation or experience.action,
                kind=MemoryKind.LEARNED,
                scope=experience.to_scope(),
                timestamp=experience.timestamp,
                source=experience.source,
                tags=experience.tags | frozenset({"promoted"}),
                confidence=experience.confidence,
                metadata=dict(experience.metadata),
                promoted_from=experience.experience_id,
            )

            # Validate and store
            is_valid, val_reason = validate_memory_content(entry, self._policy)
            if not is_valid:
                return False, val_reason, None

            self._store.store(entry)

            if self._storage is not None:
                try:
                    self._storage.store(entry)
                except Exception as e:  # noqa: BLE001
                    return False, f"persistence error: {_err(e)}", None
        except Exception as e:  # noqa: BLE001 - hostile experiences degrade to rejection
            self._error_count += 1
            return False, f"promotion failed: {_err(e)}", None

        return True, "", entry

    # ------------------------------------------------------------------
    # Consolidation
    # ------------------------------------------------------------------

    def consolidate(
        self,
        experiences: list[Experience],
        scope: MemoryScope | None = None,
    ) -> ConsolidationResult:
        """Consolidate experiences into learned knowledge.

        Groups experiences, merges consistent groups, and promotes
        when evidence is sufficient.

        Args:
            experiences: Experiences to consolidate.
            scope: Optional scope restriction.

        Returns:
            ConsolidationResult with promoted and retained entries.
        """
        self._operation_count += 1

        try:
            result = consolidate_experiences(experiences, scope=scope)
        except Exception as e:  # noqa: BLE001 - hostile input degrades to empty result
            self._error_count += 1
            return ConsolidationResult(
                provenance={"error": (_err(e),)},
            )
        self._consolidation_history.append(result)

        # Store promoted entries
        for entry in result.promoted:
            with contextlib.suppress(Exception):
                self._store.store(entry)
            if self._storage is not None:
                with contextlib.suppress(Exception):
                    self._storage.store(entry)

        return result

    # ------------------------------------------------------------------
    # Scope queries
    # ------------------------------------------------------------------

    def list_memories(
        self,
        scope: MemoryScope | None = None,
        kind: MemoryKind | None = None,
        limit: int = 100,
    ) -> list[MemoryEntry]:
        """List memories with optional filtering.

        Args:
            scope: Scope filter.
            kind: Kind filter.
            limit: Maximum results.

        Returns:
            List of matching memory entries.
        """
        try:
            return self._store.query(
                scope=scope, kind=kind, limit=max(0, coerce_int(limit, 100))
            )
        except Exception:  # noqa: BLE001 - hostile filters degrade to empty result
            self._error_count += 1
            return []

    def count_memories(
        self,
        scope: MemoryScope | None = None,
        kind: MemoryKind | None = None,
    ) -> int:
        """Count memories with optional filtering."""
        try:
            return self._store.count(scope=scope, kind=kind)
        except Exception:  # noqa: BLE001
            self._error_count += 1
            return 0

    def get_memory(self, memory_id: str) -> MemoryEntry | None:
        """Retrieve a specific memory by ID."""
        try:
            return self._store.get(memory_id)
        except Exception:  # noqa: BLE001 - hostile ids degrade to "not found"
            return None

    def remove_memory(self, memory_id: str) -> bool:
        """Remove a memory by ID."""
        try:
            removed = self._store.remove(memory_id)
        except Exception:  # noqa: BLE001
            return False
        if removed and self._storage is not None:
            with contextlib.suppress(Exception):
                self._storage.remove(memory_id)
        return removed

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def reload(self) -> int:
        """Reload from persistent storage.

        Returns:
            Number of entries loaded.

        Raises:
            PersistenceError: if the existing store state is corrupt or
                unreadable (documented storage contract — corrupt state is
                never silently treated as an empty store).
        """
        if self._storage is None:
            return 0
        try:
            count = self._storage.reload()
        except PersistenceError:
            raise
        except Exception as e:  # noqa: BLE001 - normalize to documented error
            self._error_count += 1
            raise PersistenceError(f"cannot reload store: {_err(e)}") from e
        # Rebuild in-memory store from persistence
        self._store.clear()
        for mid in self._storage.list_keys():
            entry = self._storage.get(mid)
            if entry is not None:
                self._store.store(entry)
        return count

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        """Return manager statistics."""
        try:
            return {
                "operation_count": self._operation_count,
                "error_count": self._error_count,
                "store_size": self._store.size,
                "consolidations": len(self._consolidation_history),
                "total_promoted": sum(
                    r.promoted_count for r in self._consolidation_history
                ),
            }
        except Exception as e:  # noqa: BLE001 - stats must never raise
            return {
                "operation_count": self._operation_count,
                "error_count": self._error_count + 1,
                "store_size": -1,
                "consolidations": 0,
                "total_promoted": 0,
                "stats_error": _err(e),
            }

    def clear(self, scope: MemoryScope | None = None) -> int:
        """Clear memories, optionally scoped.

        Returns:
            Number of memories cleared.
        """
        try:
            count = self._store.clear(scope=scope)
        except Exception:  # noqa: BLE001
            self._error_count += 1
            return 0
        if self._storage is not None:
            with contextlib.suppress(Exception):
                self._storage.clear(scope=scope)
        return count
