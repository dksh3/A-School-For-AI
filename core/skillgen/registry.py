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

from core.skillgen.types import Skill, SkillState

REGISTRY_FILE = "skillgen_v1.json"
SIMILARITY_MERGE = 0.85
SIMILARITY_RELATED = 0.55

_thread_lock = threading.Lock()


def _tokens(text: str) -> set[str]:
    return {t for t in "".join(c.lower() if c.isalnum() else " " for c in text).split() if t}


def similarity(a: Skill, b: Skill) -> float:
    """Deterministic lexical similarity in [0, 1] between two skills."""
    ta = _tokens(f"{a.name} {a.description} {' '.join(a.triggers)} {' '.join(a.tags)}")
    tb = _tokens(f"{b.name} {b.description} {' '.join(b.triggers)} {' '.join(b.tags)}")
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    jaccard = inter / union if union else 0.0
    # Name bonus: identical names are duplicates by definition.
    if a.name == b.name:
        return 1.0
    return round(min(1.0, jaccard * 1.15), 4)


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
            if not self._file_path.exists():
                return
            try:
                data = json.loads(self._file_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return
            for item in data.get("skills", []):
                try:
                    skill = Skill.from_dict(item)
                except (KeyError, TypeError, ValueError):
                    continue
                if skill.name:
                    self._skills[skill.name] = skill
            stats = data.get("stats", {})
            if isinstance(stats, dict):
                self._stats.update(stats)

    def save(self) -> None:
        with _thread_lock:
            self._base_path.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(
                {
                    "version": 1,
                    "skills": [s.to_dict() for s in self._skills.values()],
                    "stats": self._stats,
                },
                ensure_ascii=False,
                indent=1,
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

    @property
    def stats(self) -> dict[str, Any]:
        return self._stats

    def log_event(self, event: str, detail: str) -> None:
        events = self._stats.setdefault("events", [])
        events.append({"event": event, "detail": detail[:500]})
        if len(events) > 200:
            del events[:-200]

    # -- CRUD --------------------------------------------------------------

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def add(self, skill: Skill, overwrite: bool = False) -> tuple[bool, str]:
        if skill.name in self._skills and not overwrite:
            return False, f"skill already exists: {skill.name}"
        self._skills[skill.name] = skill
        return True, "ok"

    def remove(self, name: str) -> bool:
        return self._skills.pop(name, None) is not None

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
        for name, other in self._skills.items():
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
            f"{reason}: absorbed {source.name} v{source.version}",
            experience_id=source.created_from[-1] if source.created_from else "",
        )
        if target.state in {SkillState.CANDIDATE, SkillState.VALIDATING}:
            target.state = SkillState.ACTIVE
        self._skills.pop(source.name, None)
        return target


_registries: dict[str, SkillRegistry] = {}
_registry_lock = threading.Lock()


def registry_for(worktree: str | Path) -> SkillRegistry:
    """Per-worktree registry cache (one document per memory dir)."""
    from school.config import resolve_memory_dir

    # Resolve to an absolute path BEFORE keying: a relative worktree (CLI ".")
    # must not collide across directories in the process-level cache.
    base = resolve_memory_dir(worktree).resolve()
    key = os.path.normcase(str(base))
    with _registry_lock:
        reg = _registries.get(key)
        if reg is None:
            reg = SkillRegistry(base)
            _registries[key] = reg
        return reg
