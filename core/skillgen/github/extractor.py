"""Capability extraction from GitHub skill files (never the whole repo).

Extracts the reusable capability - name, description, procedure - as
INSTRUCTIONS. Executable dependencies are flagged, never installed or run.
"""

from __future__ import annotations

import re
from datetime import UTC
from typing import Any

from core.skillgen.github.models import GitHubCandidate
from core.skillgen.types import Skill, SkillScope, SkillState

_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_HEADING = re.compile(r"\A#\s+(.+)")
_MAX_FIELD = 4000
_MAX_STEPS = 40


def _frontmatter(text: str) -> dict[str, str]:
    match = _FRONTMATTER.match(text)
    if not match:
        return {}
    data: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            data[key.strip().lower()] = value.strip().strip('"')
    return data


def _strip_frontmatter(text: str) -> str:
    return _FRONTMATTER.sub("", text, count=1)


def _steps_from_markdown(body: str) -> list[str]:
    steps: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if re.match(r"^(#{2,4}\s|\d+\.\s|[-*]\s)", stripped) and not stripped.startswith("```"):
            clean = re.sub(r"^(#{2,4}\s|\d+\.\s|[-*]\s)", "", stripped)
            clean = re.sub(r"\*\*|__", "", clean).strip()
            if clean and len(clean) > 3:
                steps.append(clean[:300])
        if len(steps) >= _MAX_STEPS:
            break
    return steps


def extract_capability(candidate: GitHubCandidate) -> dict[str, Any]:
    """Parse the primary skill file into a capability description."""
    text = candidate.content or ""
    if not text.strip():
        return {}
    meta = _frontmatter(text)
    body = _strip_frontmatter(text)
    name = meta.get("name", "") or meta.get("skill", "")
    if not name:
        heading = _HEADING.search(body)
        name = heading.group(1).strip() if heading else candidate.repo.name
    description = meta.get("description", "") or meta.get("summary", "")
    if not description:
        for line in body.splitlines():
            line = line.strip()
            if line and not line.startswith(("#", "-", ">", "|", "```")):
                description = line
                break
    raw_triggers = meta.get("triggers", "") or ""
    triggers = [t.strip() for t in re.split(r"[,;\n]", raw_triggers) if t.strip()][:8]
    procedure = _steps_from_markdown(body)
    return {
        "name": name[:120],
        "description": (description or "")[:_MAX_FIELD],
        "procedure": procedure,
        "triggers": triggers,
        "has_executable_dep": bool(
            re.search(r"```\s*(bash|sh|shell|python|powershell)\b", body, re.IGNORECASE)
        ),
    }


def build_provenance(candidate: GitHubCandidate, analysis: dict[str, Any] | None) -> dict[str, Any]:
    """Phase 2 provenance extension: source_type=github + github + analysis."""
    from datetime import datetime

    repo = candidate.repo
    github_block = {
        "owner": repo.owner,
        "repository": repo.name,
        "url": repo.url,
        "branch": repo.default_branch,
        "commit_sha": candidate.commit_sha,  # best-effort; "" when unknown
        "source_file": candidate.content_path,
        "source_file_url": candidate.source_file_url,
        "discovered_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "license": repo.license,
        "repository_updated_at": repo.updated_at,
    }
    return {
        "source_type": "github",
        "github": github_block,
        "analysis": analysis or {},
    }


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return slug[:64] or "imported-skill"


def build_imported_skill(
    candidate: GitHubCandidate,
    capability: dict[str, Any],
    *,
    agent_id: str = "opencode",
    project_id: str = "",
    session_id: str = "",
    scope: SkillScope = SkillScope.AGENT,
    model: str = "",
) -> Skill:
    """Construct a local Skill from extracted capability (starts CANDIDATE).

    Imported skills enter the Phase 1 lifecycle - never auto-PROVEN.
    External origin does not imply trust. Content stays instructions-only.
    """
    name = _slug(capability.get("name", "") or candidate.repo.name)
    repo_full = candidate.repo.full_name
    procedure = [s[:300] for s in capability.get("procedure", [])][:_MAX_STEPS]
    if not procedure:
        procedure = [f"Review capability source: {candidate.source_file_url}"]
    analysis = candidate.analysis.to_dict() if candidate.analysis else {}
    provenance = build_provenance(candidate, analysis)
    if capability.get("has_executable_dep"):
        provenance["executable_dependency"] = True
        provenance["executable_note"] = (
            "Source contains executable code blocks; not installed or run - "
            "instructions only. Implementation must be reviewed by the user."
        )
    description = (capability.get("description") or f"Imported from {repo_full}")[:4000]
    return Skill(
        name=name,
        description=description,
        purpose=f"Reusable capability discovered from GitHub ({repo_full})."[:4000],
        triggers=[str(t)[:120] for t in capability.get("triggers", [])][:8],
        procedure=procedure,
        expected_output="Capability applied per procedure (instructions, not code).",
        constraints=[
            "Source is untrusted third-party content; verify before relying on it.",
            "No automatic execution of source repository code or dependencies.",
        ],
        examples=[],
        confidence=0.4,  # starts limited; rises only via Phase 1 feedback
        created_from=[candidate.key],
        provenance=provenance,
        state=SkillState.CANDIDATE,
        scope=scope,
        agent_id=agent_id if scope is SkillScope.AGENT else "",
        project_id=project_id if scope is SkillScope.PROJECT else "",
        session_id=session_id if scope is SkillScope.SESSION else "",
        tags=["imported", "github", *(candidate.repo.topics[:6])],
    )


__all__ = ["build_imported_skill", "build_provenance", "extract_capability"]
