"""OpenCode harness adapter stub."""

from typing import Any

from adapters.base import AdapterCapability, AdapterConfig, AdapterResponse, HarnessAdapter


class OpenCodeAdapter(HarnessAdapter):
    """Adapter for the OpenCode harness.

    Bridges the learning engine to OpenCode's CLI and API surface.
    """

    @property
    def name(self) -> str:
        return "opencode"

    @property
    def capabilities(self) -> list[AdapterCapability]:
        return [
            AdapterCapability.CODE_GENERATION,
            AdapterCapability.CODE_EXPLANATION,
            AdapterCapability.FILE_EDITING,
            AdapterCapability.TERMINAL_ACCESS,
        ]

    async def configure(self, config: AdapterConfig) -> None:
        """Apply configuration to the adapter."""
        raise NotImplementedError

    async def send_prompt(
        self, prompt: str, context: dict[str, Any] | None = None
    ) -> AdapterResponse:
        """Send a prompt to OpenCode and return the response."""
        raise NotImplementedError

    async def inject_context(self, context: dict[str, Any]) -> None:
        """Inject learning context into the OpenCode session."""
        raise NotImplementedError

    async def health_check(self) -> bool:
        """Return True if OpenCode is reachable."""
        raise NotImplementedError

    async def shutdown(self) -> None:
        """Cleanly shut down the adapter."""
        raise NotImplementedError
