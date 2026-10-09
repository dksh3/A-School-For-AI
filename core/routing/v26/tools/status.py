"""Status tool for School V2.6 — checks component health."""

from __future__ import annotations

from core.routing.v26.tools.base import Tool, ToolResult, fail_open


class StatusTool(Tool):
    """Checks that School V2.6 components are importable and healthy."""

    @property
    def name(self) -> str:
        return "school_status"

    @property
    def description(self) -> str:
        return "Check School V2.6 component status and availability."

    @property
    def schema(self) -> dict:
        return {"type": "object", "properties": {}, "required": []}

    @fail_open
    def execute(self, **kwargs) -> ToolResult:
        components: dict[str, str] = {}
        errors: list[str] = []

        try:
            from core.routing.v26.memory_manager import MemoryManager  # noqa: F401
            components["memory_manager"] = "ok"
        except ImportError as e:
            components["memory_manager"] = f"error: {e}"
            errors.append(f"memory_manager import failed: {e}")

        try:
            from core.routing.v26.experience import Experience, ExperienceOutcome  # noqa: F401
            components["experience"] = "ok"
        except ImportError as e:
            components["experience"] = f"error: {e}"
            errors.append(f"experience import failed: {e}")

        try:
            from core.routing.v26.identity import AgentIdentity, MemoryScope  # noqa: F401
            components["identity"] = "ok"
        except ImportError as e:
            components["identity"] = f"error: {e}"
            errors.append(f"identity import failed: {e}")

        try:
            from core.routing.v26.memory_types import (  # noqa: F401
                MemoryEntry,
                MemoryRequest,
                MemoryResponse,
            )
            components["memory_types"] = "ok"
        except ImportError as e:
            components["memory_types"] = f"error: {e}"
            errors.append(f"memory_types import failed: {e}")

        try:
            from core.routing.v26.memory_store import MemoryStore  # noqa: F401
            components["memory_store"] = "ok"
        except ImportError as e:
            components["memory_store"] = f"error: {e}"
            errors.append(f"memory_store import failed: {e}")

        try:
            from core.routing.v26.semantic_retrieval import scored_query  # noqa: F401
            components["semantic_retrieval"] = "ok"
        except ImportError as e:
            components["semantic_retrieval"] = f"error: {e}"
            errors.append(f"semantic_retrieval import failed: {e}")

        try:
            from core.learner.confidence import estimate_confidence  # noqa: F401
            components["confidence"] = "ok"
        except ImportError as e:
            components["confidence"] = f"error: {e}"
            errors.append(f"confidence import failed: {e}")

        try:
            from core.learner.feature_extractor import FeatureExtractor  # noqa: F401
            components["feature_extractor"] = "ok"
        except ImportError as e:
            components["feature_extractor"] = f"error: {e}"
            errors.append(f"feature_extractor import failed: {e}")

        try:
            from core.learner.similarity import cosine_similarity  # noqa: F401
            components["similarity"] = "ok"
        except ImportError as e:
            components["similarity"] = f"error: {e}"
            errors.append(f"similarity import failed: {e}")

        try:
            from core.routing.v26.consolidation import (  # noqa: F401
                ConsolidationResult,
                consolidate_experiences,
            )
            components["consolidation"] = "ok"
        except ImportError as e:
            components["consolidation"] = f"error: {e}"
            errors.append(f"consolidation import failed: {e}")

        return ToolResult(
            success=len(errors) == 0,
            data={"components": components, "all_ok": len(errors) == 0},
            errors=errors,
            metadata={"tool": self.name},
        )
