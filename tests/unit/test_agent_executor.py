"""S7 tests: school_execute."""

from __future__ import annotations

import shutil
import sys
import tempfile
from collections.abc import Iterator
from dataclasses import fields
from pathlib import Path

import pytest

from core.agent.executor import ExecuteResult, execute


@pytest.fixture
def worktree() -> Iterator[str]:
    """Isolated worktree via tempfile.mkdtemp (not tmp_path: OneDrive-safe)."""
    wt = tempfile.mkdtemp(prefix="school_exec_")
    try:
        yield wt
    finally:
        shutil.rmtree(wt, ignore_errors=True)


def _obs_file(wt: str) -> Path:
    return Path(wt) / ".school" / "agent" / "observations.jsonl"


class TestExecute:
    def test_execute_success(self, worktree: str) -> None:
        r = execute(worktree, f'"{sys.executable}" -c "print(1+1)"')
        assert r.ok is True
        assert r.exit_code == 0
        assert "2" in r.stdout

    def test_execute_failure(self, worktree: str) -> None:
        r = execute(worktree, f'"{sys.executable}" -c "import sys; sys.exit(1)"')
        assert r.ok is False
        assert r.exit_code == 1

    def test_execute_learns_on_success(self, worktree: str) -> None:
        r = execute(worktree, f'"{sys.executable}" -c "print(\'ok\')"', learn=True)
        assert r.ok is True
        assert r.learned != ""

    def test_execute_no_learn(self, worktree: str) -> None:
        r = execute(worktree, f'"{sys.executable}" -c "pass"', learn=False)
        assert r.ok is True
        assert r.learned == ""

    def test_execute_rejects_empty(self, worktree: str) -> None:
        r = execute(worktree, "")
        assert r.ok is False

    def test_execute_kill_switch(self, worktree: str, monkeypatch) -> None:
        monkeypatch.setenv("SCHOOL_EXECUTE", "0")
        r = execute(worktree, "echo test")
        assert r.ok is True
        assert r.command == "echo test"


class TestExecuteProcessManagement:
    def test_execute_cwd_uses_directory(self, worktree: str) -> None:
        target = Path(worktree) / "sub"
        target.mkdir()
        cmd = f'"{sys.executable}" -c "import os; print(os.getcwd())"'
        r = execute(worktree, cmd, cwd=str(target))
        assert r.ok is True
        assert target.name in r.stdout
        assert r.cwd is not None
        assert Path(r.cwd).name == target.name

    def test_execute_missing_cwd_errors(self, worktree: str) -> None:
        missing = str(Path(worktree) / "nope")
        r = execute(worktree, f'"{sys.executable}" -c "print(1)"', cwd=missing)
        assert r.ok is False
        assert r.error == f"cwd not found: {missing}"

    def test_execute_env_overrides_recorded(self, worktree: str) -> None:
        cmd = f'"{sys.executable}" -c "print(1)"'
        r = execute(worktree, cmd, env={"MY_VAR": "hello"})
        assert r.ok is True
        assert r.env_overrides == {"MY_VAR": "hello"}

    def test_execute_env_visible_to_command(self, worktree: str) -> None:
        cmd = f'"{sys.executable}" -c "import os; print(os.environ[\'MY_VAR\'])"'
        r = execute(worktree, cmd, env={"MY_VAR": "hello"})
        assert r.ok is True
        assert "hello" in r.stdout

    def test_execute_env_overrides_empty_without_env(self, worktree: str) -> None:
        r = execute(worktree, f'"{sys.executable}" -c "print(1)"')
        assert r.env_overrides == {}

    def test_execute_truncates_long_output(self, worktree: str) -> None:
        cmd = f'"{sys.executable}" -c "print(\'x\' * 500)"'
        r = execute(worktree, cmd, max_output=10)
        assert r.ok is True
        assert r.truncated is True
        assert len(r.stdout) <= 10
        assert len(r.stderr) <= 10

    def test_execute_no_truncation_for_short_output(self, worktree: str) -> None:
        r = execute(worktree, f'"{sys.executable}" -c "print(1)"')
        assert r.ok is True
        assert r.truncated is False

    def test_execute_returns_pid_field(self, worktree: str) -> None:
        r = execute(worktree, f'"{sys.executable}" -c "print(1)"')
        assert "pid" in {f.name for f in fields(ExecuteResult)}
        assert hasattr(r, "pid")
        assert r.pid is None or isinstance(r.pid, int)

    def test_execute_timeout_with_new_signature(self, worktree: str) -> None:
        slow = f'"{sys.executable}" -c "import time; time.sleep(5)"'
        r = execute(
            worktree,
            slow,
            timeout_ms=500,
            cwd=worktree,
            env={"MY_VAR": "hello"},
            max_output=100,
        )
        assert r.ok is False
        assert r.error == "timeout"
        assert r.duration_ms >= 0

    def test_execute_learn_false_suppresses_observation(self, worktree: str) -> None:
        r = execute(worktree, f'"{sys.executable}" -c "print(1)"', learn=False)
        assert r.ok is True
        assert not r.learned
        assert not _obs_file(worktree).exists()

    def test_execute_failure_notes_command_failure(self, worktree: str) -> None:
        r = execute(worktree, f'"{sys.executable}" -c "import sys; sys.exit(3)"')
        assert r.ok is False
        assert r.learned is not None
        assert "command failure" in r.learned

    def test_execute_empty_command_error(self, worktree: str) -> None:
        r = execute(worktree, "   ")
        assert r.ok is False
        assert r.error == "empty command"
