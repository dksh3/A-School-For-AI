"""Persistent storage for School V2.6 long-term memory.

Provides scope-isolated, versioned, atomic JSON persistence for
V2.6 memory entries. Rejects malformed/truncated state explicitly.

Design principles:
- Atomic writes: temp file + flush + fsync + os.replace with bounded
  backoff retry; the committed file is never truncated in place
- Corrupt existing state is an explicit PersistenceError — a file that
  exists but cannot be parsed is NEVER treated as an empty store
  (only a genuinely missing file initializes empty)
- Cross-process exclusive lock scoped to the store file, with
  reload-before-write inside the lock, so concurrent writers (one fresh
  bridge process per tool call) cannot overwrite newer state with a
  stale in-memory copy
- Failures raise PersistenceError so callers never report a successful
  write that did not reach durable storage
- Schema version tracking for future migration
- Scope isolation preserved across persistence
- Cross-session queries without weakening isolation
- No global mutable state (aside from per-path in-process lock registry)
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

from core.routing.v26.identity import MemoryScope
from core.routing.v26.memory_types import MemoryEntry, MemoryKind

# Current schema version
SCHEMA_VERSION = "2.6.0"


class PersistenceError(RuntimeError):
    """Raised when persistent store state cannot be safely read or written.

    Distinguishes 'file does not exist' (valid empty initial state) from
    'file exists but is invalid' (corruption — must never be treated as
    an empty store). Also raised when an atomic replacement cannot be
    completed safely, so callers never receive a success for a write
    that did not reach durable storage.
    """


# Cross-process lock acquisition: bounded wait, then explicit failure.
_LOCK_TIMEOUT_SECONDS = 30.0
_LOCK_POLL_SECONDS = 0.02

# Atomic replacement: bounded backoff retry for transient Windows sharing
# violations (another process briefly holds the target file open).
_REPLACE_ATTEMPTS = 30
_REPLACE_INITIAL_DELAY = 0.05
_REPLACE_MAX_DELAY = 0.5

# Transient read retries (sharing violations) before declaring corruption.
_READ_ATTEMPTS = 3
_READ_DELAY = 0.01

# Per-path in-process locks (msvcrt/flock locks are per-handle, so two
# threads in one process would otherwise not exclude each other).
# Registry guarded by _registry_guard; individual locks must NOT be
# nested within the same thread (store/remove/clear do not nest).
_process_locks: dict[str, threading.Lock] = {}
_registry_guard = threading.Lock()


def _thread_lock_for(path: Path) -> threading.Lock:
    """Return the per-store in-process lock (scoped to one store file)."""
    key = os.path.normcase(os.path.abspath(str(path)))
    with _registry_guard:
        lock = _process_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _process_locks[key] = lock
        return lock


def _lock_fd(fd: int) -> None:
    """Acquire an exclusive cross-process lock on fd (non-blocking)."""
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[attr-defined]


def _unlock_fd(fd: int) -> None:
    """Release the cross-process lock on fd."""
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# ScopeIsolatedStorage
# ---------------------------------------------------------------------------


class ScopeIsolatedStorage:
    """JSON-based persistent storage with scope isolation.

    Memories are stored in a flat list within a single JSON file,
    with scope fields enabling filtering. This avoids directory sprawl
    while maintaining logical isolation.

    All mutations run under a per-store cross-process lock and reload
    the latest committed state from disk before applying the mutation
    (reload-before-write), so concurrent writers cannot clobber each
    other's committed entries.
    """

    def __init__(self, base_path: Path, max_entries: int = 100_000) -> None:
        """Initialize storage.

        Args:
            base_path: Base directory for storage files.
            max_entries: Maximum entries to store before warning.
        """
        self._base_path = base_path
        self._max_entries = max_entries
        self._file_path = base_path / "v26_memory.json"
        self._cache: dict[str, MemoryEntry] | None = None

    def _ensure_dir(self) -> None:
        """Ensure the storage directory exists."""
        self._base_path.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _exclusive_lock(self) -> Iterator[None]:
        """Hold the per-store lock: in-process mutex + cross-process file lock.

        The OS releases the file lock when the process dies or the
        handle closes, so a crashed writer cannot leave a stale lock.
        """
        self._ensure_dir()
        thread_lock = _thread_lock_for(self._file_path)
        with thread_lock:
            lock_path = self._file_path.with_name(self._file_path.name + ".lock")
            fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o666)
            acquired = False
            try:
                deadline = time.monotonic() + _LOCK_TIMEOUT_SECONDS
                while True:
                    try:
                        _lock_fd(fd)
                        acquired = True
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise PersistenceError(
                                f"timed out acquiring persistence lock after "
                                f"{_LOCK_TIMEOUT_SECONDS}s: {self._file_path}"
                            ) from None
                        time.sleep(_LOCK_POLL_SECONDS)
                yield
            finally:
                if acquired:
                    with suppress(OSError):
                        _unlock_fd(fd)
                os.close(fd)

    def _load_raw(self) -> dict[str, Any]:
        """Load raw data from disk.

        A genuinely missing file yields valid empty initial state.
        An existing file that is empty, truncated, malformed, or
        structurally invalid raises PersistenceError — it is NEVER
        silently treated as an empty store.
        """
        if not self._file_path.exists():
            return {"version": SCHEMA_VERSION, "entries": []}

        text: str | None = None
        last_error: Exception | None = None
        for attempt in range(_READ_ATTEMPTS):
            try:
                text = self._file_path.read_text(encoding="utf-8")
                break
            except UnicodeDecodeError as exc:
                raise PersistenceError(
                    f"store file is not valid UTF-8 (corrupt): {self._file_path}"
                ) from exc
            except PermissionError as exc:
                # Transient sharing violation: retry briefly, then fail loud.
                last_error = exc
                time.sleep(_READ_DELAY * (attempt + 1))
            except OSError as exc:
                raise PersistenceError(
                    f"cannot read store {self._file_path}: {exc}"
                ) from exc

        if text is None:
            raise PersistenceError(
                f"cannot read store {self._file_path}: {last_error}"
            ) from last_error

        if text.strip() == "":
            raise PersistenceError(
                f"store file exists but is empty (corrupt): {self._file_path}"
            )

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise PersistenceError(
                f"store file contains malformed/truncated JSON (corrupt): "
                f"{self._file_path}: {exc}"
            ) from exc

        if not isinstance(data, dict):
            raise PersistenceError(
                f"store root is not a JSON object (corrupt): {self._file_path}"
            )
        if "entries" in data and not isinstance(data["entries"], list):
            raise PersistenceError(
                f"store 'entries' is not a list (corrupt): {self._file_path}"
            )
        data.setdefault("entries", [])
        return data

    def _load_entries(self) -> dict[str, MemoryEntry]:
        """Load all entries into a dict keyed by memory_id."""
        data = self._load_raw()
        entries: dict[str, MemoryEntry] = {}
        for raw in data.get("entries", []):
            try:
                entry = MemoryEntry.from_dict(raw)
                if entry.memory_id:
                    entries[entry.memory_id] = entry
            except (KeyError, ValueError, TypeError):
                continue  # Skip malformed entries
        return entries

    def _get_cache(self) -> dict[str, MemoryEntry]:
        """Get or build the in-memory cache."""
        if self._cache is None:
            self._cache = self._load_entries()
        return self._cache

    def _replace_with_retry(self, tmp_path: Path) -> None:
        """Atomically replace the store with tmp_path, retrying transient errors.

        On Windows, os.replace fails with PermissionError while another
        process holds the target open. Retry with bounded backoff; if the
        replacement still cannot complete, raise PersistenceError with the
        previous committed file left fully intact. The live file is NEVER
        truncated or rewritten in place.
        """
        delay = _REPLACE_INITIAL_DELAY
        last_error: OSError | None = None
        for attempt in range(_REPLACE_ATTEMPTS):
            try:
                os.replace(tmp_path, self._file_path)
                return
            except OSError as exc:
                last_error = exc
                if attempt + 1 >= _REPLACE_ATTEMPTS:
                    break
                time.sleep(min(delay, _REPLACE_MAX_DELAY))
                delay *= 1.5
        raise PersistenceError(
            f"atomic replacement failed after {_REPLACE_ATTEMPTS} attempts; "
            f"existing store left intact: {self._file_path}: {last_error}"
        ) from last_error

    def _persist(self, entries: dict[str, MemoryEntry]) -> None:
        """Persist entries atomically: temp file, flush, fsync, replace."""
        self._ensure_dir()

        data = {
            "version": SCHEMA_VERSION,
            "entries": [e.to_dict() for e in entries.values()],
        }
        raw = json.dumps(data, indent=2, ensure_ascii=False)

        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=self._base_path, suffix=".tmp"
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
            self._replace_with_retry(Path(tmp_path))
        except BaseException:
            # Clean up temp file on failure; committed file untouched.
            with suppress(OSError):
                os.unlink(tmp_path)
            raise

        self._cache = entries

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def store(self, entry: MemoryEntry) -> None:
        """Store a memory entry (create or update).

        Runs under the store lock: reload latest state from disk, apply
        the mutation, atomically persist. Never writes from a stale cache.
        """
        with self._exclusive_lock():
            latest = self._load_entries()
            latest[entry.memory_id] = entry
            self._persist(latest)

    def get(self, memory_id: str) -> MemoryEntry | None:
        """Retrieve a memory entry by ID."""
        cache = self._get_cache()
        return cache.get(memory_id)

    def remove(self, memory_id: str) -> bool:
        """Remove a memory entry by ID (locked reload-before-write)."""
        with self._exclusive_lock():
            latest = self._load_entries()
            if memory_id not in latest:
                self._cache = latest
                return False
            del latest[memory_id]
            self._persist(latest)
            return True

    def list_keys(
        self,
        scope: MemoryScope | None = None,
        kind: MemoryKind | None = None,
        project_id: str | None = None,
        session_id: str | None = None,
    ) -> list[str]:
        """List memory IDs with optional filtering.

        Args:
            scope: If provided, filter by scope (exact or parent match).
            kind: If provided, filter by memory kind.
            project_id: If provided, filter by project.
            session_id: If provided, filter by session.

        Returns:
            List of matching memory IDs.
        """
        cache = self._get_cache()
        results: list[str] = []

        for entry in cache.values():
            # Kind filter
            if kind is not None and entry.kind != kind:
                continue

            # Project filter
            if project_id and (
                entry.scope.project is None
                or entry.scope.project.project_id != project_id
            ):
                continue

            # Session filter
            if session_id and (
                entry.scope.session is None
                or entry.scope.session.session_id != session_id
            ):
                continue

            # Scope filter (if provided, entry must be within the scope)
            if scope is not None:
                if entry.scope.agent.agent_id != scope.agent.agent_id:
                    continue
                if scope.project and scope.project.project_id and (
                    entry.scope.project is None
                    or entry.scope.project.project_id != scope.project.project_id
                ):
                    continue
                if scope.session and scope.session.session_id and (
                    entry.scope.session is None
                    or entry.scope.session.session_id != scope.session.session_id
                ):
                    continue

            results.append(entry.memory_id)

        return results

    def load(
        self,
        memory_id: str,
        scope: MemoryScope | None = None,
    ) -> MemoryEntry | None:
        """Load a specific memory with optional scope validation.

        Args:
            memory_id: The memory ID to load.
            scope: If provided, validate scope access.

        Returns:
            MemoryEntry if found and scope-valid, None otherwise.
        """
        entry = self.get(memory_id)
        if entry is None:
            return None

        if scope is not None:
            if entry.scope.agent.agent_id != scope.agent.agent_id:
                return None
            if scope.project and scope.project.project_id and (
                entry.scope.project is None
                or entry.scope.project.project_id != scope.project.project_id
            ):
                return None

        return entry

    def count(
        self,
        scope: MemoryScope | None = None,
        kind: MemoryKind | None = None,
    ) -> int:
        """Count entries with optional filtering."""
        return len(self.list_keys(scope=scope, kind=kind))

    def clear(
        self,
        scope: MemoryScope | None = None,
    ) -> int:
        """Clear entries, optionally scoped (locked reload-before-write).

        Args:
            scope: If provided, only clear entries within scope.

        Returns:
            Number of entries cleared.
        """
        with self._exclusive_lock():
            latest = self._load_entries()

            if scope is None:
                count = len(latest)
                self._persist({})
                return count

            to_remove = []
            for mid, entry in latest.items():
                if entry.scope.agent.agent_id != scope.agent.agent_id:
                    continue
                if scope.project and scope.project.project_id and (
                    entry.scope.project is None
                    or entry.scope.project.project_id != scope.project.project_id
                ):
                    continue
                if scope.session and scope.session.session_id and (
                    entry.scope.session is None
                    or entry.scope.session.session_id != scope.session.session_id
                ):
                    continue
                to_remove.append(mid)

            for mid in to_remove:
                del latest[mid]

            if to_remove:
                self._persist(latest)
            else:
                self._cache = latest

            return len(to_remove)

    def reload(self) -> int:
        """Force reload from disk, discarding cache.

        Returns:
            Number of entries loaded.

        Raises:
            PersistenceError: if the existing file is corrupt (never
                silently loads an empty state).
        """
        self._cache = self._load_entries()
        return len(self._cache)

    def size(self) -> int:
        """Return current number of cached entries."""
        return len(self._get_cache())

    def migrate(self, from_version: str) -> bool:
        """Attempt to migrate from an older schema version.

        Currently a no-op since SCHEMA_VERSION is 2.6.0 and there
        are no prior versions. Provides migration hook for future use.

        Returns:
            True if migration was performed, False if already current.
        """
        data = self._load_raw()
        current = data.get("version", "")
        if current == SCHEMA_VERSION:
            return False
        # Future: implement version-specific migrations
        return False
