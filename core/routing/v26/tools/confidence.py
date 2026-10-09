"""Confidence estimation tool for School V2.6."""

from __future__ import annotations

from core.learner.confidence import estimate_confidence
from core.routing.v26.identity import coerce_float, coerce_int, coerce_text
from core.routing.v26.tools.base import (
    Tool,
    ToolResult,
    fail_open,
)


class ConfidenceTool(Tool):
    """Estimate confidence for a prediction using V2.3 confidence estimation."""

    @property
    def name(self) -> str:
        return "school_confidence"

    @property
    def description(self) -> str:
        return "Estimate confidence for a prediction based on evidence and similarity."

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string", "description": "The prediction content.", "default": ""
                },
                "prediction": {
                    "type": "string", "description": "The predicted output.", "default": ""
                },
                "similarity": {
                    "type": "number",
                    "description": "Base similarity score [0,1].",
                    "default": 0.5,
                },
                "success_count": {
                    "type": "integer",
                    "description": "Number of successful historical uses.",
                    "default": 0,
                },
                "failure_count": {
                    "type": "integer",
                    "description": "Number of failed historical uses.",
                    "default": 0,
                },
                "supporting_weight": {
                    "type": "number",
                    "description": "Total vote weight for the winning output.",
                    "default": 0.0,
                },
                "total_weight": {
                    "type": "number",
                    "description": "Total vote weight across all outputs.",
                    "default": 0.0,
                },
                "supporting_count": {
                    "type": "integer",
                    "description": "Number of neighbors supporting the winner.",
                    "default": 0,
                },
                "total_count": {
                    "type": "integer",
                    "description": "Total number of neighbors.",
                    "default": 0,
                },
                "outputs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Output strings from top-k neighbors.",
                    "default": [],
                },
            },
            "required": [],
        }

    @fail_open
    def execute(self, **kwargs) -> ToolResult:
        # Unconvertible numerics fall back to schema defaults; NaN/inf too.
        similarity = coerce_float(kwargs.get("similarity", 0.5), 0.5)
        success_count = max(0, coerce_int(kwargs.get("success_count", 0), 0))
        failure_count = max(0, coerce_int(kwargs.get("failure_count", 0), 0))
        supporting_weight = coerce_float(kwargs.get("supporting_weight", 0.0), 0.0)
        total_weight = coerce_float(kwargs.get("total_weight", 0.0), 0.0)
        supporting_count = max(0, coerce_int(kwargs.get("supporting_count", 0), 0))
        total_count = max(0, coerce_int(kwargs.get("total_count", 0), 0))
        outputs = _coerce_outputs(kwargs.get("outputs", []))

        result = estimate_confidence(
            similarity=similarity,
            success_count=success_count,
            failure_count=failure_count,
            supporting_weight=supporting_weight,
            total_weight=total_weight,
            supporting_count=supporting_count,
            total_count=total_count,
            outputs=outputs,
        )

        return ToolResult(
            success=True,
            data={
                "confidence": result.confidence,
                "probability": result.probability,
                "band": result.band,
                "similarity": result.similarity,
                "evidence_factor": result.evidence_factor,
                "agreement_bonus": result.agreement_bonus,
                "conflict_penalty": result.conflict_penalty,
                "novelty_penalty": result.novelty_penalty,
                "evidence_strength": result.evidence_strength,
                "supporting_count": result.supporting_count,
                "total_count": result.total_count,
                "conflict_count": result.conflict_count,
                "uncertainty_state": result.uncertainty_state,
            },
            errors=[],
            metadata={"tool": self.name},
        )


def _coerce_outputs(raw: object) -> list[str]:
    """Coerce outputs to a list of strings; garbage degrades to empty list."""
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    try:
        iterator = iter(raw)
    except Exception:  # noqa: BLE001
        return []
    out: list[str] = []
    try:
        for item in iterator:
            out.append(coerce_text(item))
    except Exception:  # noqa: BLE001 - hostile iterators degrade to partial list
        pass
    return out
