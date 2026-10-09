# core/context/engine.py
from __future__ import annotations

import os
import time
from typing import Any

from core.context.circuit import CircuitBreaker
from core.context.layer0 import find_spans, total_tokens
from core.context.layer1 import default_judge, summarize_segment
from core.context.layer2 import emergency_span
from core.context.redact import redact
from core.context.store import BlockStore
from core.context.types import Block, CompressionReport, ViewResult
from core.context.view import build_view
from core.skillgen.budget import ModelCallBudget

_AUTO = object()
_WINDOW_DEFAULT = 128000
_TRIGGER_DEFAULT = 0.8


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


class ContextEngine:
    """Layered compression ladder over verbatim blocks. compress() never raises."""

    def __init__(
        self,
        worktree: str = ".",
        session_id: str = "default",
        judge: Any = _AUTO,
        budget: ModelCallBudget | None = None,
        clock: Any = time.monotonic,
    ) -> None:
        self.worktree = worktree
        self.session_id = session_id
        self.store = BlockStore(worktree, session_id)
        self.circuit = CircuitBreaker(clock=clock)
        self.trigger = _env_float("SCHOOL_COMPRESS_TRIGGER", _TRIGGER_DEFAULT)
        self.window = _env_int("SCHOOL_COMPRESS_WINDOW_TOKENS", _WINDOW_DEFAULT)
        self.judge = default_judge() if judge is _AUTO else judge
        self.budget = budget or ModelCallBudget(
            {}, max_per_task=_env_int("SCHOOL_COMPRESS_MAX_CALLS_PER_TASK", 4)
        )
        self._task_key = f"compress:{session_id}"

    def should_compress(self, messages: list[Any]) -> bool:
        try:
            if os.environ.get("SCHOOL_COMPRESS", "") == "0":
                return False
            if not messages or self.window <= 0:
                return False
            return total_tokens(messages) / self.window >= self.trigger
        except Exception:  # fail open — never raise
            return False

    def _over(self, tokens: int) -> bool:
        return self.window > 0 and tokens / self.window >= self.trigger

    def compress(self, messages: list[Any]) -> CompressionReport:
        try:
            if os.environ.get("SCHOOL_COMPRESS", "") == "0":
                return CompressionReport(
                    skipped="kill_switch", messages=list(messages),
                    circuit=self.circuit.state.value,
                )
            if not isinstance(messages, list) or not messages:
                return CompressionReport(
                    skipped="empty", messages=list(messages),
                    circuit=self.circuit.state.value,
                )
            before = total_tokens(messages)
            if not self._over(before):
                return CompressionReport(
                    tokens_before=before, tokens_after=before, skipped="below_threshold",
                    messages=list(messages), circuit=self.circuit.state.value,
                )

            blocks = self.store.load()
            count_before = len(blocks)
            layer_used = -1

            # Layer 0 — free, deterministic
            for start, end, summary in find_spans(messages, blocks):
                blocks.append(
                    Block.make(
                        Block.next_id(blocks), start, end,
                        [m for m in messages[start:end] if isinstance(m, dict)],
                        redact(summary), 0,
                    )
                )
                layer_used = 0
            after = total_tokens(build_view(messages, blocks).messages)

            # Layer 1 — budgeted model, gated by circuit + budget
            if (
                self._over(after)
                and self.judge is not None
                and self.circuit.allow()
                and self.budget.allow(self._task_key)
            ):
                target = emergency_span(messages, blocks)
                if target is not None:
                    start, end, _ = target
                    self.budget.record(self._task_key)
                    segment = [m for m in messages[start:end] if isinstance(m, dict)]
                    summary = summarize_segment(segment, self.judge, focus=self.session_id)
                    if summary:
                        blocks.append(
                            Block.make(
                                Block.next_id(blocks), start, end, segment, summary, 1
                            )
                        )
                        layer_used = 1
                        self.circuit.record_success()
                    else:
                        self.circuit.record_failure()
                    after = total_tokens(build_view(messages, blocks).messages)

            # Layer 2 — emergency deterministic truncate
            if self._over(after):
                target = emergency_span(messages, blocks)
                if target is not None:
                    start, end, summary = target
                    segment = [m for m in messages[start:end] if isinstance(m, dict)]
                    blocks.append(
                        Block.make(
                            Block.next_id(blocks), start, end, segment, redact(summary), 2
                        )
                    )
                    layer_used = 2
                    after = total_tokens(build_view(messages, blocks).messages)

            if len(blocks) > count_before:
                self.store.save(blocks)
            view = build_view(messages, blocks)
            return CompressionReport(
                triggered=True,
                layer_used=layer_used,
                blocks_added=len(blocks) - count_before,
                tokens_before=before,
                tokens_after=total_tokens(view.messages),
                circuit=self.circuit.state.value,
                messages=view.messages,
            )
        except Exception:  # fail open — engine never raises
            try:
                raw = list(messages) if isinstance(messages, list) else []
            except Exception:  # noqa: BLE001 — hostile sequence (e.g. _BadList)
                raw = []
            return CompressionReport(
                skipped="fail_open", messages=raw, circuit=self.circuit.state.value
            )

    def view(self, messages: list[Any]) -> ViewResult:
        return build_view(messages, self.store.load())

    def restore(self, block_id: str = "") -> dict[str, Any]:
        """Idempotent restore: same messages every call; restores counted."""
        try:
            blocks = self.store.load()
            if not blocks:
                return {"ok": False, "reason": "no_blocks"}
            target = self.store.get(block_id) if block_id else blocks[-1]
            if target is None:
                return {"ok": False, "reason": "block_not_found"}
            target.restores += 1
            self.store.update(target)
            return {
                "ok": True,
                "id": target.id,
                "layer": target.layer,
                "summary": target.summary,
                "restores": target.restores,
                "messages": [dict(m) for m in target.messages],
            }
        except Exception as exc:  # fail open
            return {"ok": False, "reason": "fail_open", "error": type(exc).__name__}


__all__ = ["ContextEngine"]
