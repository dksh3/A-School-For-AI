"""Factory for creating a fully configured orchestrator."""
from __future__ import annotations

from core.learner.feature_extractor import FeatureExtractor
from core.routing.v26.factory_tools import create_tools
from core.routing.v26.orchestrator import Orchestrator
from core.routing.v26.persistence import ScopeIsolatedStorage
from core.routing.v26.tools.base import ToolRegistry


def create_orchestrator(
    extractor: FeatureExtractor | None = None,
    storage: ScopeIsolatedStorage | None = None,
) -> Orchestrator:
    registry = ToolRegistry()
    tools = create_tools(extractor, storage=storage)
    for tool in tools:
        registry.register(tool)
    return Orchestrator(registry)
