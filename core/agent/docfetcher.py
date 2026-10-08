"""S7: school_fetch_docs — cached live-doc fetcher with token-efficient summaries."""

from __future__ import annotations

import contextlib
import json
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.agent.observer import observe

DOC_CACHE_FILE = "docs_cache.json"
MAX_CACHE_ENTRIES = 100
MAX_DOC_CHARS = 2000
SKELETON_HEAD = 200
SKELETON_TAIL = 200
FETCH_TIMEOUT_S = 5.0
DOC_ENDPOINT = "https://context7.com/api/v1/search"


@dataclass
class DocResult:
    ok: bool
    query: str
    source: str
    content: str
    cached: bool
    tokens_saved: int
    learnings: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# persistence / estimation helpers
# ---------------------------------------------------------------------------


def _cache_path(worktree: Path) -> Path:
    return worktree / ".school" / "agent" / DOC_CACHE_FILE


def _est_tokens(text: str) -> int:
    return len(text) // 4


def _skeletonize(text: str) -> tuple[str, int]:
    """Compress large content: keep head + tail with a token marker in between."""
    if len(text) <= MAX_DOC_CHARS:
        return text, 0
    head = text[:SKELETON_HEAD]
    tail = text[-SKELETON_TAIL:]
    saved = _est_tokens(text[SKELETON_HEAD:-SKELETON_TAIL])
    return f"{head}[... {saved} tokens compressed ...]{tail}", saved


def _fetched_at(entry: dict[str, Any]) -> float:
    try:
        return float(entry.get("fetched_at", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _load_cache(worktree: Path) -> dict[str, Any]:
    try:
        raw = _cache_path(worktree).read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    data = json.loads(raw)
    return data if isinstance(data, dict) else {}


def _prune(cache: dict[str, Any]) -> None:
    """LRU evict: drop least-recently-used entries beyond the bound."""
    while len(cache) > MAX_CACHE_ENTRIES:
        oldest = min(cache, key=lambda key: _fetched_at(cache[key]))
        del cache[oldest]


def _save_cache(worktree: Path, cache: dict[str, Any]) -> None:
    _prune(cache)
    path = _cache_path(worktree)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# fetch helpers
# ---------------------------------------------------------------------------


def _build_url(query: str, library: str | None, version: str | None) -> str:
    if query.startswith(("http://", "https://")):
        return query
    params: dict[str, str] = {"query": query}
    if library:
        params["library"] = library
    if version:
        params["version"] = version
    return f"{DOC_ENDPOINT}?{urllib.parse.urlencode(params)}"


def _fetch_url(url: str, timeout: float = FETCH_TIMEOUT_S) -> str:
    """Fetch raw doc text over HTTP. Raises on network failure."""
    req = urllib.request.Request(url, headers={"User-Agent": "school-docfetcher/2.6"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read().decode("utf-8", "replace")


def _search_key(query: str, library: str | None, version: str | None) -> str:
    return f"{library}:{version or ''}:{query}" if library else query


def _cached_result(query: str, entry: dict[str, Any]) -> DocResult:
    content, saved = _skeletonize(str(entry.get("content", "")))
    tokens_saved = saved or max(0, int(entry.get("tokens", 0)) - _est_tokens(content))
    return DocResult(
        ok=True,
        query=query,
        source="cache",
        content=content,
        cached=True,
        tokens_saved=tokens_saved,
    )


def _record(worktree: Path, query: str) -> str | None:
    """Record the fetch in the observer learning trail; never raises."""
    with contextlib.suppress(Exception):
        obs = observe(str(worktree), f"docs fetched: {query}", category="research")
        return obs.pattern or None
    return None


def _fallback(
    worktree: Path,
    query: str,
    cache: dict[str, Any],
    key: str,
) -> DocResult | None:
    entry = cache.get(key)
    if isinstance(entry, dict) and "content" in entry:
        result = _cached_result(query, entry)
        result.learnings = _record(worktree, query)
        return result
    return None


def _fetch(
    worktree: Path,
    query: str,
    library: str | None,
    version: str | None,
    use_cache: bool,
) -> DocResult:
    key = _search_key(query, library, version)
    cache = _load_cache(worktree)

    if use_cache and isinstance(cache.get(key), dict) and "content" in cache[key]:
        entry = cache[key]
        entry["fetched_at"] = time.time()
        _save_cache(worktree, cache)
        result = _cached_result(query, entry)
        result.learnings = _record(worktree, query)
        return result

    url = _build_url(query, library, version)
    try:
        raw = _fetch_url(url)
    except Exception as exc:  # network errors are fail-open
        stale = _fallback(worktree, query, cache, key)
        if stale is not None:
            return stale
        return DocResult(
            ok=False,
            query=query,
            source=url,
            content="",
            cached=False,
            tokens_saved=0,
            learnings=_record(worktree, query),
            error=f"fetch failed: {exc}",
        )

    content, saved = _skeletonize(raw)
    cache[key] = {
        "content": content,
        "source": url,
        "fetched_at": time.time(),
        "tokens": _est_tokens(raw),
    }
    _save_cache(worktree, cache)
    return DocResult(
        ok=True,
        query=query,
        source=url,
        content=content,
        cached=False,
        tokens_saved=saved,
        learnings=_record(worktree, query),
    )


def fetch_docs(
    worktree: Path | str,
    query: str,
    library: str | None = None,
    version: str | None = None,
    use_cache: bool = True,
) -> DocResult:
    """Fetch up-to-date library docs, cached locally under ``.school/agent/``.

    The cache key is ``library:version:query`` (version pinning), cached content
    is skeletonized for token efficiency, and every fetch attempt is recorded in
    the observer learning trail. Network failure falls back to any cached entry.
    """
    if os.environ.get("SCHOOL_DOCS", "") == "0":
        return DocResult(
            ok=True,
            query=query,
            source="disabled",
            content="",
            cached=False,
            tokens_saved=0,
        )
    if not query or not str(query).strip():
        return DocResult(
            ok=False,
            query=str(query or ""),
            source="",
            content="",
            cached=False,
            tokens_saved=0,
            error="empty query",
        )
    try:
        return _fetch(Path(worktree), query, library, version, use_cache)
    except (OSError, ValueError, TypeError) as exc:
        return DocResult(
            ok=False,
            query=query,
            source="",
            content="",
            cached=False,
            tokens_saved=0,
            error=str(exc),
        )


__all__ = ["DOC_ENDPOINT", "DocResult", "fetch_docs"]
