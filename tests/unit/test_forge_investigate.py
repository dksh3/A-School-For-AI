"""Tests for core/forge/investigate.py — adaptive diagnostic investigation loop.

ALL DATA SYNTHETIC (fixture findings/hypotheses; probes run real local commands
but assert only on recorded evidence shape).
"""

from __future__ import annotations

import json

import pytest

from core.forge.investigate import (
    Band,
    Classification,
    EvidenceKind,
    FindingStatus,
    Investigation,
    Severity,
)


@pytest.fixture()
def case() -> Investigation:
    return Investigation.start("INV-1", "Probe the probe layer", scope="synthetic scope")


class TestEvidenceAndHypotheses:
    def test_add_evidence_assigns_stable_ids(self, case: Investigation) -> None:
        e1 = case.add_evidence("test", "tests/unit/test_x.py::test_y", "1 passed")
        e2 = case.add_evidence("file", "school/cli.py:100", "line exists")
        assert e1.id == "E-001" and e2.id == "E-002"
        assert e1.kind == EvidenceKind.TEST

    def test_probe_records_success_as_evidence(self, case: Investigation) -> None:
        evidence = case.probe("python -c \"print('probe-ok')\"", ref="echo probe")
        assert evidence.kind == EvidenceKind.COMMAND
        assert "exit=0" in evidence.detail
        assert "probe-ok" in evidence.detail

    def test_probe_failure_is_evidence_not_exception(self, case: Investigation) -> None:
        evidence = case.probe("python -c \"raise SystemExit(3)\"", ref="failing probe")
        assert "exit=3" in evidence.detail
        assert case.assessment()["evidence"] == 1

    def test_probe_timeout_recorded_without_result_claim(self, case: Investigation) -> None:
        evidence = case.probe(
            "python -c \"import time; time.sleep(5)\"", ref="slow", timeout_s=0.3
        )
        assert "TIMEOUT" in evidence.detail
        assert "no result claimed" in evidence.detail

    def test_hypothesis_confidence_requires_justification(self, case: Investigation) -> None:
        h = case.add_hypothesis("the drop happens at the boundary")
        with pytest.raises(ValueError):
            case.set_confidence(h.id, 0.9, "   ")
        case.set_confidence(h.id, 0.9, "reproduced twice with a pair-shaped row")
        assert case.hypotheses[0].confidence == 0.9

    def test_link_evidence_support_and_refute(self, case: Investigation) -> None:
        h = case.add_hypothesis("h1")
        e1 = case.add_evidence("command", "probe-1", "ok")
        e2 = case.add_evidence("command", "probe-2", "no")
        case.link_evidence(h.id, e1.id, support=True)
        case.link_evidence(h.id, e2.id, support=False)
        assert case.hypotheses[0].supporting == ["E-001"]
        assert case.hypotheses[0].refuting == ["E-002"]


class TestFindingLifecycle:
    def test_missing_evidence_blocks_closing(self, case: Investigation) -> None:
        f = case.add_finding("silent drop somewhere")
        with pytest.raises(ValueError):
            case.set_status(f.id, "FIXED")
        with pytest.raises(ValueError):
            case.set_status(f.id, "VERIFIED")

    def test_finding_closes_with_evidence(self, case: Investigation) -> None:
        f = case.add_finding("silent drop")
        e = case.add_evidence("test", "nodeid", "regression passed")
        case.attach_evidence(f.id, e.id)
        case.set_status(f.id, "FIXED")
        assert case.findings[0].status == FindingStatus.FIXED

    def test_priority_band_is_additive_and_ordered(self, case: Investigation) -> None:
        f1 = case.add_finding(
            "a", severity=Severity.MUST_FIX, impact=Band.HIGH,
            likelihood=Band.HIGH, uncertainty=Band.HIGH,
        )
        f2 = case.add_finding(
            "b", severity=Severity.NOTE, impact=Band.LOW,
            likelihood=Band.LOW, uncertainty=Band.LOW,
        )
        assert f1.priority() == 3 + 2 + 2 + 1
        assert f2.priority() == 1 + 0 + 0 + 0
        assert f1.priority() > f2.priority()

    def test_root_cause_not_claimed_without_support_flag(self, case: Investigation) -> None:
        f = case.add_finding("x", root_cause="because y")
        assert f.root_cause_supported is False
        report = case.to_markdown()
        assert "root cause: not established" in report


class TestNextActionLoop:
    def test_confirmed_defect_calls_for_fix(self, case: Investigation) -> None:
        case.add_finding("drop", classification=Classification.CONFIRMED_DEFECT)
        nxt = case.next_action()
        assert nxt is not None
        assert nxt["action_kind"] == "fix"

    def test_unknown_calls_for_probe(self, case: Investigation) -> None:
        case.add_finding("mystery", classification=Classification.UNKNOWN)
        assert case.next_action()["action_kind"] == "probe"

    def test_coverage_gap_calls_for_inspect(self, case: Investigation) -> None:
        case.add_finding("gap", classification=Classification.COVERAGE_GAP)
        assert case.next_action()["action_kind"] == "inspect"

    def test_fixed_calls_for_verify(self, case: Investigation) -> None:
        f = case.add_finding("drop", classification=Classification.CONFIRMED_DEFECT)
        e = case.add_evidence("test", "nodeid", "pass")
        case.attach_evidence(f.id, e.id)
        case.set_status(f.id, "FIXED")
        assert case.next_action()["action_kind"] == "verify"

    def test_not_reproduced_calls_for_reprobe(self, case: Investigation) -> None:
        f = case.add_finding("flake", classification=Classification.ENVIRONMENTAL_FAILURE)
        e = case.add_evidence("log", "run1", "passed once")
        case.attach_evidence(f.id, e.id)
        case.set_status(f.id, "NOT_REPRODUCED")
        assert case.next_action()["action_kind"] == "reprobe"

    def test_open_question_outranks_and_calls_for_ask(self, case: Investigation) -> None:
        case.add_finding("drop", classification=Classification.CONFIRMED_DEFECT)
        case.record_question("which surface is authoritative?", "changes the fix site")
        nxt = case.next_action()
        assert nxt is not None
        assert nxt["action_kind"] == "ask"

    def test_closed_investigation_with_no_items_returns_none(self, case: Investigation) -> None:
        assert case.next_action() is None


class TestQuestions:
    def test_unanswered_question_stays_unresolved_in_report(self, case: Investigation) -> None:
        case.record_question("is the proxy acceptable?", "decides a hard floor")
        report = case.to_markdown()
        assert "UNRESOLVED" in report
        assert "affected conclusions are marked BLOCKED" in report

    def test_answer_records_effect(self, case: Investigation) -> None:
        qid = case.record_question("q?", "matters")
        case.answer_question(qid, "no", "kept NO-GO")
        report = case.to_markdown()
        assert "kept NO-GO" in report
        assert case.open_questions() == []


class TestPersistence:
    def test_save_and_load_round_trip(self, case: Investigation, tmp_path: object) -> None:
        path = tmp_path / "case.json"  # type: ignore[operator]
        f = case.add_finding(
            "drop",
            severity=Severity.MUST_FIX,
            classification=Classification.CONFIRMED_DEFECT,
            expected="rows counted",
            observed="rows dropped",
            reproduction="run quant with pair row",
        )
        e = case.add_evidence("test", "nodeid", "exit=0")
        case.attach_evidence(f.id, e.id)
        case.record_question("q1?", "why")
        case.save(path)
        restored = Investigation.load(path)
        assert restored.findings[0].title == "drop"
        assert restored.findings[0].severity == Severity.MUST_FIX
        assert restored.findings[0].evidence == ["E-001"]
        assert restored.open_questions()[0]["question"] == "q1?"
        assert restored.to_dict()["id"] == "INV-1"

    def test_load_tolerates_hostile_json(self, tmp_path: object) -> None:
        path = tmp_path / "evil.json"  # type: ignore[operator]
        path.write_text(
            json.dumps(
                {
                    "id": 1,
                    "title": ["a"],
                    "findings": [{"id": "F-001", "title": "t", "severity": "banana",
                                  "status": 7, "confidence": "x"}],
                    "evidence": "nope",
                    "questions": [{"id": "Q-001"}],
                }
            ),
            encoding="utf-8",
        )
        restored = Investigation.load(path)
        assert restored.findings[0].severity == Severity.NOTE
        assert restored.findings[0].status == FindingStatus.OPEN
        assert restored.evidence == []


class TestReport:
    def test_report_is_honest(self, case: Investigation) -> None:
        case.add_finding("f1", expected="e", observed="o", reproduction="steps here")
        report = case.to_markdown()
        assert "does not claim exhaustive discovery" in report
        assert "evidence: NONE RECORDED" in report
        assert "not statistical measures" in report
        assert "not probabilities" in report
        assert "Missing evidence is never treated as success" in report


class TestBoundaryNormalization:
    """Stringly-typed enum fields must normalize at the boundary (fail-closed defaults).

    Regression: add_finding/add_evidence accepted plain strings and to_dict()
    then crashed on ``.value`` (caught by the CLI tests first).
    """

    def test_string_typed_fields_normalize(self, case: Investigation) -> None:
        ev = case.add_evidence("command", ref="r", detail="exit=0")
        f = case.add_finding(
            "boundary check",
            severity="must-fix",
            classification="CONFIRMED DEFECT",
            likelihood="high",
            impact="high",
            uncertainty="low",
            status="open",
        )
        case.attach_evidence(f.id, ev.id)
        d = case.to_dict()
        saved = json.dumps(d)  # must not raise
        assert '"severity": "must-fix"' in saved
        assert '"classification": "CONFIRMED DEFECT"' in saved
        assert '"kind": "command"' in saved

    def test_unknown_string_values_fail_closed_to_defaults(self, case: Investigation) -> None:
        ev = case.add_evidence("banana", ref="r", detail="x")
        f = case.add_finding("hostile", severity="telepathy", classification="vibes")
        assert ev.kind == EvidenceKind.OBSERVATION
        assert f.severity == Severity.NOTE
        assert f.classification == Classification.UNKNOWN
        case.attach_evidence(f.id, ev.id)
        json.dumps(case.to_dict())  # must not raise

    def test_set_status_rejects_unknown_strings(self, case: Investigation) -> None:
        ev = case.add_evidence("observation", ref="seen", detail="observed")
        f = case.add_finding("status hygiene", status="open")
        case.attach_evidence(f.id, ev.id)
        try:
            case.set_status(f.id, "verified!")  # a typo must never silently reopen
        except ValueError:
            pass
        else:  # pragma: no cover - fail-loud contract
            raise AssertionError("unknown status string must raise")
        assert f.status == FindingStatus.OPEN
