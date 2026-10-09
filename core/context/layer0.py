# core/context/layer0.py
from __future__ import annotations

import os
import re
from typing import Any

from core.context.types import Block

_ERR_RE = re.compile(r"(?i)\b(error|exception|traceback|failed|denied|fatal)\b")
_MIN_DUP_CHARS = 40


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def estimate_tokens(text: str) -> int:
    return len(text) // 4


def _s(v: Any) -> str:
    try:
        return v if isinstance(v, str) else ("" if v is None else str(v))
    except Exception:  # noqa: BLE001 — coercion must never raise
        return ""


def message_tokens(message: Any) -> int:
    if not isinstance(message, dict):
        return 0
    try:
        content = message.get("content")
        tool_calls = message.get("tool_calls")
    except Exception:  # noqa: BLE001
        return 0
    return estimate_tokens(_s(content)) + estimate_tokens(_s(tool_calls))


def total_tokens(messages: list[Any]) -> int:
    try:
        return sum(message_tokens(m) for m in messages)
    except Exception:  # noqa: BLE001
        return 0


def protected_from(messages: list[Any]) -> int:
    """First index of the protected tail (newest ~N tokens never compressed)."""
    budget = _env_int("SCHOOL_COMPRESS_TAIL_TOKENS", 20000)
    if budget <= 0:
        budget = 1
    acc = 0
    for i in range(len(messages) - 1, -1, -1):
        acc += message_tokens(messages[i])
        if acc >= budget:
            return i
    return 0  # whole history fits the tail budget -> nothing compressible


def _content(message: dict[str, Any]) -> str:
    value = message.get("content")
    return value if isinstance(value, str) else ""


def _is_tool(message: dict[str, Any]) -> bool:
    return isinstance(message, dict) and message.get("role") == "tool"


def _error_like(message: dict[str, Any]) -> bool:
    return _is_tool(message) and bool(_ERR_RE.search(_content(message)))


def _unsafe_cut(messages: list[Any], boundary: int) -> bool:
    """True if cutting between boundary-1 and boundary splits a tool pair."""
    if boundary <= 0 or boundary >= len(messages):
        return False
    prev, cur = messages[boundary - 1], messages[boundary]
    if not isinstance(prev, dict) or not isinstance(cur, dict):
        return False
    if prev.get("tool_calls"):
        return True
    return cur.get("role") == "tool" and prev.get("role") == "assistant"


def _normalize(message: dict[str, Any]) -> str:
    return re.sub(r"\s+", " ", _content(message)).strip()


def find_spans(
    messages: list[Any],
    existing: list[Block],
) -> list[tuple[int, int, str]]:
    """Layer 0 spans: repeated tool errors/boilerplate + consecutive error runs.

    Pair-safe, non-overlapping, strictly inside the compressible region.
    """
    try:
        protected = protected_from(messages)
        covered: set[int] = set()
        for block in existing:
            covered.update(range(block.start, block.end))

        compressible = [
            i
            for i in range(min(protected, len(messages)))
            if i not in covered and isinstance(messages[i], dict) and _is_tool(messages[i])
        ]

        spans: list[tuple[int, int, str]] = []
        used: set[int] = set()

        # Rule 1: runs of >=2 consecutive error tool messages collapse as one span.
        run: list[int] = []
        for i in compressible:
            if _error_like(messages[i]):
                if run and i == run[-1] + 1:
                    run.append(i)
                else:
                    if len(run) >= 2:
                        spans.append(
                            (
                                run[0],
                                run[-1] + 1,
                                f"[collapsed {len(run)} consecutive errors]",
                            )
                        )
                        used.update(run)
                    run = [i]
                continue
            if len(run) >= 2:
                spans.append(
                    (run[0], run[-1] + 1, f"[collapsed {len(run)} consecutive errors]")
                )
                used.update(run)
            run = []
        if len(run) >= 2:
            spans.append((run[0], run[-1] + 1, f"[collapsed {len(run)} consecutive errors]"))
            used.update(run)

        # Rule 2: non-adjacent duplicates keep the first, block the rest.
        groups: dict[str, list[int]] = {}
        for i in compressible:
            if i in used:
                continue
            norm = _normalize(messages[i])
            if len(norm) < _MIN_DUP_CHARS:
                continue
            groups.setdefault(norm, []).append(i)
        for indices in groups.values():
            if len(indices) < 2:
                continue
            for i in indices[1:]:
                if i not in used:
                    spans.append((i, i + 1, "[duplicate error omitted]"))
                    used.add(i)

        # Pair-safety extension + clamping + overlap removal.
        result: list[tuple[int, int, str]] = []
        for start, end, summary in sorted(spans):
            while end < protected and _unsafe_cut(messages, end):
                end += 1
            while start > 0 and _unsafe_cut(messages, start):
                start -= 1
            if start >= end or end > protected or start >= protected:
                continue
            if any(s < end and start < e for s, e, _ in result):
                continue
            if any(start < b.end and b.start < end for b in existing):
                continue
            result.append((start, end, summary))
        return result
    except Exception:  # fail open — layer 0 must never raise
        return []
