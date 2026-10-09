"""Generic harness adapter stub."""

from typing import Any

from adapters.base import AdapterCapability, AdapterConfig, AdapterResponse, HarnessAdapter


class GenericAdapter(HarnessAdapter):
    """Adapter for generic or custom harnesses.

    A fallback adapter that can be configured to talk to any harness
    exposing a simple prompt/response interface.
    """

    @property
    def name(self) -> str:
        return "generic"

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
        """Send a prompt to the generic harness and return the response."""
        raise NotImplementedError

    async def inject_context(self, context: dict[str, Any]) -> None:
        """Inject learning context into the generic harness session."""
        raise NotImplementedError

    async def health_check(self) -> bool:
        """Return True if the generic harness is reachable."""
        raise NotImplementedError

    async def shutdown(self) -> None:
        """Cleanly shut down the adapter."""
        raise NotImplementedError
