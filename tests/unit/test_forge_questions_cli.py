"""CLI boundary tests for the budgeted adaptive questioning controller.

`school elicit` controller mode (--question-budget / --session / --answers /
--no-followups / --no-early-stop). The legacy invocation must stay untouched.

ALL FIXTURES AND ANSWERS IN THIS FILE ARE SYNTHETIC.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "school" / "cli.py"


def _run(*args: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(REPO),
    )
    return proc.returncode, proc.stdout, proc.stderr


def _req(tmp_path: Path) -> Path:
    payload = {
        "goal": "Ship the synthetic launch brief",
        "unknowns": [
            {
                "id": "u-a",
                "question": "What is the deadline?",
                "variable": "deadline",
                "why_it_matters": "schedule",
                "affects": ["schedule"],
                "derivable": False,
                "must_ask_user": True,
                "wrong_assumption_cost": "high",
                "state": "UNKNOWN",
                "critical": True,
            },
            {
                "id": "u-b",
                "question": "Who is the audience?",
                "variable": "audience",
                "why_it_matters": "tone",
                "affects": ["correctness"],
                "derivable": False,
                "must_ask_user": True,
                "wrong_assumption_cost": "medium",
                "state": "UNKNOWN",
                "critical": False,
            },
            {
                "id": "u-c",
                "question": "What tone should it use?",
                "variable": "tone",
                "why_it_matters": "style",
                "affects": ["correctness"],
                "derivable": False,
                "must_ask_user": False,
                "wrong_assumption_cost": "low",
                "state": "UNKNOWN",
                "critical": False,
            },
        ],
    }
    path = tmp_path / "req.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class TestControllerMode:
    def test_legacy_output_has_no_budget_section(self, tmp_path: Path) -> None:
        req = _req(tmp_path)
        code, out, _err = _run("elicit", "--file", str(req))
        assert code == 0
        assert "## Question budget" not in out
        assert "## Completion status" in out
        assert "Assumptions are recorded as assumptions, never as facts." in out

    def test_custom_budget_enforced_at_cli(self, tmp_path: Path) -> None:
        req = _req(tmp_path)
        sess = tmp_path / "sess.json"
        code, out, _err = _run(
            "elicit", "--file", str(req), "--question-budget", "2", "--session", str(sess)
        )
        assert code == 0
        assert "- configured maximum: 2" in out
        assert "- presented: 2" in out
        assert "- remaining: 0" in out
        assert "budget-exhausted" in out
        assert "budget exhausted (not success)" in out
        assert sess.exists()
        state = json.loads(sess.read_text(encoding="utf-8"))
        assert state["version"] == 1
        assert state["presented"] == 2

    def test_invalid_budget_rejected_actionably(self, tmp_path: Path) -> None:
        req = _req(tmp_path)
        code, _out, err = _run("elicit", "--file", str(req), "--question-budget", "0")
        assert code == 2
        assert "invalid question budget" in err
        assert "at least 1" in err

    def test_resume_preserves_presented_count(self, tmp_path: Path) -> None:
        req = _req(tmp_path)
        sess = tmp_path / "sess.json"
        _run("elicit", "--file", str(req), "--question-budget", "2", "--session", str(sess))
        code, out, _err = _run("elicit", "--session", str(sess))
        assert code == 0
        assert "- presented: 2" in out
        assert "- remaining: 0" in out
        assert "budget-exhausted" in out
        # No fresh question may be presented after exhaustion.
        assert "remaining after:" not in out

    def test_config_drift_refused(self, tmp_path: Path) -> None:
        req = _req(tmp_path)
        sess = tmp_path / "sess.json"
        _run("elicit", "--file", str(req), "--question-budget", "2", "--session", str(sess))
        code, _out, err = _run(
            "elicit", "--session", str(sess), "--question-budget", "5"
        )
        assert code == 2
        assert "configuration is fixed for a resumed session" in err
        assert "start a new session" in err

    def test_answers_update_state_and_next_questions(self, tmp_path: Path) -> None:
        req = _req(tmp_path)
        ans = tmp_path / "ans.json"
        ans.write_text(
            json.dumps([{"id": "u-a", "answer": "March 1", "confidence": 1.0}]),
            encoding="utf-8",
        )
        code, out, _err = _run(
            "elicit",
            "--file",
            str(req),
            "--question-budget",
            "3",
            "--answers",
            str(ans),
        )
        assert code == 0
        assert "[KNOWN_FROM_USER]" in out
        assert "- `u-b` [original]" in out
        assert "- `u-a` [original]" not in out
        assert "- presented: 2" in out
        assert "- remaining: 1" in out

    def test_budget_section_renders_required_lines(self, tmp_path: Path) -> None:
        req = _req(tmp_path)
        code, out, _err = _run("elicit", "--file", str(req), "--question-budget", "5")
        assert code == 0
        for line in (
            "- configured maximum:",
            "- presented:",
            "- remaining:",
            "- follow-ups enabled:",
            "- early stopping:",
            "- why questioning stopped:",
            "- outcome:",
        ):
            assert line in out

    def test_help_lists_new_flags(self) -> None:
        code, out, _err = _run("elicit", "--help")
        assert code == 0
        for flag in (
            "--question-budget",
            "--session",
            "--answers",
            "--no-followups",
            "--no-early-stop",
        ):
            assert flag in out

    def test_unknown_answers_question_rejected(self, tmp_path: Path) -> None:
        req = _req(tmp_path)
        ans = tmp_path / "ans.json"
        ans.write_text(
            json.dumps([{"id": "u-nope", "answer": "42"}]),
            encoding="utf-8",
        )
        code, _out, err = _run("elicit", "--file", str(req), "--answers", str(ans))
        assert code == 2
        assert "elicit error" in err
        assert "not in this session" in err

    def test_followup_flag_shapes_budget_section(self, tmp_path: Path) -> None:
        req = _req(tmp_path)
        code, out, _err = _run(
            "elicit", "--file", str(req), "--question-budget", "5", "--no-followups"
        )
        assert code == 0
        assert "- follow-ups enabled: no" in out
