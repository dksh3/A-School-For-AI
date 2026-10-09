"""Session/experience consolidation for School V2.6.

Consolidation processes episodic experiences into more durable forms,
potentially promoting them to learned knowledge.

Design principles:
- Deterministic: same inputs → same outputs
- Scope-safe: never mix scopes during consolidation
- Provenance-preserving: original experience IDs retained
- Bounded: processing time proportional to input size
- Idempotent: safe to re-run on same inputs
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.routing.v26.experience import Experience, ExperienceOutcome
from core.routing.v26.identity import MemoryScope
from core.routing.v26.memory_types import MemoryEntry, MemoryKind

# ---------------------------------------------------------------------------
# Consolidation result
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConsolidationResult:
    """Result of consolidating experiences.

    Attributes:
        promoted: Memory entries ready for learned knowledge.
        retained: Experiences kept as episodic (not yet promotable).
        discarded: Experiences that were invalid or empty.
        provenance: Source experience IDs for each promoted entry.
    """

    promoted: tuple[MemoryEntry, ...] = ()
    retained: tuple[Experience, ...] = ()
    discarded: tuple[str, ...] = ()
    provenance: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def promoted_count(self) -> int:
        """Number of memories promoted."""
        return len(self.promoted)

    @property
    def retained_count(self) -> int:
        """Number of experiences retained."""
        return len(self.retained)

    @property
    def discarded_count(self) -> int:
        """Number of experiences discarded."""
        return len(self.discarded)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-safe dictionary."""
        return {
            "promoted": [m.to_dict() for m in self.promoted],
            "retained": [e.to_dict() for e in self.retained],
            "discarded": list(self.discarded),
            "provenance": {k: list(v) for k, v in self.provenance.items()},
        }


# ---------------------------------------------------------------------------
# Consolidation logic
# ---------------------------------------------------------------------------


def _aggregate_outcomes(
    experiences: list[Experience],
) -> tuple[ExperienceOutcome, float, int]:
    """Aggregate outcomes from multiple experiences.

    Returns:
        (aggregated_outcome, avg_confidence, total_count).
    """
    if not experiences:
        return ExperienceOutcome.NEUTRAL, 0.0, 0

    outcomes = [e.outcome for e in experiences]
    successes = sum(1 for o in outcomes if o == ExperienceOutcome.SUCCESS)
    failures = sum(1 for o in outcomes if o == ExperienceOutcome.FAILURE)
    total = len(outcomes)

    if successes > 0 and failures > 0:
        aggregated = ExperienceOutcome.MIXED
    elif successes > failures:
        aggregated = ExperienceOutcome.SUCCESS
    elif failures > successes:
        aggregated = ExperienceOutcome.FAILURE
    else:
        aggregated = ExperienceOutcome.NEUTRAL

    avg_confidence = sum(e.confidence for e in experiences) / total

    return aggregated, avg_confidence, total


def _merge_content(experiences: list[Experience]) -> str:
    """Merge content from multiple experiences into a single description."""
    parts: list[str] = []
    observations = [e.observation for e in experiences if e.observation]
    actions = [e.action for e in experiences if e.action]
    feedbacks = [e.feedback for e in experiences if e.feedback]

    if observations:
        # Deduplicate while preserving order
        seen: set[str] = set()
        unique_obs = []
        for obs in observations:
            if obs not in seen:
                seen.add(obs)
                unique_obs.append(obs)
        parts.append("Observations: " + "; ".join(unique_obs))

    if actions:
        seen_actions: set[str] = set()
        unique_actions = []
        for act in actions:
            if act not in seen_actions:
                seen_actions.add(act)
                unique_actions.append(act)
        parts.append("Actions: " + "; ".join(unique_actions))

    if feedbacks:
        parts.append("Feedback: " + "; ".join(feedbacks[-3:]))  # Last 3

    return " | ".join(parts) if parts else "Consolidated experience"


def _merge_tags(experiences: list[Experience]) -> frozenset[str]:
    """Merge tags from multiple experiences."""
    merged: set[str] = set()
    for e in experiences:
        merged.update(e.tags)
    return frozenset(merged)


def _merge_metadata(experiences: list[Experience]) -> dict[str, str | int | float | bool]:
    """Merge metadata from later experiences (later wins)."""
    merged: dict[str, str | int | float | bool] = {}
    for e in experiences:
        merged.update(e.metadata)
    return merged


# ---------------------------------------------------------------------------
# Public consolidation API
# ---------------------------------------------------------------------------


def consolidate_experiences(
    experiences: list[Experience],
    scope: MemoryScope | None = None,
    min_group_size: int = 2,
    max_group_size: int = 100,
) -> ConsolidationResult:
    """Consolidate a list of experiences.

    Groups experiences by scope, then by outcome consistency.
    Consistent groups are promoted to learned memories.
    Mixed or single experiences are retained.

    Args:
        experiences: List of experiences to consolidate.
        scope: If provided, only consolidate within this scope.
        min_group_size: Minimum experiences in a group to promote.
        max_group_size: Maximum experiences per group.

    Returns:
        ConsolidationResult with promoted, retained, and discarded entries.
    """
    if not experiences:
        return ConsolidationResult()

    # Group by scope
    scope_groups: dict[str, list[Experience]] = {}
    for exp in experiences:
        # Validate experience
        is_valid, _ = exp.validate()
        if not is_valid:
            continue

        key = exp.to_scope().scope_key()
        if scope is not None and not scope.includes(exp.to_scope()):
            continue

        if key not in scope_groups:
            scope_groups[key] = []
        scope_groups[key].append(exp)

    promoted: list[MemoryEntry] = []
    retained: list[Experience] = []
    discarded: list[str] = []
    provenance: dict[str, tuple[str, ...]] = {}

    for _scope_key, group in scope_groups.items():
        # Sort by timestamp for deterministic grouping
        sorted_group = sorted(group, key=lambda e: e.timestamp)

        # Group by outcome consistency
        outcome_groups: dict[ExperienceOutcome, list[Experience]] = {}
        for exp in sorted_group:
            outcome_groups.setdefault(exp.outcome, []).append(exp)

        for outcome, outcome_exps in outcome_groups.items():
            # Chunk by max_group_size
            for i in range(0, len(outcome_exps), max_group_size):
                chunk = outcome_exps[i : i + max_group_size]

                if len(chunk) >= min_group_size and outcome != ExperienceOutcome.NEUTRAL:
                    # Promote: merge into a single learned memory
                    avg_conf = sum(e.confidence for e in chunk) / len(chunk)
                    content = _merge_content(chunk)
                    tags = _merge_tags(chunk)
                    metadata = _merge_metadata(chunk)

                    # Use first experience's scope as representative
                    representative_scope = chunk[0].to_scope()

                    entry = MemoryEntry.create(
                        content=content,
                        kind=MemoryKind.LEARNED,
                        scope=representative_scope,
                        source="consolidation",
                        tags=tags | frozenset({"consolidated", f"outcome:{outcome.name.lower()}"}),
                        confidence=min(1.0, avg_conf * 1.1),  # Small consolidation bonus
                        metadata=metadata,
                    )
                    promoted.append(entry)
                    provenance[entry.memory_id] = tuple(e.experience_id for e in chunk)
                else:
                    # Retain: not enough evidence for promotion
                    retained.extend(chunk)

    return ConsolidationResult(
        promoted=tuple(promoted),
        retained=tuple(retained),
        discarded=tuple(discarded),
        provenance=provenance,
    )


def should_consolidate(experiences: list[Experience]) -> bool:
    """Determine if consolidation should be triggered.

    Heuristics:
    - More than 5 experiences with same outcome
    - Or experiences span more than 1 hour
    - Or more than 10 total experiences
    """
    if not experiences:
        return False

    # Check outcome concentration
    outcome_counts: dict[ExperienceOutcome, int] = {}
    for e in experiences:
        outcome_counts[e.outcome] = outcome_counts.get(e.outcome, 0) + 1

    if any(c >= 5 for c in outcome_counts.values()):
        return True

    # Check time span
    if len(experiences) >= 2:
        timestamps = [e.timestamp for e in experiences if e.timestamp > 0]
        if timestamps:
            span = max(timestamps) - min(timestamps)
            if span > 3600:  # 1 hour
                return True

    return len(experiences) > 10
