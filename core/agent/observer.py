"""S7: school_observe — observe agent behavior and extract learnings."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

OBSERVE_FILE = "observations.jsonl"
MAX_OBSERVATIONS = 500
_JSON_MAX_DEPTH = 6


@dataclass
class ObserveResult:
    ok: bool = True
    observation_id: str = ""
    pattern: str = ""
    learning: str = ""
    total: int = 0
    error: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def safe_str(value: Any, limit: int | None = None) -> str:
    """Coerce any value to a UTF-8-clean str; never raises (fail-open).

    Hostile objects may raise from ``__str__``/``__repr__``; lone surrogates
    break UTF-8 writes, so both are neutralised here. Shared by the other
    agent tools to keep result fields genuinely ``str``-typed.
    """
    if isinstance(value, str):
        out = value
    else:
        try:
            out = str(value)
        except Exception:
            try:
                out = repr(value)
            except Exception:
                out = f"<{type(value).__name__}>"
    out = out.encode("utf-8", "replace").decode("utf-8", "replace")
    return out[:limit] if limit is not None and len(out) > limit else out


def json_safe(value: Any, _depth: int = 0, _seen: frozenset[int] = frozenset()) -> Any:
    """Recursively coerce a value into something json.dumps accepts; never raises."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return safe_str(value)
    if _depth >= _JSON_MAX_DEPTH:
        return safe_str(value, 100)
    if isinstance(value, (bytes, bytearray, memoryview)):
        try:
            return bytes(value).decode("utf-8", "replace")
        except Exception:
            return "<bytes>"
    if id(value) in _seen:
        return "<cycle>"
    seen = _seen | {id(value)}
    try:
        if isinstance(value, dict):
            return {
                safe_str(k, 100): json_safe(v, _depth + 1, seen)
                for k, v in list(value.items())
            }
        if isinstance(value, (list, tuple, set, frozenset)):
            return [json_safe(v, _depth + 1, seen) for v in list(value)]
    except Exception:
        return safe_str(value, 100)
    return safe_str(value, 100)


def _observe_path(worktree: str) -> Path:
    return Path(worktree) / ".school" / "agent" / OBSERVE_FILE


def _append_line(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read_lines(path: Path) -> list[dict[str, Any]]:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return []
    out = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out[-MAX_OBSERVATIONS:]


def _extract_pattern(events: list[dict[str, Any]]) -> str:
    categories: dict[str, int] = {}
    for e in events:
        cat = safe_str(e.get("category", "unknown"))
        categories[cat] = categories.get(cat, 0) + 1
    if not categories:
        return ""
    top = max(categories, key=categories.get)
    return f"{top} appears {categories[top]}x"


def observe(
    worktree: str,
    observation: str,
    category: str = "pattern",
    evidence: dict[str, Any] | None = None,
) -> ObserveResult:
    """Record an agent-behaviour observation and extract a pattern."""
    if os.environ.get("SCHOOL_OBSERVE", "") == "0":
        return ObserveResult(ok=True, total=0)

    if not isinstance(observation, str) or not observation:
        return ObserveResult(ok=False, error="observation must be a non-empty string")

    try:
        path = _observe_path(worktree)
        oid = f"obs-{len(_read_lines(path)) + 1}"
        record = {
            "id": oid,
            "observation": safe_str(observation)[:500],
            "category": safe_str(category),
            "evidence": {} if evidence is None else json_safe(evidence),
        }
        _append_line(path, record)
        events = _read_lines(path)
    except Exception as exc:
        return ObserveResult(ok=False, error=safe_str(exc, 300) or type(exc).__name__)
    return ObserveResult(
        ok=True,
        observation_id=oid,
        pattern=_extract_pattern(events),
        learning=observation[:200],
        total=len(events),
    )


__all__ = ["ObserveResult", "json_safe", "observe", "safe_str"]
