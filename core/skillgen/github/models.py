"""Phase 2 data models: GitHub discovery candidates, trust state, analysis.

Trust state is metadata about the EXTERNAL source and is deliberately
separate from the local SkillState lifecycle (Phase 1). Imported skills
enter the normal Phase 1 lifecycle at CANDIDATE - never PROVEN.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TrustState(StrEnum):
    """Import trust state for an external (GitHub) candidate."""

    DISCOVERED = "discovered"
    UNVERIFIED = "unverified"
    ANALYZED = "analyzed"
    REVIEW_REQUIRED = "review_required"
    APPROVED = "approved"
    IMPORTED = "imported"
    REJECTED = "rejected"


class SecurityLevel(StrEnum):
    """Deterministic security classification of untrusted GitHub content."""

    SAFE = "SAFE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    HIGH_RISK = "HIGH_RISK"
    REJECTED = "REJECTED"

    def stricter_than(self, other: SecurityLevel) -> SecurityLevel:
        order = [
            SecurityLevel.SAFE,
            SecurityLevel.REVIEW_REQUIRED,
            SecurityLevel.HIGH_RISK,
            SecurityLevel.REJECTED,
        ]
        return self if order.index(self) >= order.index(other) else other


@dataclass(slots=True)
class RepoMeta:
    """Repository metadata (official API fields, bounded)."""

    owner: str
    name: str
    url: str = ""
    description: str = ""
    stars: int = 0
    forks: int = 0
    watchers: int = 0
    language: str = ""
    topics: list[str] = field(default_factory=list)
    license: str = "UNKNOWN"
    license_url: str = ""
    default_branch: str = "main"
    created_at: str = ""
    updated_at: str = ""
    open_issues: int = 0
    archived: bool = False
    fork: bool = False
    size_kb: int = 0

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "owner": self.owner,
            "repository": self.name,
            "full_name": self.full_name,
            "url": self.url,
            "description": self.description,
            "stars": self.stars,
            "forks": self.forks,
            "watchers": self.watchers,
            "language": self.language,
            "topics": list(self.topics),
            "license": self.license,
            "license_url": self.license_url,
            "default_branch": self.default_branch,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "open_issues": self.open_issues,
            "archived": self.archived,
            "fork": self.fork,
            "size_kb": self.size_kb,
        }


@dataclass(slots=True)
class SkillFile:
    """A skill-like file found in a repository (targeted, never cloned)."""

    path: str
    kind: str  # skill_md | agents_md | readme | prompt | workflow | mcp_config | rules | other
    url: str = ""
    size: int = 0


@dataclass(slots=True)
class ExternalAnalysis:
    """Strict structured model verdict for a GitHub candidate (fail closed)."""

    relevant: bool
    useful: bool
    generalizable: bool
    quality_score: float
    security_level: str  # model's claim; deterministic classification wins
    duplicate_of: str | None
    reason: str
    recommended_action: str  # IMPORT | REVIEW | REJECT
    model: str = "unknown"
    confidence: float = 0.0
    raw: str = ""
    parsed_ok: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "relevant": self.relevant,
            "useful": self.useful,
            "generalizable": self.generalizable,
            "quality_score": self.quality_score,
            "security_level": self.security_level,
            "duplicate_of": self.duplicate_of,
            "reason": self.reason,
            "recommended_action": self.recommended_action,
            "model": self.model,
            "confidence": self.confidence,
            "parsed_ok": self.parsed_ok,
        }


@dataclass(slots=True)
class GitHubCandidate:
    """A repository candidate carrying skill-like content, post-filtering."""

    repo: RepoMeta
    skill_files: list[SkillFile] = field(default_factory=list)
    content: str = ""
    content_path: str = ""
    capability_name: str = ""
    capability_description: str = ""
    trust_state: TrustState = TrustState.DISCOVERED
    security_level: SecurityLevel = SecurityLevel.SAFE
    security_reasons: list[str] = field(default_factory=list)
    license_warning: str = ""
    license_compatibility: str = "unknown"
    analysis: ExternalAnalysis | None = None
    duplicate_of: str = ""
    filter_reasons: list[str] = field(default_factory=list)
    commit_sha: str = ""  # best-effort head SHA for provenance (Phase 2)

    @property
    def key(self) -> str:
        return f"{self.repo.full_name}:{self.content_path or '-'}"

    @property
    def source_file_url(self) -> str:
        return (
            f"https://github.com/{self.repo.full_name}/blob/"
            f"{self.repo.default_branch}/{self.content_path}"
            if self.content_path
            else self.repo.url
        )

    def to_dict(self, include_content: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "key": self.key,
            "repo": self.repo.to_dict(),
            "skill_files": [
                {"path": f.path, "kind": f.kind, "size": f.size} for f in self.skill_files
            ],
            "content_path": self.content_path,
            "capability": {
                "name": self.capability_name,
                "description": self.capability_description,
            },
            "trust_state": self.trust_state.value,
            "security_level": self.security_level.value,
            "security_reasons": list(self.security_reasons),
            "license_warning": self.license_warning,
            "license_compatibility": self.license_compatibility,
            "duplicate_of": self.duplicate_of or None,
            "analysis": self.analysis.to_dict() if self.analysis else None,
            "filter_reasons": list(self.filter_reasons),
            "commit_sha": self.commit_sha,
        }
        if include_content:
            data["content"] = self.content[:8000]
        return data


@dataclass(slots=True)
class DiscoveryResult:
    """Outcome of a discovery pass: queries, candidates, bounded counters."""

    queries: list[str] = field(default_factory=list)
    repos: list[RepoMeta] = field(default_factory=list)
    repos_found: int = 0
    repos_examined: int = 0
    candidates: list[GitHubCandidate] = field(default_factory=list)
    filtered_out: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    offline: bool = False

    def to_dict(self, include_content: bool = False) -> dict[str, Any]:
        return {
            "queries": list(self.queries),
            "repos_found": self.repos_found,
            "repos_examined": self.repos_examined,
            "candidate_count": len(self.candidates),
            "candidates": [c.to_dict(include_content) for c in self.candidates],
            "filtered_out": dict(self.filtered_out),
            "errors": list(self.errors),
            "offline": self.offline,
        }


__all__ = [
    "DiscoveryResult",
    "ExternalAnalysis",
    "GitHubCandidate",
    "RepoMeta",
    "SecurityLevel",
    "SkillFile",
    "TrustState",
]
