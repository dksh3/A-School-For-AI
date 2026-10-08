"""S7: school_observe — observe agent behavior and extract learnings."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

OBSERVE_FILE = "observations.jsonl"
MAX_OBSERVATIONS = 500


@dataclass
class ObserveResult:
    ok: bool = True
    observation_id: str = ""
    pattern: str = ""
    learning: str = ""
    total: int = 0
    error: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def _observe_path(worktree: str) -> Path:
    return Path(worktree) / ".school" / "agent" / OBSERVE_FILE


def _append_line(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read_lines(path: Path) -> list[dict[str, Any]]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
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
        cat = str(e.get("category", "unknown"))
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

    if not observation or not isinstance(observation, str):
        return ObserveResult(ok=False, error="observation must be a non-empty string")

    try:
        path = _observe_path(worktree)
        oid = f"obs-{len(_read_lines(path)) + 1}"
        record = {
            "id": oid,
            "observation": observation[:500],
            "category": category,
            "evidence": evidence or {},
        }
        _append_line(path, record)
        events = _read_lines(path)
    except (OSError, ValueError) as exc:
        return ObserveResult(ok=False, error=str(exc))
    return ObserveResult(
        ok=True,
        observation_id=oid,
        pattern=_extract_pattern(events),
        learning=observation[:200],
        total=len(events),
    )


__all__ = ["ObserveResult", "observe"]
