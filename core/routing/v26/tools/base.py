"""Base classes for School tools."""
from __future__ import annotations

import functools
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from core.routing.v26.identity import coerce_text

_F = TypeVar("_F", bound=Callable[..., Any])


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


def format_error(exc: BaseException) -> str:
    """Format an exception safely (hostile __str__ must not raise)."""
    detail = coerce_text(exc, "<unprintable>")
    if len(detail) > 200:
        detail = detail[:200] + "..."
    return f"{type(exc).__name__}: {detail}"


def error_result(tool_name: Any, message: str) -> ToolResult:
    """Build a graceful failure ToolResult that is always JSON-safe."""
    return ToolResult(
        success=False,
        data={},
        errors=[message],
        metadata={"tool": coerce_text(tool_name, "unknown")},
    )


def safe_memory_dict(memory: Any) -> dict:
    """Serialize a memory entry to a dict; unreadable entries degrade to a stub."""
    try:
        data = memory.to_dict()
        return data if isinstance(data, dict) else {"memory_id": "?", "content": ""}
    except Exception:  # noqa: BLE001 - never break a tool over one bad entry
        return {"memory_id": "?", "content": "", "error": "unreadable memory entry"}


def fail_open(fn: _F) -> _F:
    """Fail-open decorator for Tool.execute implementations.

    Guarantees the fail-open invariant at the tool boundary: ANY input
    (hostile or valid) returns a ToolResult and never raises. Positional
    arguments are rejected with an error result (tool APIs are kwargs-only).
    """

    @functools.wraps(fn)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> ToolResult:
        tool_name = coerce_text(getattr(self, "name", None), "unknown")
        if args:
            return error_result(
                tool_name,
                f"{fn.__name__} accepts keyword arguments only "
                f"(got {len(args)} positional)",
            )
        try:
            result = fn(self, **kwargs)
        except Exception as exc:  # noqa: BLE001 - fail-open: never raise
            return error_result(
                tool_name, f"{fn.__name__} failed safely: {format_error(exc)}"
            )
        if not isinstance(result, ToolResult):
            return error_result(
                tool_name, f"{fn.__name__} returned non-result: {type(result).__name__}"
            )
        return result

    return wrapper  # type: ignore[return-value]


def fail_open_validate(fn: _F) -> _F:
    """Fail-open decorator for Tool.validate implementations.

    Guarantees validate returns a list of error strings and never raises.
    """

    @functools.wraps(fn)
    def wrapper(self: Any, **kwargs: Any) -> list[str]:
        try:
            errors = fn(self, **kwargs)
        except Exception as exc:  # noqa: BLE001 - fail-open: never raise
            return [f"invalid arguments: {format_error(exc)}"]
        if not isinstance(errors, list):
            return ["invalid arguments: validator returned non-list"]
        out: list[str] = []
        for item in errors:
            out.append(coerce_text(item, "<unprintable error>"))
        return out

    return wrapper  # type: ignore[return-value]


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
    """Registry of available tools.

    Fail-open: registry lookups and execution never raise — unknown or
    hostile tool names and hostile arguments produce graceful ToolResult
    failures.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool. Raises ValueError (only) for invalid tools."""
        try:
            name = tool.name
            self._tools[name] = tool
        except ValueError:
            raise
        except Exception as exc:  # noqa: BLE001 - normalize to documented error
            raise ValueError(f"invalid tool: {format_error(exc)}") from exc

    def get(self, name: str) -> Tool | None:
        try:
            return self._tools.get(name)
        except Exception:  # noqa: BLE001 - hostile (unhashable) names -> not found
            return None

    def list_tools(self) -> list[dict]:
        tools: list[dict] = []
        for tool in self._tools.values():
            try:
                tools.append(
                    {"name": tool.name, "description": tool.description, "schema": tool.schema}
                )
            except Exception:  # noqa: BLE001 - skip unreadable registrations
                continue
        return tools

    def execute(self, tool_name: str, **kwargs) -> ToolResult:
        # NOTE: first param is `tool_name` (not `name`) so tool keyword args
        # may legitimately include a `name` field (e.g. skill name).
        tool = self.get(tool_name)
        if tool is None:
            return error_result(tool_name, f"Unknown tool: {coerce_text(tool_name, '?')}")
        try:
            errors = tool.validate(**kwargs)
            if not isinstance(errors, list):
                errors = ["invalid arguments: validator returned non-list"]
            errors = [coerce_text(e, "<unprintable error>") for e in errors]
        except Exception as exc:  # noqa: BLE001 - fail-open
            errors = [f"invalid arguments: {format_error(exc)}"]
        if errors:
            return ToolResult(success=False, data={}, errors=errors, metadata={})
        try:
            result = tool.execute(**kwargs)
        except Exception as exc:  # noqa: BLE001 - fail-open at the registry boundary
            return error_result(tool_name, f"tool failed safely: {format_error(exc)}")
        if not isinstance(result, ToolResult):
            return error_result(
                tool_name, f"tool returned non-result: {type(result).__name__}"
            )
        return result
