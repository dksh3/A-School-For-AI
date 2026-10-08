"""Deterministic, bounded GitHub query generation and repository search.

Queries derive ONLY from the capability gap supplied by the caller (task
description, missing capability, keywords, skill name) - never the whole
conversation. Hard limits bound query count, results per query, and total
repositories per discovery pass.
"""

from __future__ import annotations

import os
import re
from typing import Any

from core.skillgen.github.cache import TTLCache, shared_cache
from core.skillgen.github.client import GitHubClient, GitHubError
from core.skillgen.github.models import DiscoveryResult, RepoMeta

_STRATEGY_LABELS = ("skill_file", "opencode_skill", "agent_workflow", "topic")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


MAX_GITHUB_QUERIES = _env_int("SCHOOL_SKILLGEN_GITHUB_MAX_QUERIES", 4)
MAX_RESULTS_PER_QUERY = _env_int("SCHOOL_SKILLGEN_GITHUB_MAX_RESULTS", 8)
MAX_REPOSITORIES = _env_int("SCHOOL_SKILLGEN_GITHUB_MAX_REPOS", 15)

_CLEAN = re.compile(r"\s+")


def _clean(text: str, limit: int = 64) -> str:
    """Single-line, bounded, quote-stripped query fragment (privacy-safe)."""
    text = _CLEAN.sub(" ", (text or "").replace('"', " ").replace("\n", " ")).strip()
    return text[:limit].strip()


def generate_queries(
    task: str = "",
    capability_gap: str = "",
    keywords: list[str] | None = None,
    skill_name: str = "",
) -> list[str]:
    """Deterministic query list for one capability gap. Hard-bounded."""
    fragments: list[str] = []
    gap = _clean(capability_gap) or _clean(task, 80)
    if gap:
        fragments.append(gap)
    for kw in keywords or []:
        cleaned = _clean(kw, 32)
        if cleaned and all(cleaned not in f for f in fragments):
            fragments.append(cleaned)
    name = _clean(skill_name, 48)
    if name and all(name not in f for f in fragments):
        fragments.append(name)
    if not fragments:
        return []

    primary = fragments[0]
    strategies = [
        f'"{primary}" skill',
        f"{primary} SKILL.md",
        f"opencode skill {primary}" if len(fragments) == 1 else f"{primary} agent workflow",
        " ".join(fragments[:3]) + " skills",
    ]
    queries: list[str] = []
    for query in strategies:
        query = _clean(query, 100)
        if query and query not in queries:
            queries.append(query)
        if len(queries) >= MAX_GITHUB_QUERIES:
            break
    return queries


def _to_repo_meta(item: dict[str, Any]) -> RepoMeta | None:
    try:
        owner = str((item.get("owner") or {}).get("login") or "")
        name = str(item.get("name") or "")
        if not owner or not name:
            return None
        lic = item.get("license") or {}
        return RepoMeta(
            owner=owner,
            name=name,
            url=str(item.get("html_url") or f"https://github.com/{owner}/{name}"),
            description=str(item.get("description") or ""),
            stars=int(item.get("stargazers_count") or 0),
            forks=int(item.get("forks_count") or 0),
            watchers=int(item.get("watchers_count") or 0),
            language=str(item.get("language") or ""),
            topics=[str(t) for t in (item.get("topics") or [])][:12],
            license=str(lic.get("spdx_id") or "UNKNOWN") or "UNKNOWN",
            license_url=str(lic.get("url") or ""),
            default_branch=str(item.get("default_branch") or "main"),
            created_at=str(item.get("created_at") or ""),
            updated_at=str(item.get("updated_at") or ""),
            open_issues=int(item.get("open_issues_count") or 0),
            archived=bool(item.get("archived", False)),
            fork=bool(item.get("fork", False)),
            size_kb=int(item.get("size") or 0),
        )
    except (TypeError, ValueError, AttributeError):
        return None


def repo_meta_from_api(item: dict[str, Any]) -> RepoMeta | None:
    """Public wrapper: build RepoMeta from a raw API payload (None if malformed)."""
    return _to_repo_meta(item)


def search(
    client: GitHubClient,
    queries: list[str],
    cache: TTLCache | None = None,
) -> DiscoveryResult:
    """Run bounded repository searches. Dedupes by full_name, capped."""
    cache = cache if cache is not None else shared_cache()
    result = DiscoveryResult(queries=list(queries))
    seen: dict[str, RepoMeta] = {}
    for query in queries:
        if len(seen) >= MAX_REPOSITORIES:
            break
        cache_key = f"search:{query}:{MAX_RESULTS_PER_QUERY}"
        items = cache.get(cache_key)
        if items is None:
            try:
                items = client.search_repositories(query, per_page=MAX_RESULTS_PER_QUERY)
            except GitHubError as exc:
                result.errors.append(str(exc))
                if exc.kind in ("rate_limited", "network"):
                    break  # fail closed: stop early, keep partial results
                continue
            cache.set(cache_key, items)
        for item in items:
            if not isinstance(item, dict) or _to_repo_meta(item) is None:
                key = "malformed_item"
                result.filtered_out[key] = result.filtered_out.get(key, 0) + 1
                continue
            meta = _to_repo_meta(item)
            if meta.full_name in seen:
                key = "duplicate_repo"
                result.filtered_out[key] = result.filtered_out.get(key, 0) + 1
                continue
            if len(seen) >= MAX_REPOSITORIES:
                break
            seen[meta.full_name] = meta
    result.repos = list(seen.values())
    result.repos_found = len(seen)
    return result


__all__ = [
    "MAX_GITHUB_QUERIES",
    "MAX_REPOSITORIES",
    "MAX_RESULTS_PER_QUERY",
    "generate_queries",
    "search",
]
