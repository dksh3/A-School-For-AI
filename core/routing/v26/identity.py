"""Universal identity abstractions for School V2.6.

Provides stable, serializable, deterministic identity primitives for
agents, projects, and sessions. Identity must NOT depend on any specific
AI provider, model, or framework.

Design principles:
- Provider/model/adapter are metadata, not identity
- Identity is serializable (to/from dict, JSON-safe)
- Identity is deterministic (same inputs → same ID)
- Identity is validated on construction
- Scope-aware: agent → project → session hierarchy
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any


def _stable_hash(*parts: str) -> str:
    """Compute a deterministic short hash from string parts."""
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Fail-open coercion helpers
#
# Shared by the V2.6 tool / manager / security layer. Every helper here must
# NEVER raise: hostile input (exploding __str__, unhashable, cyclic, NaN)
# degrades to the provided default so tool boundaries stay fail-open.
# ---------------------------------------------------------------------------


def coerce_text(value: Any, default: str = "") -> str:
    """Best-effort coercion to str that never raises."""
    if isinstance(value, str):
        return value
    if value is None:
        return default
    try:
        return str(value)
    except Exception:  # noqa: BLE001 - hostile __str__ must not escape
        return default


def coerce_float(value: Any, default: float = 0.0, *, finite: bool = True) -> float:
    """Coerce to float; unconvertible -> default; non-finite -> default."""
    if isinstance(value, bool):
        return float(value)
    try:
        result = float(value)
    except Exception:  # noqa: BLE001
        return default
    if finite and not math.isfinite(result):
        return default
    return result


def coerce_int(value: Any, default: int = 0) -> int:
    """Coerce to int; unconvertible/non-finite -> default."""
    if isinstance(value, bool):
        return int(value)
    try:
        if isinstance(value, float):
            return int(value) if math.isfinite(value) else default
        return int(value)
    except Exception:  # noqa: BLE001
        return default


def coerce_tag_set(value: Any) -> frozenset[str]:
    """Coerce an arbitrary value to a frozenset of non-empty strings."""
    if value is None:
        return frozenset()
    if isinstance(value, str):
        return frozenset({value}) if value else frozenset()
    tags: set[str] = set()
    try:
        iterator: Iterable[Any] = iter(value)
    except Exception:  # noqa: BLE001
        return frozenset()
    try:
        for item in iterator:
            text = coerce_text(item)
            if text:
                tags.add(text)
    except Exception:  # noqa: BLE001 - hostile iterators degrade to partial set
        pass
    return frozenset(tags)


def coerce_mapping(value: Any) -> dict[str, Any]:
    """Coerce an arbitrary value to a plain dict; garbage -> empty dict."""
    if isinstance(value, Mapping):
        try:
            return dict(value)
        except Exception:  # noqa: BLE001 - hostile mappings degrade to empty
            return {}
    try:
        return dict(value)
    except Exception:  # noqa: BLE001
        return {}


def _required_text(value: Any, field_name: str) -> str:
    """Coerce to a non-empty str, else raise ValueError (validated input)."""
    text = coerce_text(value, default="")
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


# ---------------------------------------------------------------------------
# AgentIdentity
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AgentIdentity:
    """Unique identity for an AI agent.

    Attributes:
        agent_id: Stable unique identifier.
        provider: Optional provider name (e.g. "openai", "anthropic").
        model: Optional model name (e.g. "gpt-4", "claude-3").
        adapter: Optional adapter name (e.g. "opencode", "claude_code").
        metadata: Additional identity metadata.
    """

    agent_id: str
    provider: str = ""
    model: str = ""
    adapter: str = ""
    metadata: dict[str, str | int | float | bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "agent_id", _required_text(self.agent_id, "agent_id"))
        object.__setattr__(self, "provider", coerce_text(self.provider))
        object.__setattr__(self, "model", coerce_text(self.model))
        object.__setattr__(self, "adapter", coerce_text(self.adapter))
        object.__setattr__(self, "metadata", coerce_mapping(self.metadata))

    @classmethod
    def create(cls, agent_id: str, **kwargs: Any) -> AgentIdentity:
        """Create an AgentIdentity with validation."""
        return cls(agent_id=agent_id, **kwargs)

    @classmethod
    def from_provider(cls, provider: str, model: str, **kwargs: Any) -> AgentIdentity:
        """Create an AgentIdentity from provider/model (generates stable ID)."""
        agent_id = _stable_hash(provider, model)
        return cls(agent_id=agent_id, provider=provider, model=model, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-safe dictionary."""
        d: dict[str, Any] = {"agent_id": self.agent_id}
        if self.provider:
            d["provider"] = self.provider
        if self.model:
            d["model"] = self.model
        if self.adapter:
            d["adapter"] = self.adapter
        if self.metadata:
            d["metadata"] = dict(self.metadata)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentIdentity:
        """Deserialize from dictionary.

        Uses a sentinel for empty agent_id to allow deserialization
        of incomplete data without raising. Hostile/unreadable fields
        degrade to safe defaults — this never raises.
        """
        try:
            agent_id = coerce_text(data.get("agent_id", ""))
            provider = coerce_text(data.get("provider", ""))
            model = coerce_text(data.get("model", ""))
            adapter = coerce_text(data.get("adapter", ""))
        except Exception:  # noqa: BLE001 - hostile mappings degrade to sentinel
            agent_id, provider, model, adapter = "", "", "", ""
        if not agent_id:
            agent_id = "__unresolved__"
        try:
            metadata = coerce_mapping(data.get("metadata", {}))
        except Exception:  # noqa: BLE001
            metadata = {}
        return cls(
            agent_id=agent_id,
            provider=provider,
            model=model,
            adapter=adapter,
            metadata=metadata,
        )

    def scope_key(self) -> str:
        """Return a deterministic key for scope-based lookups."""
        return f"agent:{self.agent_id}"


# ---------------------------------------------------------------------------
# ProjectIdentity
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProjectIdentity:
    """Unique identity for a project scope.

    Attributes:
        project_id: Stable unique identifier.
        name: Human-readable project name.
        agent_id: Owning agent's ID (optional, for multi-agent).
        metadata: Additional project metadata.
    """

    project_id: str
    name: str = ""
    agent_id: str = ""
    metadata: dict[str, str | int | float | bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", _required_text(self.project_id, "project_id"))
        object.__setattr__(self, "name", coerce_text(self.name))
        object.__setattr__(self, "agent_id", coerce_text(self.agent_id))
        object.__setattr__(self, "metadata", coerce_mapping(self.metadata))

    @classmethod
    def create(cls, project_id: str, **kwargs: Any) -> ProjectIdentity:
        """Create a ProjectIdentity with validation."""
        return cls(project_id=project_id, **kwargs)

    @classmethod
    def from_name(cls, name: str, agent_id: str = "", **kwargs: Any) -> ProjectIdentity:
        """Create a ProjectIdentity from a name (generates stable ID)."""
        project_id = _stable_hash(name, agent_id)
        return cls(project_id=project_id, name=name, agent_id=agent_id, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-safe dictionary."""
        d: dict[str, Any] = {"project_id": self.project_id}
        if self.name:
            d["name"] = self.name
        if self.agent_id:
            d["agent_id"] = self.agent_id
        if self.metadata:
            d["metadata"] = dict(self.metadata)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectIdentity:
        """Deserialize from dictionary.

        Raises ValueError (never TypeError/AttributeError/RuntimeError)
        when the data is hostile or missing a usable project_id.
        """
        try:
            project_id = coerce_text(data.get("project_id", ""))
            name = coerce_text(data.get("name", ""))
            agent_id = coerce_text(data.get("agent_id", ""))
        except Exception as exc:  # noqa: BLE001 - hostile data -> documented error
            raise ValueError("project_id must not be empty") from exc
        try:
            metadata = coerce_mapping(data.get("metadata", {}))
        except Exception:  # noqa: BLE001
            metadata = {}
        return cls(
            project_id=project_id,
            name=name,
            agent_id=agent_id,
            metadata=metadata,
        )

    def scope_key(self) -> str:
        """Return a deterministic key for scope-based lookups."""
        return f"project:{self.project_id}"


# ---------------------------------------------------------------------------
# SessionIdentity
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SessionIdentity:
    """Unique identity for a session scope.

    Attributes:
        session_id: Stable unique identifier.
        project_id: Owning project's ID.
        agent_id: Owning agent's ID.
        metadata: Additional session metadata.
    """

    session_id: str
    project_id: str = ""
    agent_id: str = ""
    metadata: dict[str, str | int | float | bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_id", _required_text(self.session_id, "session_id"))
        object.__setattr__(self, "project_id", coerce_text(self.project_id))
        object.__setattr__(self, "agent_id", coerce_text(self.agent_id))
        object.__setattr__(self, "metadata", coerce_mapping(self.metadata))

    @classmethod
    def create(cls, session_id: str, **kwargs: Any) -> SessionIdentity:
        """Create a SessionIdentity with validation."""
        return cls(session_id=session_id, **kwargs)

    @classmethod
    def from_context(
        cls, agent_id: str, project_id: str, **kwargs: Any
    ) -> SessionIdentity:
        """Create a SessionIdentity from agent/project context (generates stable ID)."""
        session_id = _stable_hash(agent_id, project_id)
        return cls(
            session_id=session_id,
            project_id=project_id,
            agent_id=agent_id,
            **kwargs,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-safe dictionary."""
        d: dict[str, Any] = {"session_id": self.session_id}
        if self.project_id:
            d["project_id"] = self.project_id
        if self.agent_id:
            d["agent_id"] = self.agent_id
        if self.metadata:
            d["metadata"] = dict(self.metadata)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionIdentity:
        """Deserialize from dictionary.

        Raises ValueError (never TypeError/AttributeError/RuntimeError)
        when the data is hostile or missing a usable session_id.
        """
        try:
            session_id = coerce_text(data.get("session_id", ""))
            project_id = coerce_text(data.get("project_id", ""))
            agent_id = coerce_text(data.get("agent_id", ""))
        except Exception as exc:  # noqa: BLE001 - hostile data -> documented error
            raise ValueError("session_id must not be empty") from exc
        try:
            metadata = coerce_mapping(data.get("metadata", {}))
        except Exception:  # noqa: BLE001
            metadata = {}
        return cls(
            session_id=session_id,
            project_id=project_id,
            agent_id=agent_id,
            metadata=metadata,
        )

    def scope_key(self) -> str:
        """Return a deterministic key for scope-based lookups."""
        return f"session:{self.session_id}"


# ---------------------------------------------------------------------------
# Composite scope
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MemoryScope:
    """Composite scope for memory operations.

    Encapsulates the full agent → project → session hierarchy
    used for memory isolation and retrieval.

    Attributes:
        agent: Agent identity.
        project: Optional project identity.
        session: Optional session identity.
    """

    agent: AgentIdentity
    project: ProjectIdentity | None = None
    session: SessionIdentity | None = None

    def scope_key(self) -> str:
        """Return a deterministic composite scope key."""
        parts = [f"agent:{self.agent.agent_id}"]
        if self.project:
            parts.append(f"project:{self.project.project_id}")
        if self.session:
            parts.append(f"session:{self.session.session_id}")
        return "|".join(parts)

    def includes(self, other: MemoryScope) -> bool:
        """Check if this scope includes the other scope.

        Scope A includes scope B if:
        - A.agent == B.agent (or A.agent is unspecified)
        - A.project includes B.project (or A.project is unspecified)
        - A.session includes B.session (or A.session is unspecified)

        Hostile or malformed scopes never include anything (fail-closed).
        """
        try:
            if self.agent.agent_id and self.agent.agent_id != other.agent.agent_id:
                return False
            if self.project and self.project.project_id and (
                other.project is None or self.project.project_id != other.project.project_id
            ):
                return False
            return not (
                self.session
                and self.session.session_id
                and (
                    other.session is None
                    or self.session.session_id != other.session.session_id
                )
            )
        except Exception:  # noqa: BLE001 - hostile scopes degrade to no access
            return False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-safe dictionary."""
        d: dict[str, Any] = {"agent": self.agent.to_dict()}
        if self.project:
            d["project"] = self.project.to_dict()
        if self.session:
            d["session"] = self.session.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryScope:
        """Deserialize from dictionary. Only ValueError may escape."""
        try:
            agent_raw = data.get("agent", {})
        except Exception as exc:  # noqa: BLE001 - hostile data -> documented error
            raise ValueError("agent_id must not be empty") from exc
        agent = AgentIdentity.from_dict(agent_raw)

        def _optional(key: str, factory) -> Any:
            try:
                if key not in data:
                    return None
                raw = data[key]
            except Exception:  # noqa: BLE001
                return None
            if raw is None:
                return None
            return factory(raw)

        return cls(
            agent=agent,
            project=_optional("project", ProjectIdentity.from_dict),
            session=_optional("session", SessionIdentity.from_dict),
        )
