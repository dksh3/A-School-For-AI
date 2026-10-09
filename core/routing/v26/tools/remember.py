"""Remember tool for School V2.6 — store an experience."""

from __future__ import annotations

from core.routing.v26.experience import Experience, ExperienceOutcome
from core.routing.v26.identity import (
    AgentIdentity,
    ProjectIdentity,
    SessionIdentity,
    coerce_float,
    coerce_tag_set,
    coerce_text,
)
from core.routing.v26.memory_manager import MemoryManager
from core.routing.v26.tools.base import (
    Tool,
    ToolResult,
    error_result,
    fail_open,
    fail_open_validate,
)


class RememberTool(Tool):
    """Store an experience into School long-term memory."""

    def __init__(self, manager: MemoryManager) -> None:
        self._manager = manager

    @property
    def name(self) -> str:
        return "school_remember"

    @property
    def description(self) -> str:
        return "Store an experience into School long-term memory."

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Experience content to remember."},
                "outcome": {
                    "type": "string",
                    "enum": ["SUCCESS", "FAILURE", "NEUTRAL", "MIXED"],
                    "description": "Outcome of the experience.",
                    "default": "NEUTRAL",
                },
                "observation": {"type": "string", "description": "What was observed."},
                "action": {"type": "string", "description": "What action was taken."},
                "agent_id": {
                    "type": "string", "description": "Agent identifier.", "default": "default"
                },
                "project": {"type": "string", "description": "Project scope identifier."},
                "session": {"type": "string", "description": "Session scope identifier."},
                "source": {
                    "type": "string", "description": "Source of the experience.", "default": "tool"
                },
                "tags": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Tags for filtering.",
                },
                "confidence": {
                    "type": "number", "description": "Confidence in this memory [0,1].",
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
        except Exception:  # noqa: BLE001 - hostile content is rejected, not raised on
            content_empty = True
        content = coerce_text(raw_content)
        if content_empty or not content:
            return error_result(self.name, "content is required and must not be empty")

        outcome_raw = kwargs.get("outcome", "NEUTRAL")
        outcome_key = coerce_text(outcome_raw)
        try:
            outcome = ExperienceOutcome[outcome_key]
        except Exception:  # noqa: BLE001 - unhashable/hostile outcome -> graceful error
            return error_result(
                self.name,
                f"Invalid outcome: {coerce_text(outcome_raw, '<unprintable>')}. "
                "Must be one of: SUCCESS, FAILURE, NEUTRAL, MIXED",
            )

        obs_raw = kwargs.get("observation", content)
        observation = coerce_text(obs_raw, content)
        action = coerce_text(kwargs.get("action", ""))
        agent_id = _first_text(
            kwargs.get("agent_id"), kwargs.get("agent"), default="default"
        )
        project_id = _first_text(kwargs.get("project"), kwargs.get("project_id"))
        session_id = _first_text(kwargs.get("session"), kwargs.get("session_id"))
        source = coerce_text(kwargs.get("source", "tool"), "tool")
        tags = coerce_tag_set(kwargs.get("tags", []))
        # NaN/inf flow through so experience validation rejects them gracefully
        confidence = coerce_float(kwargs.get("confidence", 0.5), 0.5, finite=False)

        agent = AgentIdentity.create(agent_id=agent_id)
        project = (
            ProjectIdentity.create(project_id=project_id, name=project_id)
            if project_id
            else None
        )
        session = (
            SessionIdentity.create(
                session_id=session_id, project_id=project_id, agent_id=agent_id
            )
            if session_id
            else None
        )
        experience = Experience.create(
            agent=agent,
            project=project,
            session=session,
            observation=observation,
            action=action,
            outcome=outcome,
            source=source,
            tags=tags,
            confidence=confidence,
        )

        success, reason = self._manager.store_experience(experience)

        return ToolResult(
            success=success,
            data={"experience_id": experience.experience_id, "stored": success},
            errors=[] if success else [reason],
            metadata={"tool": self.name},
        )


def _first_text(*values: object, default: str = "") -> str:
    """First truthy value coerced to text; all garbage -> default."""
    for value in values:
        try:
            if value:
                text = coerce_text(value)
                if text:
                    return text
        except Exception:  # noqa: BLE001
            continue
    return default
