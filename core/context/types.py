# core/context/types.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class CircuitState(StrEnum):
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(slots=True)
class Block:
    """Verbatim message range + summary. Originals are never mutated."""

    id: str
    start: int
    end: int  # exclusive
    messages: list[dict[str, Any]]
    summary: str
    layer: int = 0  # 0 deterministic | 1 model | 2 emergency
    parent_id: str = ""
    tokens_original: int = 0
    tokens_summary: int = 0
    created_at: str = ""
    restores: int = 0

    @property
    def range(self) -> tuple[int, int]:
        return (self.start, self.end)

    @staticmethod
    def next_id(blocks: list[Block]) -> str:
        max_n = 0
        for b in blocks:
            if b.id.startswith("b") and b.id[1:].isdigit():
                n = int(b.id[1:])
                if n > max_n:
                    max_n = n
        return f"b{max_n + 1}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "range": [self.start, self.end],
            "messages": self.messages,
            "summary": self.summary,
            "layer": self.layer,
            "parent_id": self.parent_id,
            "tokens_original": self.tokens_original,
            "tokens_summary": self.tokens_summary,
            "created_at": self.created_at,
            "restores": self.restores,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Block:
        rng = data.get("range") or [0, 0]
        return cls(
            id=str(data.get("id", "")),
            start=int(rng[0]),
            end=int(rng[1]),
            messages=list(data.get("messages") or []),
            summary=str(data.get("summary", "")),
            layer=int(data.get("layer", 0)),
            parent_id=str(data.get("parent_id", "")),
            tokens_original=int(data.get("tokens_original", 0)),
            tokens_summary=int(data.get("tokens_summary", 0)),
            created_at=str(data.get("created_at", "")),
            restores=int(data.get("restores", 0)),
        )

    @classmethod
    def make(
        cls,
        block_id: str,
        start: int,
        end: int,
        messages: list[dict[str, Any]],
        summary: str,
        layer: int,
    ) -> Block:
        now = datetime.now(UTC).isoformat(timespec="seconds")
        original = sum(len(str(m)) for m in messages)
        return cls(
            id=block_id,
            start=start,
            end=end,
            messages=[dict(m) for m in messages],
            summary=summary,
            layer=layer,
            tokens_original=max(1, original // 4),
            tokens_summary=max(1, len(summary) // 4),
            created_at=now,
        )


@dataclass(slots=True)
class CompressionReport:
    triggered: bool = False
    layer_used: int = -1  # -1 = nothing compressed
    blocks_added: int = 0
    tokens_before: int = 0
    tokens_after: int = 0
    skipped: str = ""  # kill_switch | below_threshold | circuit | budget | fail_open | ""
    circuit: str = CircuitState.OK.value
    messages: list[dict[str, Any]] | None = None  # view output on success

    def to_dict(self) -> dict[str, Any]:
        before = self.tokens_before
        return {
            "triggered": self.triggered,
            "layer_used": self.layer_used,
            "blocks_added": self.blocks_added,
            "tokens_before": before,
            "tokens_after": self.tokens_after,
            "tokens_saved": max(0, before - self.tokens_after),
            "ratio_after": round(self.tokens_after / before, 4) if before else 0.0,
            "skipped": self.skipped,
            "circuit": self.circuit,
        }


@dataclass(slots=True)
class ViewResult:
    messages: list[dict[str, Any]]
    blocks_included: list[str] = field(default_factory=list)
    mutated: bool = False  # always False by construction; asserted in tests
