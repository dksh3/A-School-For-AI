# core/context/layer2.py
from __future__ import annotations

from typing import Any

from core.context.layer0 import protected_from
from core.context.redact import redact
from core.context.types import Block


def _first_line(messages: list[Any], start: int, end: int) -> str:
    for i in range(start, end):
        message = messages[i]
        if isinstance(message, dict):
            content = redact(str(message.get("content") or "").strip())
            if content:
                return content.splitlines()[0][:80]
    return "segment"


def emergency_span(
    messages: list[Any],
    existing: list[Block],
) -> tuple[int, int, str] | None:
    """Oldest free segment outside existing blocks, inside the compressible region."""
    try:
        protected = protected_from(messages)
        covered: set[int] = set()
        for block in existing:
            covered.update(range(block.start, block.end))
        free = [
            i
            for i in range(min(protected, len(messages)))
            if i not in covered and isinstance(messages[i], dict)
        ]
        if not free:
            return None
        # oldest contiguous run of free indices
        run_start = free[0]
        run_end = run_start + 1
        for i in free[1:]:
            if i == run_end:
                run_end = i + 1
            else:
                break
        count = run_end - run_start
        summary = (
            f"[truncated {count} messages (emergency): {_first_line(messages, run_start, run_end)}]"
        )
        return run_start, run_end, summary
    except Exception:  # fail open
        return None


__all__ = ["emergency_span"]
