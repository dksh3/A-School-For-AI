"""Skill registry: persistence, versioning, duplicate detection.

Stores skills as one JSON document (skillgen_v1.json) next to the V2.6
memory file in the resolved memory dir - same worktree scoping as the rest
of School, atomic writes, reload on restart. Duplicate detection is a
deterministic lexical similarity over name/description/triggers/tags.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from core.skillgen.types import (
    Skill,
    SkillState,
    safe_int,
    safe_str,
)

REGISTRY_FILE = "skillgen_v1.json"
SIMILARITY_MERGE = 0.85
SIMILARITY_RELATED = 0.55

_thread_lock = threading.Lock()


def _tokens(text: Any) -> set[str]:
    return {
        t
        for t in "".join(c.lower() if c.isalnum() else " " for c in safe_str(text, 100_000)).split()
        if t
    }


def _skill_text(skill: Any) -> str:
    """Safe token source for a skill (never raises on hostile fields)."""
    try:
        return " ".join(
            [
                safe_str(skill.name, 200),
                safe_str(skill.description, 4000),
                " ".join(safe_str(t, 200) for t in (skill.triggers or [])),
                " ".join(safe_str(t, 100) for t in (skill.tags or [])),
            ]
        )
    except Exception:
        return safe_str(skill, 4000)


def similarity(a: Skill, b: Skill) -> float:
    """Deterministic lexical similarity in [0, 1] between two skills."""
    try:
        ta = _tokens(_skill_text(a))
        tb = _tokens(_skill_text(b))
        if not ta or not tb:
            return 0.0
        inter = len(ta & tb)
        union = len(ta | tb)
        jaccard = inter / union if union else 0.0
        # Name bonus: identical names are duplicates by definition.
        if safe_str(a.name) == safe_str(b.name) and safe_str(a.name):
            return 1.0
        return round(min(1.0, jaccard * 1.15), 4)
    except Exception:
        return 0.0


class SkillRegistry:
    """Load/store skills for one worktree memory dir."""

    def __init__(self, base_path: Path) -> None:
        self._base_path = Path(base_path)
        self._file_path = self._base_path / REGISTRY_FILE
        self._skills: dict[str, Skill] = {}
        self._stats: dict[str, Any] = {
            "model_calls_total": 0,
            "model_calls_by_task": {},
            "events": [],
        }
        self.load()

    # -- persistence -------------------------------------------------------

    @property
    def path(self) -> Path:
        return self._file_path

    def load(self) -> None:
        with _thread_lock:
            self._skills.clear()
            try:
                if not self._file_path.exists():
                    return
                data = json.loads(self._file_path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    return
                raw_skills = data.get("skills", [])
                for item in list(raw_skills)[:10_000] if isinstance(raw_skills, list) else []:
                    try:
                        skill = Skill.from_dict(item)
                    except Exception:  # noqa: BLE001 - corrupt entry: skip it
                        continue
                    if skill.name:
                        self._skills[skill.name] = skill
                stats = data.get("stats", {})
                if isinstance(stats, dict):
                    self._stats.update(stats)
                self._sanitize_stats()
            except Exception:  # noqa: BLE001 - corrupt JSON: start fresh
                return

    def _sanitize_stats(self) -> None:
        """Stats come from disk: coerce to safe shapes before use."""
        self._stats["model_calls_total"] = safe_int(self._stats.get("model_calls_total", 0))
        raw_calls = self._stats.get("model_calls_by_task", {})
        if isinstance(raw_calls, dict):
            try:
                self._stats["model_calls_by_task"] = {
                    safe_str(k, 100): safe_int(v) for k, v in list(raw_calls.items())[:500]
                }
            except Exception:  # noqa: BLE001 - hostile mapping
                self._stats["model_calls_by_task"] = {}
        else:
            self._stats["model_calls_by_task"] = {}
        self._stats["events"] = self._safe_events(self._stats.get("events", []))

    @staticmethod
    def _safe_events(raw: Any) -> list[dict[str, str]]:
        events: list[dict[str, str]] = []
        try:
            items = list(raw)[:200] if isinstance(raw, (list, tuple)) else []
        except Exception:  # noqa: BLE001 - hostile sequence (__iter__ raises)
            return events
        for item in items:
            try:
                if isinstance(item, dict):
                    events.append(
                        {
                            "event": safe_str(item.get("event", ""), 100),
                            "detail": safe_str(item.get("detail", ""), 500),
                        }
                    )
            except Exception:  # noqa: BLE001 - hostile entry
                continue
        return events

    def save(self) -> bool:
        """Persist the registry. Fail-open: write errors never raise.

        The in-memory state stays authoritative; a failed write is logged as
        a save_error event so callers can still observe the problem.
        """
        with _thread_lock:
            try:
                self._base_path.mkdir(parents=True, exist_ok=True)
                payload = json.dumps(
                    {
                        "version": 1,
                        "skills": [s.to_dict() for s in self._skills.values()],
                        "stats": self._stats,
                    },
                    ensure_ascii=False,
                    indent=1,
                    default=str,
                )
                fd, tmp = tempfile.mkstemp(
                    dir=str(self._base_path), prefix=".skillgen-", suffix=".tmp"
                )
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as fh:
                        fh.write(payload)
                    os.replace(tmp, self._file_path)
                except BaseException:
                    with contextlib.suppress(OSError):
                        os.unlink(tmp)
                    raise
                return True
            except Exception as exc:  # noqa: BLE001 - fail open on persistence errors
                with contextlib.suppress(Exception):
                    self.log_event("save_error", f"{type(exc).__name__}: {exc}")
                return False

    @property
    def stats(self) -> dict[str, Any]:
        return self._stats

    def log_event(self, event: str, detail: str) -> None:
        try:
            events = self._stats.setdefault("events", [])
            if not isinstance(events, list):
                events = []
                self._stats["events"] = events
            events.append(
                {"event": safe_str(event, 100), "detail": safe_str(detail, 500)}
            )
            if len(events) > 200:
                del events[:-200]
        except Exception:  # noqa: BLE001 - observability must never break callers
            return

    # -- CRUD --------------------------------------------------------------

    def get(self, name: str) -> Skill | None:
        try:
            return self._skills.get(name)
        except Exception:  # noqa: BLE001 - unhashable/hostile name
            return None

    def add(self, skill: Skill, overwrite: bool = False) -> tuple[bool, str]:
        try:
            name = skill.name
            if name in self._skills and not overwrite:
                return False, f"skill already exists: {safe_str(name, 100)}"
            self._skills[name] = skill
            return True, "ok"
        except Exception as exc:  # noqa: BLE001 - hostile skill/name
            return False, f"cannot register skill: {type(exc).__name__}"

    def remove(self, name: str) -> bool:
        try:
            return self._skills.pop(name, None) is not None
        except Exception:  # noqa: BLE001 - unhashable/hostile name
            return False

    def all(self) -> list[Skill]:
        return list(self._skills.values())

    def count(self, state: SkillState | None = None) -> int:
        if state is None:
            return len(self._skills)
        return sum(1 for s in self._skills.values() if s.state == state)

    # -- duplicate detection ----------------------------------------------

    def find_similar(self, skill: Skill, exclude: str = "") -> list[tuple[str, float]]:
        """All existing skills with similarity >= SIMILARITY_RELATED."""
        out: list[tuple[str, float]] = []
        try:
            items = list(self._skills.items())
        except Exception:  # noqa: BLE001 - defensive
            return out
        for name, other in items:
            if name == exclude or name == skill.name:
                continue
            sim = similarity(skill, other)
            if sim >= SIMILARITY_RELATED:
                out.append((name, sim))
        out.sort(key=lambda x: x[1], reverse=True)
        return out

    def best_match(self, skill: Skill) -> tuple[str, float] | None:
        similar = self.find_similar(skill)
        return similar[0] if similar else None

    def merge_into(self, target_name: str, source: Skill, reason: str) -> Skill:
        """Consolidate source into target: bump version, absorb provenance."""
        try:
            target = self._skills[target_name]
            for exp_id in source.created_from:
                if exp_id not in target.created_from:
                    target.created_from.append(exp_id)
            if len(source.description) > len(target.description):
                target.description = source.description
            for trig in source.triggers:
                if trig not in target.triggers and len(target.triggers) < 8:
                    target.triggers.append(trig)
            target.success_count += source.success_count
            target.failure_count += source.failure_count
            target.provenance.setdefault("merged_from", []).append(
                {"name": source.name, "version": source.version}
            )
            target.bump_version(
                "merged",
                f"{safe_str(reason, 200)}: absorbed {safe_str(source.name, 100)} "
                f"v{safe_str(source.version, 20)}",
                experience_id=source.created_from[-1] if source.created_from else "",
            )
            if target.state in {SkillState.CANDIDATE, SkillState.VALIDATING}:
                target.state = SkillState.ACTIVE
            self._skills.pop(source.name, None)
            return target
        except Exception:  # noqa: BLE001 - hostile skills: leave registry as-is
            return source


_registries: dict[str, SkillRegistry] = {}
_registry_lock = threading.Lock()


def registry_for(worktree: str | Path) -> SkillRegistry:
    """Per-worktree registry cache (one document per memory dir).

    Fail-open: an unusable/hostile worktree value falls back to a per-process
    temp registry instead of raising, so tools always get a working registry.
    """
    from school.config import resolve_memory_dir

    # Resolve to an absolute path BEFORE keying: a relative worktree (CLI ".")
    # must not collide across directories in the process-level cache.
    try:
        base = resolve_memory_dir(worktree).resolve()
    except Exception:  # noqa: BLE001 - hostile/unusable worktree -> safe fallback
        base = Path(tempfile.gettempdir()) / "school-skillgen-fallback"
    key = os.path.normcase(str(base))
    with _registry_lock:
        reg = _registries.get(key)
        if reg is None:
            reg = SkillRegistry(base)
            _registries[key] = reg
        return reg
