# core/context/view.py
from __future__ import annotations

import copy
import re
from typing import Any

from core.context.types import Block, ViewResult

_MARKER_RE = re.compile(r"…")


def _skeletonize(text: str) -> str:
    lines = text.splitlines()
    marked = [ln for ln in lines if _MARKER_RE.search(ln)]
    if marked:
        return "\n".join(marked)
    return lines[0] if lines else text


def _is_skeleton_candidate(message: dict[str, Any]) -> bool:
    if message.get("role") not in {"tool", "assistant"}:
        return False
    content = message.get("content")
    if not isinstance(content, str) or "\n" not in content:
        return False
    return bool(_MARKER_RE.search(content))


def build_view(messages: list[Any], blocks: list[Block]) -> ViewResult:
    """Assemble the prompt-side copy. Fail-open: junk in -> copies out."""
    try:
        valid = [b for b in blocks if b.id and 0 <= b.start < b.end <= len(messages)]
        valid.sort(key=lambda b: b.start)
        out: list[dict[str, Any]] = []
        included: list[str] = []
        i, bidx = 0, 0
        while i < len(messages):
            block = None
            while bidx < len(valid) and valid[bidx].end <= i:
                bidx += 1
            if bidx < len(valid) and valid[bidx].start == i:
                block = valid[bidx]
                bidx += 1
            if block is not None:
                out.append(
                    {
                        "role": "system",
                        "content": f"[school] compacted {block.id}: {block.summary}",
                        "school_block": block.id,
                    }
                )
                i = block.end
                included.append(block.id)
                continue
            message = copy.deepcopy(messages[i])
            if isinstance(message, dict) and _is_skeleton_candidate(message):
                message["content"] = _skeletonize(str(message["content"]))
            out.append(message)
            i += 1
        return ViewResult(messages=out, blocks_included=included, mutated=False)
    except Exception:  # fail open — never raise into the caller
        try:
            safe = copy.deepcopy(list(messages))
        except Exception:
            safe = []
        return ViewResult(messages=safe, blocks_included=[], mutated=False)


def view_segments(messages: list[Any], blocks: list[Block]) -> list[dict[str, Any]]:
    """Per-index edits that turn `messages` into the view. Never mutates.

    Walk mirrors build_view exactly: block start -> marker replacement,
    block interior -> drop (`content: None`), skeleton candidates ->
    skeletonized content. Only changed indices appear in the output.
    """
    try:
        valid = [b for b in blocks if b.id and 0 <= b.start < b.end <= len(messages)]
        valid.sort(key=lambda b: b.start)
        out: list[dict[str, Any]] = []
        i, bidx = 0, 0
        while i < len(messages):
            while bidx < len(valid) and valid[bidx].end <= i:
                bidx += 1
            block = None
            if bidx < len(valid) and valid[bidx].start == i:
                block = valid[bidx]
                bidx += 1
            if block is not None:
                out.append(
                    {
                        "index": i,
                        "role": "system",
                        "content": f"[school] compacted {block.id}: {block.summary}",
                    }
                )
                for j in range(i + 1, block.end):
                    out.append({"index": j, "role": "", "content": None})
                i = block.end
                continue
            message = messages[i]
            if isinstance(message, dict) and _is_skeleton_candidate(message):
                out.append(
                    {
                        "index": i,
                        "role": "",
                        "content": _skeletonize(str(message["content"])),
                    }
                )
            i += 1
        return out
    except Exception:  # fail open - never raise into the caller
        return []


def apply_segments(messages: list[Any], segments: list[dict[str, Any]]) -> list[Any]:
    """Apply view segments the way adapters must. Never mutates `messages`.

    Adapter contract: every segment MUST carry an explicit ``content`` key;
    ``None`` drops the message, any other value replaces it. A segment without
    ``content`` is treated as a drop.
    """
    try:
        edits: dict[int, dict[str, Any]] = {}
        for seg in segments:
            if isinstance(seg, dict) and "index" in seg:
                edits[int(seg["index"])] = seg
        out: list[Any] = []
        for i, message in enumerate(messages):
            edit = edits.get(i)
            if edit is not None and edit.get("content") is None:
                continue
            if edit is None:
                out.append(copy.deepcopy(message))
                continue
            replacement = copy.deepcopy(message)
            if not isinstance(replacement, dict):
                replacement = {"content": ""}
            role = str(edit.get("role") or "")
            if role:
                replacement["role"] = role
            replacement["content"] = str(edit.get("content") or "")
            out.append(replacement)
        return out
    except Exception:  # fail open
        try:
            return copy.deepcopy(list(messages))
        except Exception:
            return []


__all__ = ["apply_segments", "build_view", "view_segments"]
