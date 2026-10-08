"""Phase 2 GitHub import gates: approval, security, license, duplicates.

Import is fail-closed and order-sensitive. Registries live in tmp_path so
the suite never writes skill documents into the repository tree.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.skillgen.github.importer import import_candidate, license_info
from core.skillgen.github.models import (
    GitHubCandidate,
    RepoMeta,
    SecurityLevel,
    SkillFile,
    TrustState,
)
from core.skillgen.registry import SIMILARITY_MERGE, SkillRegistry
from core.skillgen.types import Skill, SkillScope, SkillState

REVIEW_KEYS = {
    "name",
    "source",
    "repository",
    "license",
    "security_classification",
    "analysis",
    "quality_signals",
    "trust_state",
}

SKILL_MD = """---
name: markdown-table-tools
description: Format markdown tables consistently across documents
triggers: markdown table, table formatting
---
# markdown-table-tools

## Steps

- Normalize header separator rows
- Align cell padding widths evenly
- Verify column counts before saving
"""


def make_candidate(
    *,
    name: str = "Format Markdown Tables",
    description: str = "Format markdown tables consistently across documents",
    license_id: str = "MIT",
    security: SecurityLevel = SecurityLevel.SAFE,
    capability_name: str | None = None,
    capability_description: str | None = None,
    content: str = "",
) -> GitHubCandidate:
    repo = RepoMeta(
        owner="acme",
        name="markdown-tools",
        url="https://github.com/acme/markdown-tools",
        description="Formatting helpers",
        license=license_id,
        license_url="https://licenses.example/mit",
        default_branch="main",
    )
    return GitHubCandidate(
        repo=repo,
        skill_files=[SkillFile(path="skills/SKILL.md", kind="skill_md")],
        content=content,
        content_path="skills/SKILL.md",
        capability_name=name if capability_name is None else capability_name,
        capability_description=(
            description if capability_description is None else capability_description
        ),
        security_level=security,
    )


def local_equivalent() -> Skill:
    return Skill(
        name="format-markdown-tables",
        description="Format markdown tables consistently across documents",
        purpose="Keep markdown tables tidy",
        triggers=["markdown table", "table formatting"],
        procedure=["Normalize header separators"],
        state=SkillState.ACTIVE,
    )


class TestLicenseInfo:
    def test_permissive_license_is_compatible(self) -> None:
        info = license_info(make_candidate(license_id="MIT"))
        assert info["license"] == "MIT"
        assert info["license_compatibility"] == "permissive"
        assert info["license_warning"] == ""

    def test_copyleft_license_warns_before_import(self) -> None:
        info = license_info(make_candidate(license_id="GPL-3.0"))
        assert info["license_compatibility"] == "share_alike"
        assert "Copyleft" in info["license_warning"]

    def test_unknown_license_requires_review(self) -> None:
        info = license_info(make_candidate(license_id="UNKNOWN"))
        assert info["license"] == "UNKNOWN"
        assert info["license_compatibility"] == "unknown"
        assert "review required" in info["license_warning"]

    def test_unclassified_license_flagged_for_review(self) -> None:
        info = license_info(make_candidate(license_id="WeirdLicense-1.0"))
        assert info["license_compatibility"] == "review"
        assert "WeirdLicense-1.0" in info["license_warning"]


class TestApprovalAndSecurityGates:
    def test_missing_approval_blocks_import_with_review(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        candidate = make_candidate()
        report = import_candidate(candidate, reg, approve=False)
        assert report["ok"] is False
        assert report["action"] == "rejected"
        assert report["reason"] == "approval_required"
        assert reg.count() == 0
        review = report["review"]
        assert set(review) >= REVIEW_KEYS
        assert review["source"] == "github"
        assert review["repository"] == "acme/markdown-tools"
        assert review["security_classification"] == "SAFE"
        assert review["license"]["license"] == "MIT"
        assert review["analysis"] is None
        assert review["trust_state"] == TrustState.DISCOVERED.value

    def test_rejected_security_sets_trust_rejected(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        candidate = make_candidate(security=SecurityLevel.REJECTED)
        candidate.security_reasons = ["injection:ignore previous instructions"]
        report = import_candidate(candidate, reg, approve=True)
        assert report["ok"] is False
        assert report["reason"] == "security_rejected"
        assert candidate.trust_state is TrustState.REJECTED
        assert "injection" in report["security_reasons"][0]
        assert reg.count() == 0

    def test_high_risk_is_never_imported(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        candidate = make_candidate(security=SecurityLevel.HIGH_RISK)
        candidate.security_reasons = ["forbidden:embedded_secret"]
        report = import_candidate(candidate, reg, approve=True)
        assert report["ok"] is False
        assert report["reason"] == "security_high_risk"
        assert reg.count() == 0

    def test_security_gate_precedes_license_gate(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        candidate = make_candidate(
            security=SecurityLevel.REJECTED, license_id="UNKNOWN"
        )
        report = import_candidate(candidate, reg, approve=True)
        assert report["reason"] == "security_rejected"


class TestLicenseGate:
    def test_unknown_license_requires_acknowledgement(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        report = import_candidate(
            make_candidate(license_id="UNKNOWN"), reg, approve=True
        )
        assert report["ok"] is False
        assert report["reason"] == "license_review_required"
        assert report["license"]["license"] == "UNKNOWN"
        assert reg.count() == 0

    def test_acknowledged_unknown_license_imports(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        report = import_candidate(
            make_candidate(license_id="UNKNOWN"),
            reg,
            approve=True,
            acknowledge_license=True,
        )
        assert report["ok"] is True
        assert report["action"] == "imported"
        assert report["license"]["license"] == "UNKNOWN"
        assert reg.count() == 1

    def test_license_gate_precedes_duplicate_detection(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        reg.add(local_equivalent())
        report = import_candidate(
            make_candidate(license_id="UNKNOWN"), reg, approve=True
        )
        assert report["reason"] == "license_review_required"
        assert reg.count() == 1


class TestDuplicatesAndValidation:
    def test_local_equivalent_reports_duplicate(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        reg.add(local_equivalent())
        before = reg.count()
        candidate = make_candidate(
            capability_name="", capability_description="", content=SKILL_MD
        )
        report = import_candidate(candidate, reg, approve=True)
        assert report["ok"] is False
        assert report["action"] == "duplicate"
        assert report["reason"] == "duplicate_of_local_skill"
        assert report["duplicate_of"] == "format-markdown-tables"
        assert report["similarity"] >= SIMILARITY_MERGE
        assert candidate.duplicate_of == "format-markdown-tables"
        assert reg.count() == before

    def test_duplicate_gate_survives_precomputed_capability_name(
        self, tmp_path: Path
    ) -> None:
        """Regression: capability_name set by discover() must not strip triggers.

        The duplicate gate must re-extract from content, otherwise similarity
        drops below SIMILARITY_MERGE and a near-identical skill imports twice.
        """
        reg = SkillRegistry(tmp_path)
        reg.add(local_equivalent())
        candidate = make_candidate(content=SKILL_MD)
        assert candidate.capability_name  # discover() always sets this
        report = import_candidate(candidate, reg, approve=True)
        assert report["ok"] is False
        assert report["action"] == "duplicate"
        assert report["duplicate_of"] == "format-markdown-tables"
        assert report["similarity"] >= SIMILARITY_MERGE
        assert reg.count() == 1

    def test_name_conflict_rejected(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        reg.add(
            Skill(
                name="format-markdown-tables",
                description="Unrelated deployment automation for remote clusters",
                purpose="Deploy things",
                triggers=["deploy clusters"],
                procedure=["Deploy the cluster"],
                state=SkillState.ACTIVE,
            )
        )
        report = import_candidate(make_candidate(), reg, approve=True)
        assert report["ok"] is False
        assert report["reason"] == "name_conflict"
        assert reg.count() == 1

    def test_invalid_skill_name_fails_validation(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        candidate = make_candidate(
            capability_name="A", capability_description="single letter name"
        )
        report = import_candidate(candidate, reg, approve=True)
        assert report["ok"] is False
        assert report["reason"].startswith("validation:")
        assert reg.count() == 0

    def test_missing_capability_reports_extraction_failed(
        self, tmp_path: Path
    ) -> None:
        reg = SkillRegistry(tmp_path)
        candidate = make_candidate(
            capability_name="", capability_description="", content=""
        )
        report = import_candidate(candidate, reg, approve=True)
        assert report["ok"] is False
        assert report["reason"] == "extraction_failed"
        assert reg.count() == 0


class TestImportLifecycle:
    def test_happy_path_import_becomes_active(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        report = import_candidate(make_candidate(), reg, approve=True)
        assert report["ok"] is True
        assert report["action"] == "imported"
        assert report["state"] == "active"
        assert report["scope"] == "agent"
        skill = reg.get("format-markdown-tables")
        assert skill is not None
        assert skill.state is SkillState.ACTIVE
        assert skill.version == 1

    def test_imported_skill_is_never_proven(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        import_candidate(make_candidate(), reg, approve=True)
        skill = reg.get("format-markdown-tables")
        assert skill is not None
        assert skill.state is not SkillState.PROVEN
        assert skill.success_count == 0
        assert skill.failure_count == 0
        assert skill.confidence < 0.5

    def test_failed_self_test_stays_validating(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        report = import_candidate(
            make_candidate(),
            reg,
            approve=True,
            scope=SkillScope.PROJECT,
            project_id="",
        )
        assert report["ok"] is True
        assert report["state"] == "validating"
        skill = reg.get("format-markdown-tables")
        assert skill is not None
        assert skill.state is SkillState.VALIDATING

    def test_provenance_carries_github_source(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        import_candidate(make_candidate(), reg, approve=True)
        skill = reg.get("format-markdown-tables")
        assert skill is not None
        provenance: dict[str, Any] = skill.provenance
        assert provenance["source_type"] == "github"
        github_block = provenance["github"]
        assert github_block["owner"] == "acme"
        assert github_block["repository"] == "markdown-tools"
        assert github_block["source_file"] == "skills/SKILL.md"
        assert github_block["license"] == "MIT"
        assert github_block["source_file_url"].startswith(
            "https://github.com/acme/markdown-tools/blob/"
        )

    def test_registry_persists_and_logs_import_event(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        import_candidate(make_candidate(), reg, approve=True)
        assert reg.path.exists()
        reloaded = SkillRegistry(tmp_path)
        assert reloaded.count() == 1
        assert reloaded.get("format-markdown-tables") is not None
        events = reg.stats["events"]
        assert any(e["event"] == "skill_imported_github" for e in events)
        detail = next(
            e["detail"] for e in events if e["event"] == "skill_imported_github"
        )
        assert "acme/markdown-tools" in detail
        assert "license=MIT" in detail
        assert reloaded.stats["events"]
