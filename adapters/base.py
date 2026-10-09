"""Abstract harness adapter interface.

The core contract that all harness adapters must implement to communicate
with the learning engine. Each adapter bridges a specific AI coding
assistant (OpenCode, Claude Code, Codex, etc.) to the engine's unified
learning pipeline.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class AdapterCapability(Enum):
    """Capabilities an adapter may advertise."""

    CODE_GENERATION = auto()
    CODE_EXPLANATION = auto()
    FILE_EDITING = auto()
    TERMINAL_ACCESS = auto()
    WEB_SEARCH = auto()
    CONTEXT_INJECTION = auto()


@dataclass
class AdapterConfig:
    """Configuration for a harness adapter."""

    name: str
    enabled: bool = True
    options: dict[str, Any] = field(default_factory=dict)
    capabilities: list[AdapterCapability] = field(default_factory=list)


@dataclass
class AdapterResponse:
    """Standardised response from an adapter interaction."""

    content: str
    success: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


class HarnessAdapter(ABC):
    """Abstract base class for harness adapters.

    Each concrete adapter wraps a specific AI coding assistant and
    translates between the engine's learning events and the assistant's
    native interface.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this adapter (e.g. 'opencode', 'claude_code')."""
        ...

    @property
    @abstractmethod
    def capabilities(self) -> list[AdapterCapability]:
        """Capabilities supported by this adapter."""
        ...

    @abstractmethod
    async def configure(self, config: AdapterConfig) -> None:
        """Apply configuration to the adapter.

        Args:
            config: The adapter configuration.
        """
        ...

    @abstractmethod
    async def send_prompt(
        self, prompt: str, context: dict[str, Any] | None = None
    ) -> AdapterResponse:
        """Send a prompt to the underlying harness and return the response.

        Args:
            prompt: The prompt text.
            context: Optional context (file state, prior conversation, etc.).

        Returns:
            An AdapterResponse with the harness output.
        """
        ...

    @abstractmethod
    async def inject_context(self, context: dict[str, Any]) -> None:
        """Inject learning context into the harness session.

        Args:
            context: Context data (e.g. relevant docs, code snippets).
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the underlying harness is reachable and ready."""
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """Cleanly shut down the adapter and release resources."""
        ...
