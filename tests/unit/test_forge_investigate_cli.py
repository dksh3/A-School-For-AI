"""CLI-layer tests for ``school investigate``.

ALL FIXTURES AND PROBE COMMANDS ARE SYNTHETIC. No real-world accuracy or
human validation is claimed anywhere in this file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from core.forge.investigate import Investigation


def _case_file(tmp_path: Path) -> Path:
    """Build a small synthetic case and persist it. Returns the case path."""
    case = Investigation.start(
        "INV-CLI",
        "CLI synthetic case",
        scope="synthetic scope — CLI wiring only",
    )
    ev = case.add_evidence("command", ref="fixture", detail="exit=0\nsynthetic fixture output")
    case.attach_evidence(
        case.add_finding(
            "Synthetic finding for CLI wiring",
            severity="must-fix",
            component="tests",
            entry_point="test_forge_investigate_cli",
            expected="the handler renders the case",
            observed="pending",
            reproduction="run school investigate --file <case>",
            classification="CONFIRMED DEFECT",
            confidence=0.9,
            confidence_justification="synthetic fixture",
        ).id,
        ev.id,
    )
    path = tmp_path / "case.json"
    case.save(path)
    return path


def _run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    """Invoke school.cli.main() in-process with argv; returns (exit, out, err)."""
    old = sys.argv
    sys.argv = ["school", *argv]
    code = 0
    try:
        import school.cli

        school.cli.main()
    except SystemExit as exc:
        code = int(exc.code or 0)
    finally:
        sys.argv = old
    captured = capsys.readouterr()
    return code, captured.out, captured.err


class TestInvestigateCLI:
    def test_report_action_renders_case(self, tmp_path: Path, capsys) -> None:
        path = _case_file(tmp_path)
        code, out, _ = _run(["investigate", "--file", str(path)], capsys)
        assert code == 0
        assert "Synthetic finding for CLI wiring" in out
        assert "INV-CLI" in out

    def test_report_action_is_honest(self, tmp_path: Path, capsys) -> None:
        case = Investigation.start("INV-H", "Honest report check", scope="synthetic")
        case.add_finding(
            "Finding with no evidence yet",
            severity="note",
            component="tests",
            entry_point="cli",
            expected="evidence before closure",
            observed="none recorded",
            reproduction_unavailable="synthetic — nothing to run",
            classification="UNKNOWN",
            confidence=0.1,
            confidence_justification="none yet",
        )
        path = tmp_path / "case.json"
        case.save(path)
        _, out, _ = _run(["investigate", "--file", str(path)], capsys)
        assert "NONE RECORDED" in out
        assert "does not claim exhaustive discovery" in out

    def test_probe_records_and_persists(self, tmp_path: Path, capsys) -> None:
        path = _case_file(tmp_path)
        code, out, _ = _run(
            [
                "investigate",
                "--file",
                str(path),
                "--action",
                "probe",
                "--probe-cmd",
                "echo probe-ok",
            ],
            capsys,
        )
        assert code == 0
        assert "Probe evidence" in out
        assert "probe-ok" in out
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert any("probe-ok" in json.dumps(e) for e in saved.get("evidence", []))

    def test_probe_ids_increment_across_runs(self, tmp_path: Path, capsys) -> None:
        import re

        path = _case_file(tmp_path)
        _, out1, _ = _run(
            ["investigate", "--file", str(path), "--action", "probe",
             "--probe-cmd", "echo one"],
            capsys,
        )
        _, out2, _ = _run(
            ["investigate", "--file", str(path), "--action", "probe",
             "--probe-cmd", "echo two"],
            capsys,
        )
        id1 = re.search(r"Probe evidence (E-\d+)", out1)
        id2 = re.search(r"Probe evidence (E-\d+)", out2)
        assert id1 is not None and id2 is not None
        # stable incrementing ids across resumable runs (fixture may pre-create E-001)
        assert int(id2.group(1)[2:]) == int(id1.group(1)[2:]) + 1

    def test_status_action_renders_assessment(self, tmp_path: Path, capsys) -> None:
        path = _case_file(tmp_path)
        code, out, _ = _run(
            ["investigate", "--file", str(path), "--action", "status"], capsys
        )
        assert code == 0
        assert "Investigation status" in out
        assert "INV-CLI" in out

    def test_next_action_uses_the_loop(self, tmp_path: Path, capsys) -> None:
        path = _case_file(tmp_path)
        code, out, _ = _run(
            ["investigate", "--file", str(path), "--action", "next"], capsys
        )
        assert code == 0
        assert "Next action" in out
        # CONFIRMED DEFECT + OPEN -> fix
        assert "fix" in out

    def test_missing_file_exits_2(self, capsys) -> None:
        code, _, err = _run(["investigate"], capsys)
        assert code == 2
        assert "--file is required" in err

    def test_bad_json_exits_2(self, tmp_path: Path, capsys) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        code, _, err = _run(["investigate", "--file", str(bad)], capsys)
        assert code == 2
        assert "cannot load case JSON" in err

    def test_probe_requires_cmd(self, tmp_path: Path, capsys) -> None:
        path = _case_file(tmp_path)
        code, _, err = _run(
            ["investigate", "--file", str(path), "--action", "probe"], capsys
        )
        assert code == 2
        assert "--probe-cmd is required" in err

    def test_save_writes_report(self, tmp_path: Path, capsys) -> None:
        path = _case_file(tmp_path)
        dest = tmp_path / "report.md"
        code, _, _ = _run(
            ["investigate", "--file", str(path), "--save", str(dest)], capsys
        )
        assert code == 0
        assert dest.exists()
        assert "Synthetic finding for CLI wiring" in dest.read_text(encoding="utf-8")
