"""Tool factory helpers — creates tool instances with shared dependencies."""
from __future__ import annotations

from core.learner.feature_extractor import FeatureExtractor
from core.routing.v26.memory_manager import MemoryManager
from core.routing.v26.memory_store import MemoryStore
from core.routing.v26.persistence import ScopeIsolatedStorage
from core.routing.v26.tools.confidence import ConfidenceTool
from core.routing.v26.tools.conflict import ConflictDetectionTool
from core.routing.v26.tools.deduplicate import DeduplicateTool
from core.routing.v26.tools.diagnose import DiagnoseTool
from core.routing.v26.tools.knowledge import KnowledgeExtractionTool
from core.routing.v26.tools.lifecycle import LifecycleTool
from core.routing.v26.tools.recall import RecallTool
from core.routing.v26.tools.remember import RememberTool
from core.routing.v26.tools.semantic_search import SemanticSearchTool
from core.routing.v26.tools.skillgen import create_skillgen_tools
from core.routing.v26.tools.skillgen_github import create_skillgen_github_tools
from core.routing.v26.tools.status import StatusTool


def create_tools(
    extractor: FeatureExtractor | None = None,
    storage: ScopeIsolatedStorage | None = None,
) -> list:
    if extractor is None:
        extractor = FeatureExtractor()
    manager = MemoryManager(storage=storage, extractor=extractor)
    if storage is not None:
        manager.reload()
    store = MemoryStore()
    if storage is not None:
        for mid in storage.list_keys():
            entry = storage.get(mid)
            if entry is not None:
                store.store(entry)
    return [
        StatusTool(),
        RememberTool(manager=manager),
        RecallTool(manager=manager),
        ConflictDetectionTool(manager=manager),
        ConfidenceTool(),
        SemanticSearchTool(store=store, extractor=extractor),
        DeduplicateTool(store=store, extractor=extractor),
        KnowledgeExtractionTool(manager=manager),
        LifecycleTool(manager=manager),
        DiagnoseTool(manager=manager),
        *create_skillgen_tools(),
        *create_skillgen_github_tools(),
    ]
