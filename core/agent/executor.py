"""S7: school_execute — run commands in managed processes, learn from outcomes.

PTY-grade process management: streaming capture with bounded retention,
explicit working directory and environment control, process metadata (pid),
tree-kill timeouts, and learn-from-outcome observations.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.agent.observer import safe_str

_DEFAULT_TIMEOUT_MS = 30000
_MAX_TIMEOUT_MS = 3_600_000.0
_DEFAULT_MAX_OUTPUT = 10000


@dataclass
class ExecuteResult:
    ok: bool = True
    command: str = ""
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    learned: str | None = None
    cwd: str | None = None
    env_overrides: dict[str, str] | None = None
    pid: int | None = None
    truncated: bool = False
    error: str | None = None


class _Capture:
    """Bounded streaming capture: keeps the first ``limit`` characters."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._parts: list[str] = []
        self._kept = 0
        self.dropped = 0

    def feed(self, line: str) -> None:
        if self._kept < self.limit:
            self._parts.append(line)
            self._kept += len(line)
        else:
            self.dropped += len(line)

    @property
    def text(self) -> str:
        return "".join(self._parts)[: self.limit]

    @property
    def truncated(self) -> bool:
        return self.dropped > 0 or self._kept > self.limit


def _drain(stream: Any, capture: _Capture) -> None:
    """Stream a pipe into a capture, draining past the limit.

    Draining continues after the retain window is full so the child never
    blocks writing into a full pipe.
    """
    try:
        for line in iter(stream.readline, ""):
            capture.feed(line)
    except (OSError, ValueError):
        pass  # fail-open: keep whatever was captured
    finally:
        with contextlib.suppress(OSError):
            stream.close()


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill a process and its descendants (shell=True spawns a wrapper)."""
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                timeout=15,
            )
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        with contextlib.suppress(OSError):
            proc.kill()


def _to_int(value: Any, default: int) -> int:
    """Coerce any value to int; never raises."""
    try:
        return int(value)
    except Exception:
        return default


def _to_timeout_s(value: Any) -> float:
    """Coerce a hostile-or-valid timeout_ms into seconds; never raises."""
    try:
        timeout_s = float(value) / 1000.0
    except Exception:
        return _DEFAULT_TIMEOUT_MS / 1000.0
    if timeout_s != timeout_s:  # NaN -> default
        return _DEFAULT_TIMEOUT_MS / 1000.0
    return min(max(0.001, timeout_s), _MAX_TIMEOUT_MS / 1000.0)


def execute(
    worktree: Path | str,
    command: str,
    learn: bool = True,
    context: str | None = None,
    timeout_ms: int = 30000,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    max_output: int = 10000,
) -> ExecuteResult:
    """Run a shell command in a managed process and learn from the outcome.

    ``cwd`` selects the working directory (defaults to the worktree), ``env``
    injects environment variables over ``os.environ``, ``max_output`` bounds
    the retained stdout/stderr, and ``context`` is echoed into the learning
    evidence when supplied.
    """
    if os.environ.get("SCHOOL_EXECUTE", "") == "0":
        return ExecuteResult(ok=True, command=safe_str(command))

    if not isinstance(command, str) or not command.strip():
        return ExecuteResult(ok=False, command=safe_str(command), error="empty command")

    # Resolve the working directory: explicit cwd wins, else the worktree.
    if cwd is not None:
        try:
            target = Path(cwd)
            is_dir = target.is_dir()
        except Exception:
            target, is_dir = None, False
        if target is None or not is_dir:
            return ExecuteResult(
                ok=False, command=command, error=f"cwd not found: {safe_str(cwd, 200)}"
            )
        try:
            used_cwd: str | None = str(target.resolve())
        except Exception:
            used_cwd = safe_str(target, 300)
    else:
        try:
            root = Path(worktree)
            used_cwd = str(root.resolve()) if root.is_dir() else None
        except Exception:
            used_cwd = None

    env_overrides: dict[str, str] = {}
    merged_env: dict[str, str] | None = None
    if env is not None:
        try:
            raw_pairs = list(env.items())
        except Exception:
            raw_pairs = None
        if raw_pairs is None:
            return ExecuteResult(
                ok=False, command=command, cwd=used_cwd, error="invalid env"
            )
        env_overrides = {safe_str(k, 200): safe_str(v) for k, v in raw_pairs}
        if env_overrides:
            merged_env = {**os.environ, **env_overrides}

    limit = max(1, _to_int(max_output, _DEFAULT_MAX_OUTPUT))
    wait_s = _to_timeout_s(timeout_ms)
    try:
        do_learn = bool(learn)
    except Exception:
        do_learn = False
    popen_kwargs: dict[str, Any] = {}
    if os.name != "nt":
        popen_kwargs["start_new_session"] = True

    start = time.monotonic()
    try:
        proc = subprocess.Popen(
            command,
            shell=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            cwd=used_cwd,
            env=merged_env,
            **popen_kwargs,
        )
    except Exception as exc:  # OSError/ValueError (embedded NUL) are fail-open
        return ExecuteResult(
            ok=False,
            command=command,
            cwd=used_cwd,
            env_overrides=env_overrides,
            error=safe_str(exc, 300) or type(exc).__name__,
        )

    out_capture = _Capture(limit)
    err_capture = _Capture(limit)
    readers = [
        threading.Thread(target=_drain, args=(proc.stdout, out_capture), daemon=True),
        threading.Thread(target=_drain, args=(proc.stderr, err_capture), daemon=True),
    ]
    for reader in readers:
        reader.start()

    timed_out = False
    try:
        proc.wait(timeout=wait_s)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_tree(proc)
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=5)
    for reader in readers:
        reader.join(timeout=5)

    duration_ms = int((time.monotonic() - start) * 1000)
    exit_code = proc.returncode if proc.returncode is not None else -1

    learned = ""
    if do_learn:
        try:
            from core.agent.observer import observe

            status = "success" if exit_code == 0 and not timed_out else "failure"
            obs = observe(
                safe_str(worktree, 300),
                f"command {status}: {command[:200]}",
                category="execute",
                evidence={
                    "exit_code": exit_code,
                    "duration_ms": duration_ms,
                    **({"context": safe_str(context)} if context else {}),
                },
            )
            learned = obs.learning
        except Exception:
            pass  # fail-open

    return ExecuteResult(
        ok=exit_code == 0 and not timed_out,
        command=command,
        exit_code=exit_code,
        stdout=out_capture.text,
        stderr=err_capture.text,
        duration_ms=duration_ms,
        learned=learned,
        cwd=used_cwd,
        env_overrides=env_overrides,
        pid=proc.pid,
        truncated=out_capture.truncated or err_capture.truncated,
        error="timeout" if timed_out else None,
    )


__all__ = ["ExecuteResult", "execute"]
