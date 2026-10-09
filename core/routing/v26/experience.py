"""Episodic experience abstraction for School V2.6.

Represents agent experiences as first-class objects that can be stored,
retrieved, and potentially promoted into learned knowledge.

Design principles:
- Experiences are DATA, not instructions
- Each experience preserves full provenance
- Experiences are validated before persistence
- Promotion into learned knowledge requires evidence
- Deterministic and auditable
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from typing import Any

from core.routing.v26.identity import AgentIdentity, MemoryScope, ProjectIdentity, SessionIdentity
from core.routing.v26.memory_types import MemoryEntry, MemoryKind

# ---------------------------------------------------------------------------
# Experience types
# ---------------------------------------------------------------------------


class ExperienceOutcome(Enum):
    """Outcome of an experience."""

    SUCCESS = auto()
    FAILURE = auto()
    NEUTRAL = auto()
    MIXED = auto()


# ---------------------------------------------------------------------------
# Experience
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Experience:
    """A single episodic experience from an agent.

    Attributes:
        experience_id: Unique identifier.
        agent: Agent that generated this experience.
        project: Project context.
        session: Session context.
        timestamp: When this experience occurred.
        observation: What the agent observed.
        action: What the agent did.
        outcome: The outcome of the action.
        feedback: Optional feedback received.
        confidence: Agent's confidence in the experience [0, 1].
        source: Source of the experience.
        tags: Tags for filtering.
        metadata: Additional metadata.
    """

    experience_id: str
    agent: AgentIdentity
    project: ProjectIdentity | None = None
    session: SessionIdentity | None = None
    timestamp: float = 0.0
    observation: str = ""
    action: str = ""
    outcome: ExperienceOutcome = ExperienceOutcome.NEUTRAL
    feedback: str = ""
    confidence: float = 0.5
    source: str = "agent"
    tags: frozenset[str] = field(default_factory=frozenset)
    metadata: dict[str, str | int | float | bool] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        agent: AgentIdentity,
        observation: str = "",
        action: str = "",
        outcome: ExperienceOutcome = ExperienceOutcome.NEUTRAL,
        **kwargs: Any,
    ) -> Experience:
        """Create an Experience with auto-generated ID and timestamp."""
        experience_id = uuid.uuid4().hex[:16]
        ts = kwargs.pop("timestamp", None)
        if ts is None:
            ts = datetime.now(UTC).timestamp()
        return cls(
            experience_id=experience_id,
            agent=agent,
            timestamp=ts,
            observation=observation,
            action=action,
            outcome=outcome,
            **kwargs,
        )

    def to_scope(self) -> MemoryScope:
        """Convert experience context to a MemoryScope."""
        return MemoryScope(agent=self.agent, project=self.project, session=self.session)

    def to_memory_entry(self) -> MemoryEntry:
        """Convert experience to a MemoryEntry for storage.

        The experience content is composed from observation, action,
        and outcome. The memory kind is EPISODIC.
        """
        parts: list[str] = []
        if self.observation:
            parts.append(f"Observation: {self.observation}")
        if self.action:
            parts.append(f"Action: {self.action}")
        parts.append(f"Outcome: {self.outcome.name}")
        if self.feedback:
            parts.append(f"Feedback: {self.feedback}")

        content = " | ".join(parts)

        tags = self.tags
        tags = tags | frozenset({f"outcome:{self.outcome.name.lower()}"})

        return MemoryEntry(
            memory_id=self.experience_id,
            content=content,
            kind=MemoryKind.EPISODIC,
            scope=self.to_scope(),
            timestamp=self.timestamp,
            source=self.source,
            tags=tags,
            confidence=self.confidence,
            metadata=dict(self.metadata),
        )

    def validate(self) -> tuple[bool, str]:
        """Validate the experience. Returns (is_valid, reason)."""
        if not self.agent or not self.agent.agent_id or self.agent.agent_id == "__unresolved__":
            return False, "agent identity is required"
        if not self.experience_id:
            return False, "experience_id is required"
        if not (0.0 <= self.confidence <= 1.0):
            return False, "confidence must be in [0, 1]"
        if self.timestamp < 0:
            return False, "timestamp must be non-negative"
        return True, ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-safe dictionary."""
        return {
            "experience_id": self.experience_id,
            "agent": self.agent.to_dict(),
            "project": self.project.to_dict() if self.project else None,
            "session": self.session.to_dict() if self.session else None,
            "timestamp": self.timestamp,
            "observation": self.observation,
            "action": self.action,
            "outcome": self.outcome.name,
            "feedback": self.feedback,
            "confidence": self.confidence,
            "source": self.source,
            "tags": sorted(self.tags, key=str),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Experience:
        """Deserialize from dictionary."""
        outcome_str = data.get("outcome", "NEUTRAL")
        try:
            outcome = ExperienceOutcome[outcome_str]
        except KeyError:
            outcome = ExperienceOutcome.NEUTRAL

        return cls(
            experience_id=str(data.get("experience_id", "")),
            agent=AgentIdentity.from_dict(data.get("agent", {})),
            project=ProjectIdentity.from_dict(data["project"]) if data.get("project") else None,
            session=SessionIdentity.from_dict(data["session"]) if data.get("session") else None,
            timestamp=float(data.get("timestamp", 0.0)),
            observation=str(data.get("observation", "")),
            action=str(data.get("action", "")),
            outcome=outcome,
            feedback=str(data.get("feedback", "")),
            confidence=float(data.get("confidence", 0.5)),
            source=str(data.get("source", "agent")),
            tags=frozenset(data.get("tags", [])),
            metadata=dict(data.get("metadata", {})),
        )


# ---------------------------------------------------------------------------
# Experience validation
# ---------------------------------------------------------------------------


def validate_experience_content(experience: Experience) -> tuple[bool, str]:
    """Validate experience content for safety and completeness.

    Returns:
        Tuple of (is_valid, reason).
    """
    if not experience.observation and not experience.action:
        return False, "experience must have at least observation or action"

    if len(experience.observation) > 100_000:
        return False, "observation exceeds maximum length"

    if len(experience.action) > 100_000:
        return False, "action exceeds maximum length"

    if len(experience.feedback) > 50_000:
        return False, "feedback exceeds maximum length"

    return True, ""


def is_promotable(experience: Experience) -> tuple[bool, str]:
    """Determine if an experience is a candidate for promotion to learned knowledge.

    Promotion criteria:
    - Experience must have outcome
    - Confidence must be above threshold
    - Not mixed outcome (needs clear signal)

    Returns:
        Tuple of (promotable, reason).
    """
    if experience.outcome == ExperienceOutcome.MIXED:
        return False, "mixed outcomes require consolidation before promotion"

    if experience.outcome == ExperienceOutcome.NEUTRAL:
        return False, "neutral experiences are not promotable"

    if experience.confidence < 0.3:
        return False, "confidence too low for promotion"

    if not experience.observation and not experience.action:
        return False, "no meaningful content for promotion"

    return True, "experience is a promotion candidate"
