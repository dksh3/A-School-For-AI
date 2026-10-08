"""Deterministic candidate filtering for GitHub discovery (Phase 2).

Cheap gate FIRST: skill-like material, accessibility, activity, size,
relevance, spam, duplicates. Only surviving candidates reach model analysis,
mirroring Phase 1's "deterministic signals first" principle.
"""

from __future__ import annotations

import os
import re

from core.skillgen.github.models import (
    GitHubCandidate,
    RepoMeta,
    SecurityLevel,
    SkillFile,
    TrustState,
)
from core.skillgen.github.security import classify_content, classify_repository

# Skill-oriented file patterns (spec section 9). Not every hit is useful -
# content is analyzed later; this is only the presence gate.
_SKILL_FILE_KINDS: tuple[tuple[str, str], ...] = (
    (r"(^|/)SKILL\.md$", "skill_md"),
    (r"(^|/)AGENTS\.md$", "agents_md"),
    (r"(^|/)CLAUDE\.md$", "agents_md"),
    (r"(^|/)README\.md$", "readme"),
    (r"(^|/)\.cursorrules$", "rules"),
    (r"(^|/)(\.opencode|\.agents|\.claude|\.cursor)/", "prompt"),
    (r"(^|/)(prompts|skills|workflows)/[^/]+\.(md|mdx|txt)$", "prompt"),
    (r"(^|/)mcp(\.json|/)", "mcp_config"),
    (r"(^|/)(\.github/workflows|tools)/[^/]+\.(yml|yaml|md)$", "workflow"),
)

_STOPWORDS = frozenset(
    ["the", "a", "an", "of", "for", "with", "and", "or", "to",
     "in", "on", "how", "use", "using", "skill", "skills", "agent", "agents"]
)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


MAX_REPO_SIZE_KB = _env_int("SCHOOL_SKILLGEN_GITHUB_MAX_REPO_KB", 500000)
MIN_RELEVANCE = float(os.environ.get("SCHOOL_SKILLGEN_GITHUB_MIN_RELEVANCE", "0.12") or 0.12)


def classify_file(path: str) -> str:
    for pattern, kind in _SKILL_FILE_KINDS:
        if re.search(pattern, path, re.IGNORECASE):
            return kind
    return ""


def find_skill_files(paths: list[str]) -> list[SkillFile]:
    files: list[SkillFile] = []
    for path in paths:
        kind = classify_file(path)
        if kind:
            files.append(SkillFile(path=path, kind=kind))
    # Prefer the most skill-specific files first.
    priority = {
        "skill_md": 0, "agents_md": 1, "prompt": 2, "rules": 3,
        "workflow": 4, "readme": 5, "mcp_config": 6,
    }
    files.sort(key=lambda f: (priority.get(f.kind, 9), len(f.path)))
    return files


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {t for t in words if t not in _STOPWORDS and len(t) > 2}


def relevance_score(repo: RepoMeta, skill_files: list[SkillFile], gap_tokens: set[str]) -> float:
    """Token overlap between the capability gap and repository signals."""
    if not gap_tokens:
        return 0.5  # no gap context -> neutral, still passes the presence gate
    repo_tokens = _tokens(repo.name.replace("-", " ")) | _tokens(repo.description)
    repo_tokens |= {t for topic in repo.topics for t in _tokens(topic)}
    file_tokens: set[str] = set()
    for f in skill_files:
        file_tokens |= _tokens(f.path.replace("/", " ").replace("_", " ").replace(".", " "))
    if not repo_tokens and not file_tokens:
        return 0.0
    overlap = len(gap_tokens & (repo_tokens | file_tokens))
    return min(1.0, (overlap / max(1, len(gap_tokens))) * 1.5)


def filter_candidates(
    repos: list[RepoMeta],
    tree_paths: dict[str, list[str]],
    gap_tokens: set[str],
) -> tuple[list[GitHubCandidate], dict[str, int]]:
    """Deterministic gate. Returns surviving candidates + rejection counters."""
    survivors: list[GitHubCandidate] = []
    rejected: dict[str, int] = {}
    seen_names: set[str] = set()

    def bump(reason: str) -> None:
        rejected[reason] = rejected.get(reason, 0) + 1

    for repo in repos:
        if repo.full_name in seen_names:
            bump("duplicate_repo")
            continue
        seen_names.add(repo.full_name)
        if repo.archived:
            bump("archived")
            continue
        if repo.size_kb > MAX_REPO_SIZE_KB:
            bump("too_large")
            continue
        spam_level, spam_reasons = classify_repository(repo.name, repo.description)
        if spam_level is SecurityLevel.REJECTED:
            bump("spam")
            continue
        paths = tree_paths.get(repo.full_name, [])
        skill_files = find_skill_files(paths)
        if not skill_files:
            bump("no_skill_material")
            continue
        rel = relevance_score(repo, skill_files, gap_tokens)
        if rel < MIN_RELEVANCE:
            bump("irrelevant")
            continue
        candidate = GitHubCandidate(
            repo=repo,
            skill_files=skill_files,
            content_path=skill_files[0].path,
            trust_state=TrustState.UNVERIFIED,
            filter_reasons=[f"relevance={rel:.2f}"],
        )
        # Pre-content security screen (spam already handled above).
        level, reasons = classify_content(repo.description or "")
        candidate.security_level = level
        candidate.security_reasons = reasons
        if level is SecurityLevel.REJECTED:
            bump("unsafe_metadata")
            continue
        survivors.append(candidate)
    return survivors, rejected


__all__ = [
    "MAX_REPO_SIZE_KB",
    "classify_file",
    "filter_candidates",
    "find_skill_files",
    "relevance_score",
]
