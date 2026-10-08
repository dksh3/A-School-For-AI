"""Base classes for School tools."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ToolResult:
    """Structured result from a tool execution."""
    success: bool
    data: dict
    errors: list[str]
    metadata: dict

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "data": self.data,
            "errors": self.errors,
            "metadata": self.metadata,
        }


class Tool(ABC):
    """Base class for all School tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool identifier."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description."""

    @property
    @abstractmethod
    def schema(self) -> dict:
        """JSON Schema for tool parameters."""

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """Execute the tool."""

    def validate(self, **kwargs) -> list[str]:
        """Validate parameters. Returns list of error messages."""
        return []


@dataclass
class PipelineResult:
    """Result of a multi-step tool pipeline."""
    steps: list[tuple[str, ToolResult]]
    success: bool

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "steps": [{"tool": name, "result": r.to_dict()} for name, r in self.steps],
        }


@dataclass
class BackgroundTask:
    """A queued background processing task."""
    task_type: str
    params: dict
    created_at: float = field(default_factory=time.time)


class ToolRegistry:
    """Registry of available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[dict]:
        return [{"name": t.name, "description": t.description, "schema": t.schema}
                for t in self._tools.values()]

    def execute(self, tool_name: str, **kwargs) -> ToolResult:
        # NOTE: first param is `tool_name` (not `name`) so tool keyword args
        # may legitimately include a `name` field (e.g. skill name).
        tool = self.get(tool_name)
        if tool is None:
            return ToolResult(
                success=False,
                data={},
                errors=[f"Unknown tool: {tool_name}"],
                metadata={},
            )
        errors = tool.validate(**kwargs)
        if errors:
            return ToolResult(success=False, data={}, errors=errors, metadata={})
        return tool.execute(**kwargs)
