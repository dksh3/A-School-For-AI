"""Codex harness adapter stub."""

from typing import Any

from adapters.base import AdapterCapability, AdapterConfig, AdapterResponse, HarnessAdapter


class CodexAdapter(HarnessAdapter):
    """Adapter for the Codex harness.

    Bridges the learning engine to OpenAI Codex's interface.
    """

    @property
    def name(self) -> str:
        return "codex"

    @property
    def capabilities(self) -> list[AdapterCapability]:
        return [
            AdapterCapability.CODE_GENERATION,
            AdapterCapability.CODE_EXPLANATION,
        ]

    async def configure(self, config: AdapterConfig) -> None:
        """Apply configuration to the adapter."""
        raise NotImplementedError

    async def send_prompt(
        self, prompt: str, context: dict[str, Any] | None = None
    ) -> AdapterResponse:
        """Send a prompt to Codex and return the response."""
        raise NotImplementedError

    async def inject_context(self, context: dict[str, Any]) -> None:
        """Inject learning context into the Codex session."""
        raise NotImplementedError

    async def health_check(self) -> bool:
        """Return True if Codex is reachable."""
        raise NotImplementedError

    async def shutdown(self) -> None:
        """Cleanly shut down the adapter."""
        raise NotImplementedError
