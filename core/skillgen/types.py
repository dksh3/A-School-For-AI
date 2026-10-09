"""1A-2Z skill data model: Skill, scope, lifecycle states, provenance.

Phase 1 (automatic skill generation from agent experience). Skills are
reusable, instructional procedures - DATA the agent reads, never executable
code this package runs. Experiences feed the pipeline; confidence and
lifecycle primitives are reused from core.learner (no second engine).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
MAX_FIELD = 4000
MAX_PROCEDURE_STEPS = 40


# ---------------------------------------------------------------------------
# Fail-open coercion helpers (never raise, even on hostile objects)
# ---------------------------------------------------------------------------


def safe_str(value: Any, limit: int | None = None) -> str:
    """Coerce any value to str without raising (hostile __str__/__repr__)."""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = str(value)
        except Exception:
            try:
                text = repr(value)
            except Exception:
                text = f"<{type(value).__name__}>"
    return text[:limit] if limit is not None else text


def safe_float(value: Any, default: float = 0.0) -> float:
    """Coerce to a finite float in one step; NaN/inf and junk -> default."""
    try:
        out = float(value)
    except Exception:
        return default
    if math.isnan(out) or math.isinf(out):
        return default
    return out


def safe_int(value: Any, default: int = 0) -> int:
    """Coerce to a bounded int; junk -> default. Never raises."""
    try:
        out = int(value)
    except Exception:
        return default
    return max(-(10**12), min(10**12, out))


def safe_list_str(
    value: Any, max_items: int = 40, max_len: int = 400
) -> list[str]:
    """Coerce any value to a bounded list of safe strings. Never raises."""
    if value is None:
        return []
    if isinstance(value, str):
        items: list[Any] = [value]
    else:
        try:
            items = list(value)
        except Exception:
            items = [value]
    return [safe_str(item, max_len) for item in items[:max_items]]


def _get(data: Any, key: str, default: Any = None) -> Any:
    """dict.get that survives hostile mappings."""
    try:
        return data.get(key, default)
    except Exception:
        return default


def _json_safe(value: Any, depth: int = 0) -> Any:
    """Recursively coerce to JSON-serializable data (bounded)."""
    if depth > 4:
        return safe_str(value, 200)
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return safe_int(value)
    if isinstance(value, float):
        return safe_float(value)
    if isinstance(value, str):
        return value[:4000]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        try:
            for k, v in list(value.items())[:100]:
                out[safe_str(k, 200)] = _json_safe(v, depth + 1)
        except Exception:
            return {}
        return out
    if isinstance(value, (list, tuple, set, frozenset)):
        try:
            items = list(value)[:100]
        except Exception:
            return [safe_str(value, 200)]
        return [_json_safe(v, depth + 1) for v in items]
    return safe_str(value, 200)


class SkillState(Enum):
    """Lifecycle of a skill (skill-specific states over the same concepts
    the memory lifecycle uses: active / superseded / archived)."""

    CANDIDATE = "candidate"
    VALIDATING = "validating"
    ACTIVE = "active"
    PROVEN = "proven"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


RETRIEVABLE_STATES = frozenset({SkillState.ACTIVE, SkillState.PROVEN})


class SkillScope(Enum):
    """How broadly a skill applies. Narrower scopes never leak wider."""

    SESSION = "session"
    PROJECT = "project"
    AGENT = "agent"
    GLOBAL = "global"


def _now() -> float:
    return datetime.now(UTC).timestamp()


@dataclass(frozen=True, slots=True)
class SkillEvent:
    """One provenance entry in a skill's history (why/when it changed)."""

    version: int
    event: str
    reason: str
    timestamp: float
    confidence: float
    experience_id: str = ""
    actor: str = "skillgen"

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "event": self.event,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "confidence": self.confidence,
            "experience_id": self.experience_id,
            "actor": self.actor,
        }

    @classmethod
    def from_dict(cls, data: Any) -> SkillEvent:
        """Deserialize defensively: any input yields a valid event record."""
        return cls(
            version=safe_int(_get(data, "version", 1), 1),
            event=safe_str(_get(data, "event", ""), 200),
            reason=safe_str(_get(data, "reason", ""), 500),
            timestamp=safe_float(_get(data, "timestamp", 0.0)),
            confidence=max(0.0, min(1.0, safe_float(_get(data, "confidence", 0.5), 0.5))),
            experience_id=safe_str(_get(data, "experience_id", ""), 200),
            actor=safe_str(_get(data, "actor", "skillgen"), 100),
        )


@dataclass(slots=True)
class Skill:
    """A reusable capability generated by 1A-Z2."""

    name: str
    description: str
    purpose: str
    triggers: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    procedure: list[str] = field(default_factory=list)
    expected_output: str = ""
    constraints: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    confidence: float = 0.5
    created_from: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    version: int = 1
    success_count: int = 0
    failure_count: int = 0
    use_count: int = 0
    state: SkillState = SkillState.CANDIDATE
    scope: SkillScope = SkillScope.SESSION
    agent_id: str = ""
    project_id: str = ""
    session_id: str = ""
    tags: list[str] = field(default_factory=list)
    history: list[SkillEvent] = field(default_factory=list)
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)

    def bump_version(self, event: str, reason: str, **kw: Any) -> None:
        self.version += 1
        self.updated_at = _now()
        self.history.append(
            SkillEvent(
                version=self.version,
                event=event,
                reason=reason,
                timestamp=self.updated_at,
                confidence=self.confidence,
                **kw,
            )
        )

    def record(self, event: str, reason: str, **kw: Any) -> None:
        self.updated_at = _now()
        self.history.append(
            SkillEvent(
                version=self.version,
                event=event,
                reason=reason,
                timestamp=self.updated_at,
                confidence=self.confidence,
                **kw,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "purpose": self.purpose,
            "triggers": list(self.triggers),
            "inputs": list(self.inputs),
            "procedure": list(self.procedure),
            "expected_output": self.expected_output,
            "constraints": list(self.constraints),
            "examples": list(self.examples),
            "confidence": self.confidence,
            "created_from": list(self.created_from),
            "provenance": dict(self.provenance),
            "version": self.version,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "use_count": self.use_count,
            "state": self.state.value,
            "scope": self.scope.value,
            "agent_id": self.agent_id,
            "project_id": self.project_id,
            "session_id": self.session_id,
            "tags": list(self.tags),
            "history": [e.to_dict() for e in self.history],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Skill:
        """Deserialize defensively: any input yields a valid (maybe empty) skill.

        Corrupt registries and hostile payloads never raise here; unusable
        fields are coerced to safe defaults and counters are clamped.
        """
        if not isinstance(data, dict):
            data = {}
        try:
            state_raw = safe_str(_get(data, "state", "candidate"), 32)
            try:
                state = SkillState(state_raw)
            except ValueError:
                state = SkillState.CANDIDATE
            try:
                scope = SkillScope(safe_str(_get(data, "scope", "session"), 32))
            except ValueError:
                scope = SkillScope.SESSION
            raw_provenance = _get(data, "provenance", {})
            provenance = (
                _json_safe(raw_provenance) if isinstance(raw_provenance, dict) else {}
            )
            history: list[SkillEvent] = []
            try:
                history_raw = _get(data, "history", [])
                if isinstance(history_raw, (list, tuple)):
                    for item in list(history_raw)[:500]:
                        history.append(SkillEvent.from_dict(item))
            except Exception:  # noqa: BLE001 - hostile history container
                history = []
            return cls(
                name=safe_str(_get(data, "name", ""), 200),
                description=safe_str(_get(data, "description", ""), 8000),
                purpose=safe_str(_get(data, "purpose", ""), 8000),
                triggers=safe_list_str(_get(data, "triggers", []), 8, 400),
                inputs=safe_list_str(_get(data, "inputs", []), 8, 400),
                procedure=safe_list_str(
                    _get(data, "procedure", []), MAX_PROCEDURE_STEPS, 4000
                ),
                expected_output=safe_str(_get(data, "expected_output", ""), 8000),
                constraints=safe_list_str(_get(data, "constraints", []), 16, 400),
                examples=safe_list_str(_get(data, "examples", []), 8, 400),
                confidence=max(0.0, min(1.0, safe_float(_get(data, "confidence", 0.5), 0.5))),
                created_from=safe_list_str(_get(data, "created_from", []), 32, 200),
                provenance=provenance,
                version=max(1, safe_int(_get(data, "version", 1), 1)),
                success_count=max(0, safe_int(_get(data, "success_count", 0))),
                failure_count=max(0, safe_int(_get(data, "failure_count", 0))),
                use_count=max(0, safe_int(_get(data, "use_count", 0))),
                state=state,
                scope=scope,
                agent_id=safe_str(_get(data, "agent_id", ""), 200),
                project_id=safe_str(_get(data, "project_id", ""), 200),
                session_id=safe_str(_get(data, "session_id", ""), 200),
                tags=safe_list_str(_get(data, "tags", []), 8, 100),
                history=history,
                created_at=safe_float(_get(data, "created_at", 0.0)),
                updated_at=safe_float(_get(data, "updated_at", 0.0)),
            )
        except Exception:
            return cls(name="", description="", purpose="")

    def to_skill_md(self) -> str:
        """Render as SKILL.md (frontmatter + body) for agent consumption."""
        name = safe_str(self.name, 200)
        triggers = [safe_str(t, 400) for t in (self.triggers or [])]
        inputs = [safe_str(i, 400) for i in (self.inputs or [])]
        procedure = [safe_str(s, 4000) for s in (self.procedure or [])]
        constraints = [safe_str(c, 400) for c in (self.constraints or [])]
        examples = [safe_str(e, 400) for e in (self.examples or [])]
        created_from = [safe_str(c, 200) for c in (self.created_from or [])]
        state_val = self.state.value if isinstance(self.state, SkillState) else "candidate"
        scope_val = self.scope.value if isinstance(self.scope, SkillScope) else "session"
        lines = [
            "---",
            f"name: {name}",
            f"description: {safe_str(self.description, MAX_FIELD)}",
            f"state: {state_val}",
            f"scope: {scope_val}",
            f"version: {safe_int(self.version, 1)}",
            f"confidence: {safe_float(self.confidence, 0.5):.2f}",
            f"purpose: {safe_str(self.purpose, MAX_FIELD)}",
            f"triggers: [{', '.join(triggers)}]",
            f"created_from: [{', '.join(created_from)}]",
            "---",
            "",
            f"# {name}",
            "",
            safe_str(self.purpose, MAX_FIELD),
            "",
            "## When to use",
            *[f"- {t}" for t in triggers],
            "",
            "## Inputs",
            *([f"- {i}" for i in inputs] or ["- none"]),
            "",
            "## Procedure",
            *[f"{i}. {step}" for i, step in enumerate(procedure, 1)],
            "",
            f"## Expected output\n{safe_str(self.expected_output, MAX_FIELD)}",
        ]
        if constraints:
            lines += ["", "## Constraints", *[f"- {c}" for c in constraints]]
        if examples:
            lines += ["", "## Examples", *[f"- {e}" for e in examples]]
        lines += [
            "",
            "## Provenance",
            f"- confidence: {safe_float(self.confidence, 0.5):.2f}",
            f"- created from: {', '.join(created_from) or 'manual'}",
            f"- success/failure: {safe_int(self.success_count)}/"
            f"{safe_int(self.failure_count)}",
            "",
        ]
        return "\n".join(lines)


def scope_visible(skill: Skill, agent_id: str, project_id: str, session_id: str) -> bool:
    """Scope isolation: can a viewer with this context see the skill?"""
    try:
        if not isinstance(skill, Skill):
            return False
        if skill.scope == SkillScope.GLOBAL:
            return True
        viewer_agent = safe_str(agent_id, 200)
        viewer_project = safe_str(project_id, 200)
        viewer_session = safe_str(session_id, 200)
        if skill.scope == SkillScope.AGENT:
            return bool(skill.agent_id) and skill.agent_id == viewer_agent
        if skill.scope == SkillScope.PROJECT:
            return bool(skill.project_id) and skill.project_id == viewer_project
        if skill.scope == SkillScope.SESSION:
            return bool(skill.session_id) and skill.session_id == viewer_session
        return False
    except Exception:
        return False
