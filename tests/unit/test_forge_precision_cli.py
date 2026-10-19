"""school quantify / school elicit — CLI regression tests.

ALL INPUTS BELOW ARE SYNTHETIC TEST DATA (labelled); no real budgets, risks,
or user requirements appear. These tests exercise the JSON boundary of the
precision layer: string-typed enums must normalize, checks must fail closed,
and provenance must survive to the rendered report.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from school.cli import main

QUANT_INPUT = {
    "title": "Synthetic budget fixture",
    "currency": "USD",
    "budget": {
        "lines": [
            {"name": "tables", "amount": "60.00"},
            {"name": "signage", "amount": "40.00"},
            {"name": "snacks", "amount": "76.00"},
        ],
        "declared_total": "180.00",
        "ceiling_text": "TOTAL MONEY <= $200",
    },
    "percentages": [
        {"numerator": 80, "denominator": 300, "claimed": "27%", "scope": "books", "period": "wk6"}
    ],
    "changes": [{"before": 40, "after": 50}],
    "risks": [
        {
            "probability": 0.4,
            "conditional_loss": 250,
            "probability_class": "expert_judgment",
            "loss_unit": "USD",
            "probability_method": "organizer estimate",
            "probability_source": "Ada",
        }
    ],
    "scenarios": [
        {"probability": 0.5, "outcome": 100},
        {"probability": 0.3, "outcome": 250},
        {"probability": 0.2, "outcome": 400},
    ],
    "schedule": {
        "start": "2026-05-02",
        "deadline": "2026-04-25",
        "reference": "2026-01-15",
        "duration_days": 45,
    },
    "constraints": [
        {
            "id": "C1",
            "requirement": "EXACTLY 3 phases",
            "actual": 3,
            "kind": "hard",
            "evidence_kind": "machine_checked",
        },
        {
            "id": "C2",
            "requirement": "budget stays under 200",
            "kind": "hard",
            "actual": "176.00",
            "expected": "200",
            "evidence_kind": "simulated",
            "result": "satisfied",
            "explanation": "proxy check only",
        },
    ],
}

ELICIT_INPUT = {
    "goal": "Synthetic elicitation fixture",
    "requirements": [
        {"id": "r1", "kind": "hard_constraint", "text": "TOTAL MONEY <= 200 USD", "source": "user"},
    ],
    "unknowns": [
        {
            "id": "u-tax",
            "question": "Does sales tax apply to the ceiling?",
            "affects": ["cost"],
            "critical": True,
            "wrong_assumption_cost": "high",
            "state": "UNKNOWN",
        },
        {
            "id": "u-color",
            "question": "Tablecloth color?",
            "affects": [],
            "state": "NOT_APPLICABLE",
        },
        {
            "id": "u-assume",
            "question": "Volunteer count",
            "state": "ASSUMED_WITH_AUTHORIZATION",
            "why_it_matters": "staffing",
        },
    ],
    "verification_defined": False,
}


def _run(argv: list[str]) -> str:
    with patch("sys.argv", ["school", *argv]):
        main()
    return ""


@pytest.fixture()
def quant_file(tmp_path: Path) -> Path:
    p = tmp_path / "quant.json"
    p.write_text(json.dumps(QUANT_INPUT), encoding="utf-8")
    return p


@pytest.fixture()
def elicit_file(tmp_path: Path) -> Path:
    p = tmp_path / "elicit.json"
    p.write_text(json.dumps(ELICIT_INPUT), encoding="utf-8")
    return p


class TestQuantifyCLI:
    def test_budget_total_and_declared_mismatch_are_reported(
        self, quant_file: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _run(["quantify", "--file", str(quant_file)])
        out = capsys.readouterr().out
        assert "176.00" in out  # recomputed total
        assert "declared total 180.00 != recomputed sum 176.00" in out  # claim vs check
        assert "Remaining under ceiling" in out
        assert "24.00" in out

    def test_simulated_evidence_never_reaches_go(
        self, quant_file: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Regression: string-typed 'satisfied' + 'simulated' used to fall
        through every branch of validate_constraints and print GO."""
        _run(["quantify", "--file", str(quant_file)])
        out = capsys.readouterr().out
        assert "GO — every hard constraint satisfied" not in out
        assert "NO-GO" in out
        assert "simulated" in out

    def test_percent_claim_with_suffix_is_compared(
        self, quant_file: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _run(["quantify", "--file", str(quant_file)])
        out = capsys.readouterr().out
        assert "claimed 27% does not match recomputed" in out

    def test_pp_and_relative_are_distinct(
        self, quant_file: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _run(["quantify", "--file", str(quant_file)])
        out = capsys.readouterr().out
        assert "10 pp" in out
        assert "25.00" in out

    def test_schedule_violation_and_risk_provenance(
        self, quant_file: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _run(["quantify", "--file", str(quant_file)])
        out = capsys.readouterr().out
        assert "deadline 2026-04-25 precedes start 2026-05-02" in out
        assert "expert_judgment" in out  # probability class travels to the report
        assert "not a statistically calibrated probability" in out
        assert "sum_p = 1.0" in out  # scenario consistency is visible

    def test_missing_file_exits_2(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc:
            _run(["quantify"])
        assert exc.value.code == 2


class TestElicitCLI:
    def test_critical_unknowns_surface_and_na_never_asked(
        self, elicit_file: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _run(["elicit", "--file", str(elicit_file)])
        out = capsys.readouterr().out
        assert "u-tax" in out
        batch = out.split("Next question batch")[1].split("Completion status")[0]
        assert "u-color" not in batch  # NOT_APPLICABLE is never asked
        assert "u-assume" not in batch  # resolved assumptions are never asked

    def test_assumption_is_labelled_not_fact(
        self, elicit_file: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _run(["elicit", "--file", str(elicit_file)])
        out = capsys.readouterr().out
        assert "assumed, not fact" in out

    def test_status_blocks_on_unverified_critical(
        self, elicit_file: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _run(["elicit", "--file", str(elicit_file)])
        out = capsys.readouterr().out
        assert "complete: no" in out
        assert "u-tax" in out.split("blocking:")[1]
        assert "verification defined: no" in out

    def test_missing_file_exits_2(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc:
            _run(["elicit"])
        assert exc.value.code == 2

    def test_interview_adapter_smoke(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from core.forge.clarion import auto_answer, start_interview
        from core.forge.models import Domain

        interview = auto_answer(start_interview(title="T", domain=Domain.WRITING))
        p = tmp_path / "interview.json"
        p.write_text(json.dumps(interview.to_dict()), encoding="utf-8")
        _run(["elicit", "--interview", str(p)])
        out = capsys.readouterr().out
        assert "Elicitation" in out
        assert "Completion status" in out


class TestBoundaryInputShapes:
    """Regression: pair-shaped rows must count; malformed rows must fail closed."""

    @staticmethod
    def _write(tmp_path: Path, payload: dict) -> Path:
        p = tmp_path / "in.json"
        p.write_text(json.dumps(payload), encoding="utf-8")
        return p

    def test_money_pair_rows_are_counted_not_dropped(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        p = self._write(
            tmp_path,
            {
                "title": "pair tax",
                "currency": "USD",
                "budget": {
                    "lines": [{"name": "tables", "amount": "60.00"}],
                    "tax": [["tax", "8.80"]],
                },
            },
        )
        _run(["quantify", "--file", str(p)])
        out = capsys.readouterr().out
        assert "68.80" in out
        assert "tax = 0" not in out

    def test_unrecognized_budget_rows_fail_closed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        p = self._write(
            tmp_path,
            {
                "title": "bad tax",
                "currency": "USD",
                "budget": {"lines": [{"name": "tables", "amount": "60.00"}], "tax": ["junk"]},
            },
        )
        _run(["quantify", "--file", str(p)])
        out = capsys.readouterr().out
        assert "no total is claimed" in out
        assert "unparsed row" in out
        assert "68.80" not in out

    def test_scenario_pair_rows_are_parsed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        p = self._write(
            tmp_path,
            {
                "title": "pair scenarios",
                "currency": "USD",
                "scenarios": [[0.6, 100], [0.6, 200]],
            },
        )
        _run(["quantify", "--file", str(p)])
        out = capsys.readouterr().out
        assert "empty space" not in out
        assert "not 1" in out

    def test_unrecognized_scenario_rows_fail_closed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        p = self._write(tmp_path, {"title": "bad scen", "currency": "USD", "scenarios": ["junk"]})
        _run(["quantify", "--file", str(p)])
        out = capsys.readouterr().out
        assert "no E[X] is claimed" in out
        assert "unparsed row" in out


class TestUnparsedRowVisibility:
    """Regression (Mission 20 case a): malformed rows beside valid rows were
    silently dropped — an unreadable hard constraint still printed 'GO — every
    hard constraint satisfied on real evidence'. Now every unparsed row is
    named and collective claims fail closed. ALL FIXTURES SYNTHETIC."""

    @staticmethod
    def _write(tmp_path: Path, payload: dict) -> Path:
        p = tmp_path / "mix.json"
        p.write_text(json.dumps(payload), encoding="utf-8")
        return p

    def test_unparsed_rows_are_reported_in_every_section(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        p = self._write(
            tmp_path,
            {
                "title": "synthetic mixture",
                "currency": "USD",
                "budget": {"lines": [{"name": "signage", "amount": 40}]},
                "percentages": [
                    {
                        "numerator": 80,
                        "denominator": 300,
                        "scope": "s",
                        "period": "p",
                        "source": "s",
                    },
                    42,
                ],
                "changes": [{"before": 40, "after": 50}, "not-a-change-row"],
                "risks": [
                    {
                        "conditional_loss": 250,
                        "probability": 0.3,
                        "probability_class": "expert_judgment",
                        "loss_unit": "USD",
                        "probability_method": "synthetic",
                        "probability_source": "synthetic",
                        "source": "synthetic",
                    },
                    99,
                ],
                "availability": [
                    {"item": "hall", "as_of": "2026-03-01", "available_from": "2026-04-01"},
                    ["hall2", "2026-03-01"],
                ],
                "constraints": [
                    {
                        "id": "H1",
                        "requirement": "EXACTLY 3 phases in the plan",
                        "kind": "hard",
                        "actual": "3 phases",
                        "expected": "3",
                        "evidence_source": "synthetic",
                        "evidence_kind": "machine_checked",
                        "result": "satisfied",
                    },
                    "not-a-constraint-row",
                ],
            },
        )
        _run(["quantify", "--file", str(p)])
        out = capsys.readouterr().out
        for repr_frag in (
            "42",
            "'not-a-change-row'",
            "99",
            "['hall2', '2026-03-01']",
            "'not-a-constraint-row'",
        ):
            assert f"unparsed row: {repr_frag}" in out
        assert out.count("unrecognized shape") == 5

    def test_unparsed_constraint_row_blocks_go(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """An unreadable hard-constraint row must void the GO claim."""
        p = self._write(
            tmp_path,
            {
                "title": "synthetic",
                "constraints": [
                    {
                        "id": "H1",
                        "requirement": "hold",
                        "kind": "hard",
                        "evidence_kind": "machine_checked",
                        "result": "satisfied",
                    },
                    "not-a-constraint-row",
                ],
            },
        )
        _run(["quantify", "--file", str(p)])
        out = capsys.readouterr().out
        assert "GO — every hard constraint satisfied" not in out
        assert "NO-GO" in out
        assert "INPUT-ERROR" in out
        assert "checklist is incomplete" in out

    def test_valid_rows_still_compute_beside_unparsed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        p = self._write(
            tmp_path,
            {
                "title": "synthetic",
                "percentages": [
                    {
                        "numerator": 80,
                        "denominator": 300,
                        "scope": "s",
                        "period": "p",
                        "source": "s",
                    },
                    42,
                ],
                "changes": [{"before": 40, "after": 50}, "junk"],
            },
        )
        _run(["quantify", "--file", str(p)])
        out = capsys.readouterr().out
        assert "26.67" in out
        assert "10 pp" in out
        assert "25.00" in out

    def test_clean_input_reports_no_unparsed_noise(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        p = self._write(
            tmp_path,
            {
                "title": "synthetic clean",
                "currency": "USD",
                "percentages": [
                    {
                        "numerator": 80,
                        "denominator": 300,
                        "scope": "s",
                        "period": "p",
                        "source": "s",
                    }
                ],
            },
        )
        _run(["quantify", "--file", str(p)])
        out = capsys.readouterr().out
        assert "unparsed row" not in out
        assert "unrecognized shape" not in out

    def test_unparsed_unknown_blocks_completion(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        p = self._write(
            tmp_path,
            {
                "title": "synthetic",
                "goal": "synthetic goal",
                "unknowns": [
                    {
                        "id": "u-done",
                        "question": "resolved question",
                        "variable": "v",
                        "state": "KNOWN_FROM_USER",
                    },
                    "not-an-unknown-row",
                ],
                "verification_defined": True,
            },
        )
        _run(["elicit", "--file", str(p)])
        out = capsys.readouterr().out
        assert "Unparsed input rows" in out
        assert "u:unparsed:1" in out
        assert "complete: no" in out
        assert "u:unparsed:1" in out.split("blocking:")[1]


class TestPhaseCountWords:
    """Regression (Mission 20 case e): word-number phase counts were unenforced
    at the CLI boundary ('exactly three phases' + actual 4 → n_a → no block).
    ALL FIXTURES SYNTHETIC."""

    @staticmethod
    def _write(tmp_path: Path, payload: dict) -> Path:
        p = tmp_path / "phase.json"
        p.write_text(json.dumps(payload), encoding="utf-8")
        return p

    def test_word_number_violation_blocks_go(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        p = self._write(
            tmp_path,
            {
                "title": "synthetic",
                "constraints": [
                    {
                        "id": "H1",
                        "requirement": "EXACTLY three phases in the plan",
                        "kind": "hard",
                        "actual": "4 phases",
                    }
                ],
            },
        )
        _run(["quantify", "--file", str(p)])
        out = capsys.readouterr().out
        assert "GO — every hard constraint satisfied" not in out
        assert "NO-GO" in out
        assert "requirement says 3" in out

    def test_word_number_satisfied_reaches_go(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        p = self._write(
            tmp_path,
            {
                "title": "synthetic",
                "constraints": [
                    {
                        "id": "H1",
                        "requirement": "EXACTLY three phases in the plan",
                        "kind": "hard",
                        "actual": "3 phases",
                    }
                ],
            },
        )
        _run(["quantify", "--file", str(p)])
        out = capsys.readouterr().out
        assert "GO — every hard constraint satisfied" in out


class TestScheduleVerdictIntegrity:
    """SYNTHETIC fixtures — F-004 policy: contradictions hard, time-relative warnings only."""

    _SAT = {
        "id": "H1",
        "requirement": "total money at most $200",
        "kind": "hard",
        "validation_method": "sum",
        "actual": "176.00",
        "expected": "176.00",
        "evidence_source": "budget",
        "evidence_kind": "machine_checked",
        "result": "satisfied",
        "explanation": "",
    }

    @staticmethod
    def _write(tmp_path: Path, payload: dict) -> Path:
        p = tmp_path / "sched.json"
        p.write_text(json.dumps(payload), encoding="utf-8")
        return p

    def test_contradictory_schedule_forces_no_go(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        p = self._write(
            tmp_path,
            {
                "schedule": {"start": "2026-03-15", "deadline": "2026-03-01"},
                "constraints": [dict(self._SAT)],
            },
        )
        _run(["quantify", "--file", str(p)])
        out = capsys.readouterr().out
        assert "NO-GO" in out
        assert "- blocking: SCHEDULE-1" in out
        assert "precedes start" in out
        assert "GO \u2014 every hard constraint satisfied" not in out

    def test_expired_reference_stays_go_with_warning_note(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        p = self._write(
            tmp_path,
            {
                "schedule": {
                    "start": "2026-01-01",
                    "deadline": "2026-02-01",
                    "reference": "2026-04-01",
                },
                "constraints": [dict(self._SAT)],
            },
        )
        _run(["quantify", "--file", str(p)])
        out = capsys.readouterr().out
        assert "GO \u2014 every hard constraint satisfied" in out
        assert "NO-GO" not in out
        assert "time-relative schedule warning" in out
        assert "expired dependency" in out

    def test_missing_dates_leave_satisfied_verdict_untouched(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        p = self._write(tmp_path, {"constraints": [dict(self._SAT)]})
        _run(["quantify", "--file", str(p)])
        out = capsys.readouterr().out
        assert "GO \u2014 every hard constraint satisfied" in out
        assert "nothing is certified" not in out
        assert "time-relative" not in out

    def test_contradiction_without_rows_blocks_instead_of_certifying(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        p = self._write(
            tmp_path,
            {"schedule": {"start": "2026-03-15", "deadline": "2026-03-01"}},
        )
        _run(["quantify", "--file", str(p)])
        out = capsys.readouterr().out
        assert "NO-GO" in out
        assert "SCHEDULE-1" in out
        assert "nothing is certified" not in out
