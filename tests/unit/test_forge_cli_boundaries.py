"""Forge CLI input-boundary tests (Mission 20.1, case F-010).

ALL FIXTURES AND INPUTS ARE SYNTHETIC. These tests lock CLI-layer behaviour at
the high-risk boundaries: malformed JSON, wrong-shaped JSON, unexpected field
types, silent data loss, and success-despite-failed-hard-constraint.

Pre-fix behaviour (recorded by m21_boundary_probe.py before the fix):
a non-dict --interview JSON exited 0 and fabricated an empty
"# Blueprint - General Blueprint" artifact with ZERO warning (silent success).
The tests below pin the fail-closed contract that replaced it.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "school" / "cli.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(REPO),
    )


def _write(tmp_path: Path, name: str, payload: object) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _interview(constraint_text: str) -> dict:
    return {
        "title": "Boundary probe",
        "domain": "writing",
        "questions": [
            {
                "id": "constraints-1",
                "dimension": "constraints",
                "prompt": "Hard rules?",
                "type": "text",
            },
            {"id": "sequence-1", "dimension": "sequence", "prompt": "First?", "type": "text"},
            {"id": "sequence-2", "dimension": "sequence", "prompt": "Second?", "type": "text"},
            {"id": "sequence-3", "dimension": "sequence", "prompt": "Third?", "type": "text"},
        ],
        "answers": [
            {"question_id": "constraints-1", "value": constraint_text, "confidence": 1.0},
            {"question_id": "sequence-1", "value": "Define the scope", "confidence": 1.0},
            {"question_id": "sequence-2", "value": "Organize the work", "confidence": 1.0},
            {"question_id": "sequence-3", "value": "Wrap it up", "confidence": 1.0},
        ],
    }


class TestMalformedJson:
    def test_malformed_interview_json_exits_2(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("not json", encoding="utf-8")
        proc = _run("blueprint", "--interview", str(bad))
        assert proc.returncode == 2
        assert "invalid --interview JSON" in proc.stderr

    def test_malformed_answers_json_exits_2(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{oops", encoding="utf-8")
        proc = _run("clarion", "--title", "Boundary probe", "--answers", str(bad))
        assert proc.returncode == 2
        assert "invalid --answers JSON" in proc.stderr


class TestWrongShapeFailsClosed:
    def test_non_dict_interview_json_exits_2(self, tmp_path: Path) -> None:
        """A non-object --interview is unreadable input, not an empty project.

        Before the fix this exited 0 and fabricated "# Blueprint - General
        Blueprint" (coverage 0%) with zero warning.
        """
        lst = _write(tmp_path, "list.json", [1, 2, 3])
        proc = _run("blueprint", "--interview", str(lst))
        assert proc.returncode == 2
        assert "must be a JSON object" in proc.stderr
        assert "General Blueprint" not in proc.stdout

    def test_non_dict_file_json_exits_2(self, tmp_path: Path) -> None:
        lst = _write(tmp_path, "list.json", [1, 2, 3])
        proc = _run("quantify", "--file", str(lst))
        assert proc.returncode == 2
        assert "must be a JSON object" in proc.stderr

    def test_non_list_commands_json_exits_2(self, tmp_path: Path) -> None:
        scalar = _write(tmp_path, "scalar.json", 42)
        proc = _run("weave", "--commands", str(scalar))
        assert proc.returncode == 2
        assert "must be a list of commands" in proc.stderr

    def test_commands_object_without_list_exits_2(self, tmp_path: Path) -> None:
        obj = _write(tmp_path, "obj.json", {"not": "commands"})
        proc = _run("weave", "--commands", str(obj))
        assert proc.returncode == 2
        assert "must be a list of commands" in proc.stderr

    def test_junk_command_rows_warn_not_silently_dropped(self, tmp_path: Path) -> None:
        """Rows that are not command objects are ignored loudly, not silently."""
        lst = _write(tmp_path, "list.json", [1, 2, 3])
        proc = _run("weave", "--commands", str(lst))
        assert proc.returncode == 0
        assert "forge warning: 3 --commands row(s) were not objects" in proc.stderr


class TestPhaseCountAtCli:
    def test_exactly_n_phases_honored_at_cli(self, tmp_path: Path) -> None:
        iv = _write(tmp_path, "iv.json", _interview("EXACTLY 2 phases"))
        proc = _run("edict", "--interview", str(iv))
        assert proc.returncode == 0
        headings = re.findall(r"^### Phase \d+", proc.stdout, flags=re.MULTILINE)
        assert len(headings) == 2
        assert "Define the scope" in proc.stdout

    def test_contradictory_phase_counts_first_match_wins(self, tmp_path: Path) -> None:
        """Documented limitation, NOT fixed here (policy gap, reported).

        'EXACTLY 2 phases and also EXACTLY 3 phases' - the first matching count
        wins; the second count is silently dropped from the structure but the
        full contradictory text is preserved in the directive row.
        """
        iv = _write(tmp_path, "iv.json", _interview("EXACTLY 2 phases and also EXACTLY 3 phases"))
        proc = _run("edict", "--interview", str(iv))
        assert proc.returncode == 0
        headings = re.findall(r"^### Phase \d+", proc.stdout, flags=re.MULTILINE)
        assert len(headings) == 2
        assert "EXACTLY 2 phases and also EXACTLY 3 phases" in proc.stdout


class TestUnexpectedFieldTypes:
    def test_evil_field_types_do_not_crash(self, tmp_path: Path) -> None:
        """Models coercion is deliberate fail-open; rendering must not crash.

        Observed (m21_boundary_probe.py): domain 42 coerces to General and a
        dict-valued title leaks its repr into the heading - cosmetic gaps kept
        as documented behaviour, not crashes and not silent data loss.
        """
        iv = _write(
            tmp_path,
            "evil.json",
            {
                "title": {"nested": "dict-title"},
                "domain": 42,
                "mode": ["list"],
                "questions": [
                    {"id": "constraints-1", "dimension": "constraints", "prompt": "Hard rules?"},
                ],
                "answers": [
                    {"question_id": "constraints-1", "value": ["a", "b"], "confidence": "high"},
                ],
            },
        )
        proc = _run("edict", "--interview", str(iv))
        assert proc.returncode == 0
        assert "Edict" in proc.stdout
