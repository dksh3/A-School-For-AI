"""Phase 2 discovery flows: search -> discover -> analyze -> compare -> import.

Single entry layer used by orchestrator tools and the CLI. All GitHub
failures (network, rate limit, malformed, disabled) convert to structured
fail-closed dicts - Phase 1 local skillgen is never affected. Network calls
happen ONLY inside these functions (opt-in: user must call a discovery tool).
"""

from __future__ import annotations

import os
from typing import Any

from core.skillgen.budget import ModelCallBudget
from core.skillgen.github.analyzer import _GITHUB_MAX_MODEL_CALLS, analyze
from core.skillgen.github.cache import TTLCache, shared_cache
from core.skillgen.github.candidate import filter_candidates, find_skill_files
from core.skillgen.github.client import GitHubClient, GitHubError, default_client
from core.skillgen.github.comparator import find_local_duplicate, improvement_report
from core.skillgen.github.extractor import extract_capability
from core.skillgen.github.importer import import_candidate, license_info, review_preview
from core.skillgen.github.models import (
    GitHubCandidate,
    RepoMeta,
    SecurityLevel,
    TrustState,
)
from core.skillgen.github.search import generate_queries, repo_meta_from_api, search
from core.skillgen.github.security import classify_content, classify_repository
from core.skillgen.judge import ModelJudge, default_judge
from core.skillgen.registry import SkillRegistry, registry_for
from core.skillgen.types import SkillScope

MAX_CONTENT_FETCHES = int(
    os.environ.get("SCHOOL_SKILLGEN_GITHUB_MAX_FILES", "5") or 5
)


def _offline(exc: GitHubError) -> dict[str, Any]:
    """Discovery unavailable -> structured failure; Phase 1 keeps working."""
    return {
        "ok": False,
        "offline": True,
        "reason": f"github_{exc.kind}",
        "error": str(exc),
        "kind": exc.kind,
        "detail": (
            "GitHub discovery unavailable; local skillgen (Phase 1) is unaffected."
        ),
    }


def _tokens_for_gap(task: str, capability_gap: str, keywords: list[str]) -> set[str]:
    import re

    text = " ".join([capability_gap or "", task or "", " ".join(keywords or "")])
    stop = {"the", "a", "an", "of", "for", "with", "and", "or", "to", "in", "on", "skill"}
    return {
        t for t in re.findall(r"[a-z0-9]+", text.lower())
        if len(t) > 2 and t not in stop
    }


# ---- flow 1: search ---------------------------------------------------

def search_github(
    task: str = "",
    capability_gap: str = "",
    keywords: list[str] | None = None,
    skill_name: str = "",
    client: GitHubClient | None = None,
    cache: TTLCache | None = None,
) -> dict[str, Any]:
    """Deterministic bounded repository search. Read-only."""
    queries = generate_queries(task, capability_gap, keywords, skill_name)
    if not queries:
        return {
            "ok": False,
            "reason": "empty_query",
            "detail": "Provide a task or capability_gap to search for.",
        }
    try:
        client = client or default_client()
    except GitHubError as exc:
        return _offline(exc)
    result = search(client, queries, cache=cache)
    if result.errors and not result.repos:
        return _offline(GitHubError("http", "; ".join(result.errors)[:300]))
    return {
        "ok": True,
        "queries": result.queries,
        "repos_found": result.repos_found,
        "repos": [
            {
                "full_name": r.full_name,
                "url": r.url,
                "description": r.description[:200],
                "stars": r.stars,
                "license": r.license,
                "archived": r.archived,
                "updated_at": r.updated_at,
            }
            for r in result.repos
        ],
        "errors": result.errors,
    }


# ---- flow 2: discover -------------------------------------------------

def discover(
    task: str = "",
    capability_gap: str = "",
    keywords: list[str] | None = None,
    skill_name: str = "",
    client: GitHubClient | None = None,
    cache: TTLCache | None = None,
    max_files: int | None = None,
) -> dict[str, Any]:
    """Full deterministic pass: search -> trees -> filter -> content -> security."""
    queries = generate_queries(task, capability_gap, keywords, skill_name)
    if not queries:
        return {
            "ok": False,
            "reason": "empty_query",
            "detail": "Provide a task or capability_gap to search for.",
        }
    try:
        client = client or default_client()
    except GitHubError as exc:
        return _offline(exc)
    cache = cache if cache is not None else shared_cache()
    result = search(client, queries, cache=cache)
    if not result.repos:
        if result.errors:
            return _offline(GitHubError("http", "; ".join(result.errors)[:300]))
        result.filtered_out["no_results"] = 1
        return {
            "ok": True,
            "result": result.to_dict(include_content=False),
            "next_step": "Broaden the capability gap; no repositories matched.",
        }

    repos = result.repos
    gap_tokens = _tokens_for_gap(task, capability_gap, keywords or [])
    tree_paths: dict[str, list[str]] = {}
    examined = 0
    for repo in repos:
        if examined >= MAX_CONTENT_FETCHES * 3:
            break
        examined += 1
        try:
            paths = _cached_tree(client, cache, repo)
        except GitHubError as exc:
            result.errors.append(f"{repo.full_name}: {exc}")
            continue
        tree_paths[repo.full_name] = paths
    result.repos_examined = examined

    survivors, rejected = filter_candidates(repos, tree_paths, gap_tokens)
    result.filtered_out.update(rejected)

    fetched = 0
    limit_files = max_files if max_files is not None else MAX_CONTENT_FETCHES
    kept: list[GitHubCandidate] = []
    for candidate in survivors:
        if fetched >= limit_files:
            break
        try:
            content = _cached_file(client, cache, candidate.repo, candidate.content_path)
        except GitHubError as exc:
            result.filtered_out["content_fetch_failed"] = (
                result.filtered_out.get("content_fetch_failed", 0) + 1
            )
            result.errors.append(f"{candidate.key}: {exc}")
            continue
        fetched += 1
        candidate.content = content
        level, reasons = classify_content(content)
        candidate.security_level = level
        candidate.security_reasons = reasons
        if level is SecurityLevel.REJECTED:
            result.filtered_out["unsafe_content"] = (
                result.filtered_out.get("unsafe_content", 0) + 1
            )
            continue
        capability = extract_capability(candidate)
        if not capability or not capability.get("name"):
            result.filtered_out["no_capability"] = (
                result.filtered_out.get("no_capability", 0) + 1
            )
            continue
        candidate.capability_name = capability.get("name", "")[:120]
        candidate.capability_description = capability.get("description", "")[:1000]
        candidate.trust_state = (
            TrustState.UNVERIFIED
            if candidate.security_level is SecurityLevel.SAFE
            else TrustState.REVIEW_REQUIRED
        )
        lic = license_info(candidate)
        candidate.license_warning = lic["license_warning"]
        candidate.license_compatibility = lic["license_compatibility"]
        kept.append(candidate)
    result.candidates = kept
    return {
        "ok": True,
        "result": result.to_dict(include_content=False),
        "next_step": (
            "Use school_skill_analyze_external on a candidate, then "
            "school_skill_compare, then school_skill_import after user review."
        ),
    }


def _cached_tree(client: GitHubClient, cache: TTLCache, repo: RepoMeta) -> list[str]:
    key = f"tree:{repo.full_name}:{repo.default_branch}"
    paths = cache.get(key)
    if paths is None:
        paths = client.get_tree(repo.owner, repo.name, repo.default_branch)
        cache.set(key, paths)
    return paths


def _cached_file(client: GitHubClient, cache: TTLCache, repo: RepoMeta, path: str) -> str:
    key = f"file:{repo.full_name}:{repo.default_branch}:{path}"
    text = cache.get(key)
    if text is None:
        text = client.get_file_content(repo.owner, repo.name, path, repo.default_branch)
        cache.set(key, text)
    return text


def _cached_commit_sha(client: GitHubClient, cache: TTLCache, repo: RepoMeta) -> str:
    """Best-effort branch head SHA for provenance; failures cached as ''."""
    key = f"commit:{repo.full_name}:{repo.default_branch}"
    sha = cache.get(key)
    if sha is None:
        try:
            sha = client.get_commit_sha(repo.owner, repo.name, repo.default_branch)
        except GitHubError:
            sha = ""
        cache.set(key, sha)
    return str(sha)


# ---- shared candidate loader (analyze / compare / import) -------------

def load_candidate(
    owner: str,
    repo: str,
    file_path: str = "",
    client: GitHubClient | None = None,
    cache: TTLCache | None = None,
) -> tuple[GitHubCandidate | None, dict[str, Any] | None]:
    """Fetch + classify one repository's primary skill file. Fail closed."""
    try:
        client = client or default_client()
    except GitHubError as exc:
        return None, _offline(exc)
    cache = cache if cache is not None else shared_cache()
    owner, repo = owner.strip(), repo.strip()
    if not owner or not repo:
        return None, {"ok": False, "reason": "missing_repo", "offline": False}
    try:
        raw = cache.get(f"repo:{owner}/{repo}")
        if raw is None:
            raw = client.get_repository(owner, repo)
            cache.set(f"repo:{owner}/{repo}", raw)
        meta = repo_meta_from_api(raw)
        if meta is None:
            return None, {"ok": False, "reason": "malformed_repo", "offline": False}
        paths = _cached_tree(client, cache, meta)
    except GitHubError as exc:
        return None, _offline(exc)

    spam_level, spam_reasons = classify_repository(meta.name, meta.description)
    skill_files = find_skill_files(paths)
    if file_path:
        if paths and file_path not in paths:
            return None, {
                "ok": False,
                "reason": "file_not_found",
                "detail": f"{file_path} not present in {meta.full_name}.",
            }
        from core.skillgen.github.models import SkillFile

        kind = next((f.kind for f in skill_files if f.path == file_path), "other")
        skill_files = [SkillFile(path=file_path, kind=kind), *skill_files]
        primary = file_path
    else:
        if not skill_files:
            return None, {
                "ok": False,
                "reason": "no_skill_material",
                "detail": f"{meta.full_name} has no skill-like files.",
            }
        primary = skill_files[0].path

    candidate = GitHubCandidate(repo=meta, skill_files=skill_files, content_path=primary)
    if spam_level is SecurityLevel.REJECTED:
        candidate.security_level = SecurityLevel.REJECTED
        candidate.security_reasons = spam_reasons
        return candidate, None
    try:
        content = _cached_file(client, cache, meta, primary)
    except GitHubError as exc:
        return None, _offline(exc)
    candidate.content = content
    level, reasons = classify_content(content)
    candidate.security_level = level
    candidate.security_reasons = reasons
    candidate.trust_state = (
        TrustState.UNVERIFIED if level is SecurityLevel.SAFE else TrustState.REJECTED
    )
    lic = license_info(candidate)
    candidate.license_warning = lic["license_warning"]
    candidate.license_compatibility = lic["license_compatibility"]
    capability = extract_capability(candidate)
    candidate.capability_name = str(capability.get("name", ""))[:120]
    candidate.capability_description = str(capability.get("description", ""))[:1000]
    candidate.commit_sha = _cached_commit_sha(client, cache, meta)
    return candidate, None


# ---- flow 3: analyze --------------------------------------------------

def analyze_external(
    owner: str,
    repo: str,
    file_path: str = "",
    task: str = "",
    registry: SkillRegistry | None = None,
    judge: ModelJudge | None = None,
    client: GitHubClient | None = None,
    cache: TTLCache | None = None,
) -> dict[str, Any]:
    """Budgeted model analysis of one candidate. Does not modify skills."""
    candidate, err = load_candidate(owner, repo, file_path, client, cache)
    if err is not None or candidate is None:
        return err or {"ok": False, "reason": "no_candidate"}
    if candidate.security_level is SecurityLevel.REJECTED:
        candidate.trust_state = TrustState.REJECTED
        return {
            "ok": False,
            "reason": "security_rejected",
            "security_reasons": candidate.security_reasons,
            "review": review_preview(candidate),
        }
    registry = registry or registry_for(".")
    capability = extract_capability(candidate)
    local_similar: list[tuple[str, float]] = []
    probe_dup, probe_sim = find_local_duplicate(
        capability, registry, candidate.repo.full_name
    )
    if probe_dup:
        local_similar = [(probe_dup, probe_sim)]
        candidate.duplicate_of = probe_dup
    judge = judge if judge is not None else default_judge()
    budget = ModelCallBudget(registry.stats, max_per_task=_GITHUB_MAX_MODEL_CALLS)
    task_key = task or f"github:{candidate.repo.full_name}"
    verdict = analyze(
        candidate,
        capability,
        judge=judge,
        budget=budget,
        task_key=task_key,
        local_similar=local_similar,
    )
    registry.save()  # persist budget counters only
    candidate.analysis = verdict
    if verdict.recommended_action == "REJECT":
        candidate.trust_state = TrustState.REJECTED
    elif verdict.recommended_action == "REVIEW" or not verdict.parsed_ok:
        candidate.trust_state = TrustState.REVIEW_REQUIRED
    else:
        candidate.trust_state = TrustState.ANALYZED
    return {
        "ok": True,
        "trust_state": candidate.trust_state.value,
        "review": review_preview(candidate),
        "model_calls": budget.report(task_key),
    }


# ---- flow 4: compare --------------------------------------------------

def compare(
    owner: str,
    repo: str,
    file_path: str = "",
    registry: SkillRegistry | None = None,
    client: GitHubClient | None = None,
    cache: TTLCache | None = None,
) -> dict[str, Any]:
    """Duplicate/improvement comparison against local skills. Read-only."""
    candidate, err = load_candidate(owner, repo, file_path, client, cache)
    if err is not None or candidate is None:
        return err or {"ok": False, "reason": "no_candidate"}
    registry = registry or registry_for(".")
    capability = extract_capability(candidate)
    duplicate_of, sim = find_local_duplicate(capability, registry, candidate.repo.full_name)
    candidate.duplicate_of = duplicate_of
    improvement: dict[str, Any] | None = None
    best_name, best_sim = "", 0.0
    if not duplicate_of:
        from core.skillgen.github.comparator import _probe_skill

        probe = _probe_skill(capability, candidate.repo.full_name)
        best = registry.best_match(probe)
        if best:
            best_name, best_sim = best
            existing = registry.get(best_name)
            if existing is not None:
                improvement = improvement_report(existing, probe)
    return {
        "ok": True,
        "duplicate": bool(duplicate_of),
        "duplicate_of": duplicate_of or None,
        "similarity": sim,
        "best_match": {"name": best_name or None, "similarity": round(best_sim, 4)},
        "improvement": improvement,
        "review": review_preview(candidate),
        "note": (
            "Improvement reports require explicit approval; use "
            "school_skill_evolve to change local skills."
        ),
    }


# ---- flow 5: import ---------------------------------------------------

def import_external(
    owner: str,
    repo: str,
    file_path: str = "",
    approve: bool = False,
    scope: str = "agent",
    acknowledge_license: bool = False,
    registry: SkillRegistry | None = None,
    agent_id: str = "opencode",
    project_id: str = "",
    session_id: str = "",
    client: GitHubClient | None = None,
    cache: TTLCache | None = None,
) -> dict[str, Any]:
    """Explicit-approval import into the local registry (fail closed)."""
    candidate, err = load_candidate(owner, repo, file_path, client, cache)
    if err is not None or candidate is None:
        return err or {"ok": False, "reason": "no_candidate"}
    try:
        scope_value = SkillScope(str(scope).strip().lower())
    except ValueError:
        scope_value = SkillScope.AGENT
    registry = registry or registry_for(".")
    return import_candidate(
        candidate,
        registry,
        approve=approve,
        scope=scope_value,
        agent_id=agent_id,
        project_id=project_id,
        session_id=session_id,
        acknowledge_license=acknowledge_license,
    )


__all__ = [
    "MAX_CONTENT_FETCHES",
    "analyze_external",
    "compare",
    "discover",
    "import_external",
    "load_candidate",
    "search_github",
]
