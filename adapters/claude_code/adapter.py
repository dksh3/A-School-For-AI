"""Claude Code harness adapter stub."""

from typing import Any

from adapters.base import AdapterCapability, AdapterConfig, AdapterResponse, HarnessAdapter


class ClaudeCodeAdapter(HarnessAdapter):
    """Adapter for the Claude Code harness.

    Bridges the learning engine to Claude Code's interface.
    """

    @property
    def name(self) -> str:
        return "claude_code"

    @property
    def capabilities(self) -> list[AdapterCapability]:
        return [
            AdapterCapability.CODE_GENERATION,
            AdapterCapability.CODE_EXPLANATION,
            AdapterCapability.FILE_EDITING,
            AdapterCapability.WEB_SEARCH,
        ]

    async def configure(self, config: AdapterConfig) -> None:
        """Apply configuration to the adapter."""
        raise NotImplementedError

    async def send_prompt(
        self, prompt: str, context: dict[str, Any] | None = None
    ) -> AdapterResponse:
        """Send a prompt to Claude Code and return the response."""
        raise NotImplementedError

    async def inject_context(self, context: dict[str, Any]) -> None:
        """Inject learning context into the Claude Code session."""
        raise NotImplementedError

    async def health_check(self) -> bool:
        """Return True if Claude Code is reachable."""
        raise NotImplementedError

    async def shutdown(self) -> None:
        """Cleanly shut down the adapter."""
        raise NotImplementedError
