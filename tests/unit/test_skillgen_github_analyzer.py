"""Phase 2 GitHub analyzer: prompt build, strict parse, budgeted analysis.

Every model verdict is injected through tiny local fakes - no network, no
external model, and no subprocess judge is ever started in this suite.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from core.skillgen.budget import ModelCallBudget
from core.skillgen.github.analyzer import analyze, build_analysis_prompt, parse_analysis
from core.skillgen.github.models import GitHubCandidate, RepoMeta, SecurityLevel

CAPABILITY: dict[str, Any] = {
    "name": "format-markdown-tables",
    "description": "Format markdown tables consistently across documents",
    "procedure": ["Normalize header separators", "Align cell padding widths"],
    "triggers": ["markdown table", "table formatting"],
}


class MockJudge:
    """Injectable analysis judge: canned text or a raised error."""

    def __init__(self, raw: str = "", error: Exception | None = None) -> None:
        self.raw = raw
        self.error = error
        self.calls = 0

    def __call__(self, prompt: str) -> tuple[str, str]:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.raw, "mock-model"


def verdict(**overrides: Any) -> str:
    payload: dict[str, Any] = {
        "relevant": True,
        "useful": True,
        "generalizable": True,
        "quality_score": 0.8,
        "security_level": "SAFE",
        "duplicate_of": None,
        "reason": "solid reusable capability",
        "recommended_action": "IMPORT",
    }
    payload.update(overrides)
    return json.dumps(payload)


def make_candidate(security: SecurityLevel = SecurityLevel.SAFE) -> GitHubCandidate:
    repo = RepoMeta(
        owner="acme",
        name="markdown-tools",
        url="https://github.com/acme/markdown-tools",
        description="Formatting helpers",
        license="MIT",
    )
    return GitHubCandidate(
        repo=repo,
        content_path="skills/SKILL.md",
        capability_name=str(CAPABILITY["name"]),
        capability_description=str(CAPABILITY["description"]),
        security_level=security,
    )


def budget(max_per_task: int = 4, stats: dict[str, Any] | None = None) -> ModelCallBudget:
    return ModelCallBudget(stats if stats is not None else {}, max_per_task=max_per_task)


class TestBuildAnalysisPrompt:
    def test_prompt_embeds_bounded_capability_evidence(self) -> None:
        capability = dict(
            CAPABILITY,
            description="d" * 700,
            procedure=[f"step number {i} of the flow" for i in range(12)],
        )
        prompt = build_analysis_prompt(make_candidate(), capability)
        raw = prompt.split("EVIDENCE (JSON):\n", 1)[1].split("\n\n", 1)[0]
        evidence = json.loads(raw)
        assert evidence["repository"]["full_name"] == "acme/markdown-tools"
        assert evidence["source_file"] == "skills/SKILL.md"
        assert evidence["deterministic_security"] == "SAFE"
        assert len(evidence["capability"]["description"]) == 600
        assert len(evidence["capability"]["procedure_steps"]) == 8

    def test_prompt_marks_content_untrusted_and_lists_local_similarity(self) -> None:
        prompt = build_analysis_prompt(
            make_candidate(), CAPABILITY, [("local-helper", 0.91)]
        )
        assert "UNTRUSTED" in prompt
        assert "deterministic" in prompt
        assert '"name": "local-helper"' in prompt
        assert '"similarity": 0.91' in prompt
        assert '"relevant": true' in prompt


class TestParseAnalysis:
    def test_valid_json_returns_parsed_fields(self) -> None:
        result = parse_analysis(verdict(), model_id="mock-model")
        assert result.parsed_ok is True
        assert result.relevant is True
        assert result.useful is True
        assert result.generalizable is True
        assert result.quality_score == pytest.approx(0.8)
        assert result.security_level == "SAFE"
        assert result.recommended_action == "IMPORT"
        assert result.duplicate_of is None
        assert result.model == "mock-model"
        assert result.confidence == pytest.approx(0.8)

    def test_json_fenced_output_accepted(self) -> None:
        raw = f"```json\n{verdict(quality_score=0.5)}\n```"
        result = parse_analysis(raw)
        assert result.parsed_ok is True
        assert result.quality_score == pytest.approx(0.5)

    def test_garbage_fails_closed(self) -> None:
        result = parse_analysis("definitely not json at all")
        assert result.parsed_ok is False
        assert result.relevant is False
        assert result.useful is False
        assert result.security_level == "REJECTED"
        assert result.recommended_action == "REJECT"
        assert result.reason == "unparseable_model_output"
        assert result.quality_score == 0.0
        assert result.duplicate_of is None

    def test_empty_output_fails_closed(self) -> None:
        result = parse_analysis("   \n  ")
        assert result.parsed_ok is False
        assert result.recommended_action == "REJECT"
        assert result.reason == "unparseable_model_output"

    def test_non_object_payload_fails_closed(self) -> None:
        result = parse_analysis("```json\n[1, 2, 3]\n```")
        assert result.parsed_ok is False
        assert result.security_level == "REJECTED"
        assert result.recommended_action == "REJECT"

    def test_non_bool_relevant_fails_closed(self) -> None:
        result = parse_analysis(verdict(relevant="yes"))
        assert result.parsed_ok is False
        assert result.recommended_action == "REJECT"

    def test_non_bool_useful_fails_closed(self) -> None:
        result = parse_analysis(verdict(useful=1))
        assert result.parsed_ok is False
        assert result.reason == "unparseable_model_output"

    def test_invalid_security_level_defaults_to_review_required(self) -> None:
        result = parse_analysis(verdict(security_level="MEDIUM"))
        assert result.parsed_ok is True
        assert result.security_level == "REVIEW_REQUIRED"

    def test_invalid_recommended_action_falls_back_to_review(self) -> None:
        result = parse_analysis(verdict(recommended_action="OBLITERATE"))
        assert result.parsed_ok is True
        assert result.recommended_action == "REVIEW"

    @pytest.mark.parametrize(
        ("raw_score", "expected"),
        [(5.0, 1.0), (-2.5, 0.0), ("excellent", 0.0)],
    )
    def test_quality_score_clamped_to_unit_interval(
        self, raw_score: Any, expected: float
    ) -> None:
        result = parse_analysis(verdict(quality_score=raw_score))
        assert result.parsed_ok is True
        assert result.quality_score == pytest.approx(expected)

    def test_duplicate_of_null_cleared(self) -> None:
        result = parse_analysis(verdict(duplicate_of=None))
        assert result.duplicate_of is None

    def test_duplicate_of_string_preserved(self) -> None:
        result = parse_analysis(verdict(duplicate_of="local-skill"))
        assert result.duplicate_of == "local-skill"

    def test_duplicate_of_falsy_cleared(self) -> None:
        result = parse_analysis(verdict(duplicate_of=0))
        assert result.duplicate_of is None

    def test_duplicate_of_truthy_non_string_stringified(self) -> None:
        result = parse_analysis(verdict(duplicate_of=123))
        assert isinstance(result.duplicate_of, str)
        assert result.duplicate_of == "123"


class TestAnalyze:
    def test_no_judge_keeps_deterministic_security(self) -> None:
        candidate = make_candidate(SecurityLevel.REVIEW_REQUIRED)
        report = analyze(
            candidate, CAPABILITY, judge=None, budget=budget(), task_key="t-nojudge"
        )
        assert report.reason == "no_judge_configured"
        assert report.recommended_action == "REVIEW"
        assert report.security_level == "REVIEW_REQUIRED"
        assert report.parsed_ok is False

    def test_zero_budget_never_calls_judge(self) -> None:
        judge = MockJudge(verdict())
        report = analyze(
            make_candidate(),
            CAPABILITY,
            judge=judge,
            budget=budget(max_per_task=0),
            task_key="t-zero",
        )
        assert report.reason == "budget_exhausted"
        assert report.recommended_action == "REVIEW"
        assert report.parsed_ok is False
        assert judge.calls == 0

    def test_exhausted_task_budget_never_calls_judge(self) -> None:
        stats = {"model_calls_total": 3, "model_calls_by_task": {"t-used": 3}}
        judge = MockJudge(verdict())
        report = analyze(
            make_candidate(),
            CAPABILITY,
            judge=judge,
            budget=budget(max_per_task=3, stats=stats),
            task_key="t-used",
        )
        assert report.reason == "budget_exhausted"
        assert report.security_level == "SAFE"
        assert judge.calls == 0

    def test_judge_error_fails_closed(self) -> None:
        judge = MockJudge(error=RuntimeError("model down"))
        report = analyze(
            make_candidate(),
            CAPABILITY,
            judge=judge,
            budget=budget(),
            task_key="t-err",
        )
        assert report.reason == "judge_error:RuntimeError"
        assert report.recommended_action == "REJECT"
        assert report.parsed_ok is False
        assert report.security_level == "SAFE"

    def test_rejected_content_beats_model_safe_claim(self) -> None:
        judge = MockJudge(verdict())
        report = analyze(
            make_candidate(SecurityLevel.REJECTED),
            CAPABILITY,
            judge=judge,
            budget=budget(),
            task_key="t-rej",
        )
        assert judge.calls == 1
        assert report.security_level == "REJECTED"
        assert report.recommended_action == "REJECT"

    def test_high_risk_content_beats_model_safe_claim(self) -> None:
        judge = MockJudge(verdict())
        report = analyze(
            make_candidate(SecurityLevel.HIGH_RISK),
            CAPABILITY,
            judge=judge,
            budget=budget(),
            task_key="t-high",
        )
        assert report.security_level == "HIGH_RISK"
        assert report.recommended_action == "REJECT"

    def test_import_verdict_on_safe_candidate_accepted(self) -> None:
        judge = MockJudge(verdict())
        report = analyze(
            make_candidate(),
            CAPABILITY,
            judge=judge,
            budget=budget(),
            task_key="t-ok",
        )
        assert report.parsed_ok is True
        assert report.security_level == "SAFE"
        assert report.recommended_action == "IMPORT"
        assert report.model == "mock-model"
        assert report.confidence == pytest.approx(0.8)

    def test_budget_consumes_exactly_one_call(self) -> None:
        report_budget = budget(max_per_task=4)
        analyze(
            make_candidate(),
            CAPABILITY,
            judge=MockJudge(verdict()),
            budget=report_budget,
            task_key="t-budget",
        )
        assert report_budget.used("t-budget") == 1
        assert report_budget.report("t-budget") == {
            "used": 1,
            "max": 4,
            "remaining": 3,
            "total": 1,
        }
