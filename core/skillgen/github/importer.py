"""Explicit-approval import of GitHub candidates into the local registry.

Fail-closed: no approval -> no import; REJECTED security -> no import;
unknown license without acknowledgement -> no import; duplicate -> no new
skill. Imported skills enter the normal Phase 1 lifecycle at CANDIDATE ->
VALIDATING -> (self-test) -> ACTIVE. They are NEVER auto-PROVEN: external
origin does not imply trust or correctness.
"""

from __future__ import annotations

from typing import Any

from core.skillgen.github.comparator import find_local_duplicate
from core.skillgen.github.extractor import build_imported_skill, extract_capability
from core.skillgen.github.models import GitHubCandidate, SecurityLevel, TrustState
from core.skillgen.matcher import match as match_skills
from core.skillgen.registry import SkillRegistry
from core.skillgen.types import SkillScope, SkillState
from core.skillgen.validate import validate_skill

_PERMISSIVE = {
    "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "0BSD",
    "Unlicense", "CC0-1.0", "MPL-2.0",
}
_SHARE_ALIKE = {"GPL-2.0", "GPL-3.0", "AGPL-3.0", "LGPL-3.0", "MPL-1.1"}


def license_info(candidate: GitHubCandidate) -> dict[str, str]:
    """Surface license facts. No legal conclusions - unknown requires review."""
    spdx = (candidate.repo.license or "UNKNOWN").strip() or "UNKNOWN"
    if spdx == "UNKNOWN" or spdx == "NOASSERTION":
        return {
            "license": "UNKNOWN",
            "license_url": candidate.repo.license_url or "",
            "license_compatibility": "unknown",
            "license_warning": "License not stated - review required before import.",
        }
    if spdx in _PERMISSIVE:
        compat, warning = "permissive", ""
    elif spdx in _SHARE_ALIKE:
        compat, warning = (
            "share_alike",
            "Copyleft license - obligations may apply; review before importing.",
        )
    else:
        compat, warning = "review", f"Unclassified license '{spdx}' - review required."
    return {
        "license": spdx,
        "license_url": candidate.repo.license_url or "",
        "license_compatibility": compat,
        "license_warning": warning,
    }


def review_preview(candidate: GitHubCandidate) -> dict[str, Any]:
    """Everything the user should inspect before approving (spec section 23)."""
    return {
        "key": candidate.key,
        "name": candidate.capability_name or candidate.repo.name,
        "description": candidate.capability_description or candidate.repo.description,
        "source": "github",
        "repository": candidate.repo.full_name,
        "repository_url": candidate.repo.url,
        "source_file": candidate.content_path,
        "source_file_url": candidate.source_file_url,
        "license": license_info(candidate),
        "security_classification": candidate.security_level.value,
        "security_reasons": list(candidate.security_reasons),
        "quality_signals": {
            "stars": candidate.repo.stars,
            "forks": candidate.repo.forks,
            "updated_at": candidate.repo.updated_at,
            "archived": candidate.repo.archived,
            "open_issues": candidate.repo.open_issues,
        },
        "analysis": candidate.analysis.to_dict() if candidate.analysis else None,
        "duplicate_of": candidate.duplicate_of or None,
        "trust_state": candidate.trust_state.value,
        "capability": {
            "name": candidate.capability_name,
            "description": candidate.capability_description,
        },
    }


def _self_test(
    registry: SkillRegistry,
    skill_name: str,
    query: str,
    agent_id: str,
    project_id: str,
    session_id: str,
) -> tuple[bool, str]:
    """Phase 1-style retrieval self-test: the skill must match its own query."""
    matches = match_skills(
        registry,
        query,
        agent_id=agent_id,
        project_id=project_id,
        session_id=session_id,
        include_unusable=True,
        limit=5,
    )
    if any(m["name"] == skill_name for m in matches):
        return True, ""
    return False, "skill_not_retrievable_for_own_query"


def import_candidate(
    candidate: GitHubCandidate,
    registry: SkillRegistry,
    *,
    approve: bool,
    scope: SkillScope = SkillScope.AGENT,
    agent_id: str = "opencode",
    project_id: str = "",
    session_id: str = "",
    acknowledge_license: bool = False,
) -> dict[str, Any]:
    """Import one reviewed candidate. Explicit approval is mandatory."""
    if not approve:
        return {
            "ok": False,
            "action": "rejected",
            "reason": "approval_required",
            "detail": "Explicit approval is required; nothing was imported.",
            "review": review_preview(candidate),
        }

    # Hard security gate - deterministic, model-independent.
    if candidate.security_level is SecurityLevel.REJECTED:
        candidate.trust_state = TrustState.REJECTED
        return {
            "ok": False,
            "action": "rejected",
            "reason": "security_rejected",
            "security_reasons": list(candidate.security_reasons),
            "review": review_preview(candidate),
        }
    if candidate.security_level is SecurityLevel.HIGH_RISK:
        return {
            "ok": False,
            "action": "rejected",
            "reason": "security_high_risk",
            "security_reasons": list(candidate.security_reasons),
            "detail": "HIGH_RISK content must be manually reviewed and cleaned; "
            "it is never imported by the pipeline.",
            "review": review_preview(candidate),
        }

    lic = license_info(candidate)
    if lic["license"] == "UNKNOWN" and not acknowledge_license:
        return {
            "ok": False,
            "action": "rejected",
            "reason": "license_review_required",
            "license": lic,
            "detail": "License unknown - acknowledge_license=True required after review.",
        }

    # Always re-extract from content so the duplicate gate sees triggers and
    # procedure, not just the pre-computed name/description pair.
    capability = extract_capability(candidate) if candidate.content else {}
    if not capability.get("name") and candidate.capability_name:
        capability = {
            "name": candidate.capability_name,
            "description": candidate.capability_description,
            "procedure": [],
            "triggers": [],
            "has_executable_dep": False,
        }
    if not capability or not capability.get("name"):
        return {
            "ok": False,
            "action": "rejected",
            "reason": "extraction_failed",
            "detail": "No capability could be extracted from the source file.",
        }

    # Local duplicate check (Phase 1 similarity) - no duplicate skills.
    duplicate_of, sim = find_local_duplicate(capability, registry, candidate.repo.full_name)
    if duplicate_of:
        candidate.duplicate_of = duplicate_of
        candidate.trust_state = TrustState.REJECTED
        return {
            "ok": False,
            "action": "duplicate",
            "reason": "duplicate_of_local_skill",
            "duplicate_of": duplicate_of,
            "similarity": sim,
            "detail": f"Local skill '{duplicate_of}' already covers this capability.",
        }

    # Scope decision: global promotion is never automatic for external content.
    effective_scope = scope
    if scope is SkillScope.GLOBAL:
        generalizable = bool(candidate.analysis and candidate.analysis.generalizable)
        if not generalizable:
            effective_scope = SkillScope.AGENT

    skill = build_imported_skill(
        candidate,
        capability,
        agent_id=agent_id,
        project_id=project_id,
        session_id=session_id,
        scope=effective_scope,
        model=candidate.analysis.model if candidate.analysis else "",
    )
    if skill.name in {s.name for s in registry.all()}:
        return {
            "ok": False,
            "action": "rejected",
            "reason": "name_conflict",
            "detail": f"Registry already has a skill named '{skill.name}'.",
        }
    ok, reason = validate_skill(skill)
    if not ok:
        return {
            "ok": False,
            "action": "rejected",
            "reason": f"validation:{reason}",
        }

    # Phase 1 lifecycle: CANDIDATE -> VALIDATING -> (self-test) -> ACTIVE.
    skill.state = SkillState.VALIDATING
    added, add_reason = registry.add(skill)
    if not added:
        return {"ok": False, "action": "rejected", "reason": f"registry:{add_reason}"}

    query = " ".join([skill.name.replace("-", " "), *skill.triggers[:3]]).strip()
    passed, test_reason = _self_test(registry, skill.name, query, agent_id, project_id, session_id)
    final_state = SkillState.ACTIVE if passed else SkillState.VALIDATING
    skill.state = final_state
    candidate.trust_state = TrustState.IMPORTED
    registry.log_event(
        "skill_imported_github",
        f"name={skill.name} source={candidate.repo.full_name} "
        f"file={candidate.content_path} state={final_state.value} "
        f"license={lic['license']} security={candidate.security_level.value} "
        f"self_test={'passed' if passed else test_reason}",
    )
    registry.save()
    return {
        "ok": True,
        "action": "imported",
        "name": skill.name,
        "state": final_state.value,
        "scope": effective_scope.value,
        "confidence": skill.confidence,
        "license": lic,
        "security": candidate.security_level.value,
        "provenance": {"source_type": "github", "repo": candidate.repo.full_name},
        "review": review_preview(candidate),
    }


__all__ = ["import_candidate", "license_info", "review_preview"]
