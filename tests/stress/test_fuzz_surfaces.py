"""Adversarial fail-open fuzz campaign for the School SURFACE layer.

Surfaces under attack
--------------------
A. ``school/bridge.py`` — the JSON bridge ``main()`` wire: every one of the 40
   ``_COMMANDS`` plus protocol-level hostile inputs (unknown/missing/unhashable
   command, non-JSON garbage, empty lines, non-object JSON, huge payloads),
   fed both in-process (monkeypatched stdin) and through real subprocess pipes.
B. ``_dispatch_to_orchestrator`` + ``_safe_dump`` — hostile Python objects.
C. ``school/mcp/server.py`` — ``_route_result``, ``_bridge_call``,
   ``_build_request``, ``_call_tool`` (42 tools) and the ``SCHOOL_PREFERRED``
   dominance suffix on every tool description.
D. ``school/cli.py`` — argparse + every subcommand with hostile argv (including
   non-str entries), and ``_cmd_visualize`` with hostile visual types/data.
E. ``school/plugin_source.py`` — TS_PLUGIN_SOURCE structural invariants,
   hostile version rendering, and real ``node --check`` syntax validation.

FAIL-OPEN INVARIANT: every surface, given ANY input, must emit a valid
response (strict JSON / graceful result / valid TS) and NEVER raise out of
the surface boundary. Exceptions raised by fuzzed calls are recorded as
failures by ``fuzz_fail_open``.

Two sanctioned graceful channels exist (pinned by the unit-test suite and
therefore treated as results, not crashes):
* ``argparse`` SystemExit(2) with usage text (tests/unit/test_cli_skills.py),
* ``mcp.server._call_tool`` ValueError("Unknown tool"/validation) which the
  MCP framework converts into a JSON-RPC error response.

Network/latency kill-switches (``SCHOOL_SKILLGEN_GITHUB_DISABLED=1`` and
``SCHOOL_DOCS=0``) are enabled during fuzzing so 2000-iteration labels stay
fast; the real network paths are exercised once each by a bounded live smoke
test at the end. Worktrees and HOME are sandboxed under ``tempfile.mkdtemp``
so no fuzz input can write outside the sandbox.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import random
import re
import shutil
import subprocess
import sys
import tempfile
import zlib
from types import SimpleNamespace
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from fuzz_harness import (  # noqa: E402
    FUZZ_FAILURES,
    FUZZ_LEDGER,
    HOSTILE,
    fuzz_fail_open,
    gen_json_safe,
    ledger_summary,
)

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest  # noqa: E402

from school import bridge, plugin_source  # noqa: E402
from school import cli as school_cli  # noqa: E402

N = 2000  # iterations per fuzz label
NODE = shutil.which("node")

try:  # the `mcp` package is optional; MCP labels run only when importable
    from school.mcp import server as mcp_server
except Exception:  # noqa: BLE001
    mcp_server = None  # type: ignore[assignment]

requires_mcp = pytest.mark.skipif(mcp_server is None, reason="mcp package not installed")
requires_node = pytest.mark.skipif(NODE is None, reason="node not on PATH")


# ---------------------------------------------------------------------------
# Strict JSON + safe-string helpers (the invariants under test)
# ---------------------------------------------------------------------------

def _strict_load(text: str) -> Any:
    """json.loads that rejects NaN/Infinity/-Infinity literals (RFC 8259)."""
    def _bad(name: str) -> None:
        raise ValueError(f"non-strict JSON constant in output: {name}")
    return json.loads(text, parse_constant=_bad)


def _safe_str(value: Any) -> str:
    try:
        return str(value)
    except Exception:  # noqa: BLE001
        try:
            return repr(value)
        except Exception:  # noqa: BLE001
            return f"<{type(value).__name__}>"


# ---------------------------------------------------------------------------
# JSON-encodable hostile corpus (survives a json.dumps wire round-trip)
# ---------------------------------------------------------------------------

JHOSTILE: list[Any] = [
    None, True, False, 0, -1, 1, 2**63, -(2**63) - 1, 10**50, -(10**50),
    3.14, -0.0, float("inf"), float("-inf"), float("nan"),
    "", " ", "\t", "\n", "\r\n", "\x00", "null\x00byte", "a\x00b",
    "🔥💀émoji ünïcödé", "​zero​width​", "\U0001f4a9" * 100,
    "line\nbreaks\ttabbed", " " * 5000, "X" * 50_000,
    "répétition" * 500, "{}{}{}".format("{x}", "{y}", "{z}"),
    "1e999", "-1e999", "\ud800", "\udfff", "\\u0000", "%s%n%x",
    "C:\\nope", "..\\..\\..\\..\\..\\..\\..\\..\\evil",
    "\\\\?\\C:\\weird", "//server/share/x", "con", "nul", "*", "?",
    [], [None], [1, 2, [3, {"x": None}]], {}, {"a": 1},
    {"nested": {"deep": [1, 2, {"x": None}]}}, {"k" * 200: "v" * 200},
]

# Curated benign/garbage shell commands for the `execute` surface: hostile
# enough to break parsers, never destructive.
EXEC_CMDS = [
    "", " ", "\t", "zzz_school_fuzz_nonexistent_12345", "echo school-fuzz",
    "🔥 unicode cmd", "X" * 2000, "{}{}{x}", "a\x00b", "echo fuzz & echo fuzz2",
    "exit 3", "cmd /c echo school-fuzz",
]


def _deep(depth: int) -> Any:
    """A deep-but-linear hostile structure (a true chain: no shared children,
    so JSON encode/decode stays O(depth) — wire JSON cannot carry sharing)."""
    node: Any = 0
    for _ in range(depth):
        node = {"a": node, "b": [1, 2], "c": "x"}
    return node


def _jvalue(rng: random.Random, depth: int = 0) -> Any:
    """A random JSON-encodable hostile value."""
    pick = rng.randint(0, 5)
    if pick == 0 or depth > 3:
        return rng.choice(JHOSTILE)
    if pick == 1:
        return [_jvalue(rng, depth + 1) for _ in range(rng.randint(0, 3))]
    if pick == 2:
        return {f"k{rng.randint(0, 9)}": _jvalue(rng, depth + 1)
                for _ in range(rng.randint(0, 3))}
    if pick == 3:
        return _deep(rng.randint(5, 40))
    if pick == 4:
        return rng.choice(["worktree", "content", "query", "text", "data"])
    return rng.choice(JHOSTILE)


# ---------------------------------------------------------------------------
# Sandbox fixture: worktrees, HOME, env kill-switches, safe CWD
# ---------------------------------------------------------------------------

SANDBOX: str = ""
WT_BASE: str = ""      # deeply nested worktree root (traversal containment)
HOME_DIR: str = ""     # sandboxed Path.home() for install/uninstall fuzz
_RESTORE: dict[str, Any] = {}


@pytest.fixture(scope="module", autouse=True)
def sandbox() -> Any:
    global SANDBOX, WT_BASE, HOME_DIR
    SANDBOX = tempfile.mkdtemp(prefix="school_fuzz_")
    wt = pathlib.Path(SANDBOX)
    for level in range(8):  # 8 nested levels: bounded `..` traversal stays in
        wt = wt / f"L{level}"
    wt.mkdir(parents=True)
    WT_BASE = str(wt)
    HOME_DIR = os.path.join(SANDBOX, "home")
    os.makedirs(HOME_DIR, exist_ok=True)

    _RESTORE["cwd"] = os.getcwd()
    _RESTORE["env"] = {
        k: os.environ.get(k)
        for k in ("USERPROFILE", "HOME", "SCHOOL_SKILLGEN_GITHUB_DISABLED",
                  "SCHOOL_DOCS", "SCHOOL_EXECUTE", "PYTHONIOENCODING")
    }
    os.chdir(SANDBOX)
    os.environ["USERPROFILE"] = HOME_DIR
    os.environ["HOME"] = HOME_DIR
    os.environ["SCHOOL_SKILLGEN_GITHUB_DISABLED"] = "1"
    os.environ["SCHOOL_DOCS"] = "0"
    os.environ["PYTHONIOENCODING"] = "utf-8"

    # Bare `school mcp` must never enter the blocking stdio server loop when
    # fuzzing argv routing. The server internals are fuzzed in section C.
    _RESTORE["mcp_main"] = None
    if mcp_server is not None:
        _RESTORE["mcp_main"] = mcp_server.main
        mcp_server.main = lambda: None  # type: ignore[assignment]

    yield

    if mcp_server is not None and _RESTORE["mcp_main"] is not None:
        mcp_server.main = _RESTORE["mcp_main"]  # type: ignore[assignment]
    os.chdir(_RESTORE["cwd"])
    for key, value in _RESTORE["env"].items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    shutil.rmtree(SANDBOX, ignore_errors=True)


def map_wt(value: Any, i: int = 0) -> Any:
    """Keep worktree hostility but guarantee writes stay inside the sandbox.

    Non-str values and NUL-strings are passed through (every path operation
    fails on them, so no disk writes can happen). Relative values (including
    bounded ``..`` traversal) pass through untouched when they resolve inside
    the sandbox; everything else is re-rooted under it.
    """
    if not isinstance(value, str) or "\x00" in value:
        return value
    root = os.path.normpath(SANDBOX)
    is_abs = os.path.isabs(value) or (len(value) >= 2 and value[1] == ":")
    if is_abs or value.startswith("\\\\"):
        tail = re.sub(r"[^A-Za-z0-9._-]", "_", value)[-40:]
        return os.path.join(SANDBOX, f"abs{i}_{tail}")
    joined = os.path.normpath(os.path.join(WT_BASE, value))
    if joined == root or joined.startswith(root + os.sep):
        return joined
    tail = re.sub(r"[^A-Za-z0-9._-]", "_", value)[-40:]
    return os.path.join(WT_BASE, f"esc{i}_{tail}")


# ---------------------------------------------------------------------------
# Bridge in-process runner (monkeypatched stdin/stdout — the real main())
# ---------------------------------------------------------------------------

def run_bridge_main(raw: str) -> str:
    old_in, old_out = sys.stdin, sys.stdout
    sys.stdin, sys.stdout = io.StringIO(raw), io.StringIO()
    try:
        bridge.main()
        return sys.stdout.getvalue()
    finally:
        sys.stdin, sys.stdout = old_in, old_out


def _check_main_out(out: str) -> None:
    data = _strict_load(out)
    assert isinstance(data, dict), f"bridge response is not a JSON object: {type(data)}"
    assert "ok" in data, f"bridge response missing 'ok': {_safe_str(data)[:120]}"


# ---------------------------------------------------------------------------
# Per-command valid request shapes (used as the base of every mutation)
# ---------------------------------------------------------------------------

def valid_req(cmd: str) -> dict[str, Any]:
    wt = WT_BASE
    table: dict[str, dict[str, Any]] = {
        "status": {"worktree": wt},
        "remember": {"worktree": wt, "content": "fuzz fact", "outcome": "SUCCESS"},
        "recall": {"worktree": wt, "query": "fuzz"},
        "learn": {"worktree": wt, "content": "fuzz lesson", "outcome": "SUCCESS"},
        "diagnose": {"worktree": wt, "detail": "summary"},
        "conflict": {"worktree": wt, "content": "fuzz fact"},
        "confidence": {"worktree": wt, "content": "fuzz claim"},
        "deduplicate": {"worktree": wt, "content": "fuzz fact"},
        "lifecycle": {"worktree": wt, "action": "score"},
        "search": {"worktree": wt, "query": "fuzz"},
        "knowledge": {"worktree": wt},
        "skill_list": {"worktree": wt},
        "skill_search": {"worktree": wt, "query": "fuzz"},
        "skill_create": {"worktree": wt, "name": "fuzz-skill", "description": "d",
                         "purpose": "p", "procedure": ["step"]},
        "skill_use": {"worktree": wt, "name": "fuzz-skill"},
        "skill_feedback": {"worktree": wt, "name": "fuzz-skill", "success": True},
        "skill_status": {"worktree": wt},
        "skill_evolve": {"worktree": wt, "action": "recompute"},
        "skill_search_github": {"worktree": wt, "task": "t", "capability_gap": "g"},
        "skill_discover": {"worktree": wt, "task": "t", "capability_gap": "g"},
        "skill_analyze_external": {"worktree": wt, "owner": "o", "repo": "r"},
        "skill_compare": {"worktree": wt, "owner": "o", "repo": "r"},
        "skill_import": {"worktree": wt, "owner": "o", "repo": "r", "approve": False},
        "skeleton": {"worktree": wt, "text": "def f():\n    return 1\n" * 50},
        "context_status": {"worktree": wt},
        "context_compress": {"worktree": wt,
                             "messages": [{"role": "user", "content": "x" * 5000}]},
        "context_restore": {"worktree": wt, "block_id": ""},
        "context_view": {"worktree": wt, "messages": [{"role": "user", "content": "x"}]},
        "context_coexist": {"worktree": wt, "action": "get"},
        "observe": {"worktree": wt, "observation": "fuzz obs"},
        "goal": {"worktree": wt, "action": "status"},
        "research": {"worktree": wt, "query": "fuzz"},
        "explore": {"worktree": wt, "target": ".", "depth": "file"},
        "progress": {"worktree": wt, "action": "read"},
        "session": {"worktree": wt, "action": "list"},
        "execute": {"worktree": wt, "cmd": "echo school-fuzz", "timeout_ms": 5000},
        "navigate": {"worktree": wt, "action": "list", "path": ""},
        "workflow": {"worktree": wt, "name": "tdd", "action": "status"},
        "docs": {"worktree": wt, "query": "fuzz"},
        "visualize": {"worktree": wt, "type": "sparkline",
                      "data": {"values": [1, 2, 3]}},
    }
    return dict(table.get(cmd, {"worktree": wt}))


VALUE_KEYS = ("worktree", "content", "query", "action", "text", "data", "items",
              "messages", "target", "path", "name", "goal_id", "evidence", "env",
              "tags", "limit", "depth", "width", "type", "label", "observation",
              "outcome", "confidence", "max_turns", "block_id", "session", "agent",
              "project", "cmd", "command_")

# Keys whose values feed shell execution: curated benign/garbage only.
_SHELL_KEYS = {"cmd", "command_"}


def _hostile_value(key: str, rng: random.Random) -> Any:
    if key in _SHELL_KEYS:
        return rng.choice(EXEC_CMDS)
    return _jvalue(rng)


def main_args(cmd: str, i: int) -> tuple[tuple, dict]:
    """8 rotating hostile shapes for one bridge command."""
    rng = random.Random((zlib.crc32(cmd.encode()) & 0xFFFF) * 1000003 + i)
    shape = i % 8
    req: dict[str, Any] = {"command": cmd}
    base = valid_req(cmd)
    if shape == 0:  # valid shape
        req.update(base)
    elif shape == 1:  # hostile field values
        for key in list(base):
            if rng.random() < 0.75:
                base[key] = _hostile_value(key, rng)
        req.update(base)
    elif shape == 2:  # hostile/traversal worktree
        req.update(base)
        req["worktree"] = map_wt(_jvalue(rng), i)
    elif shape == 3:  # missing required fields + hostile extras
        for key in VALUE_KEYS:
            if rng.random() < 0.25:
                req[key] = _hostile_value(key, rng)
    elif shape == 4:  # huge + NUL keys
        req.update(base)
        req["zz_huge"] = "X" * rng.randint(20_000, 200_000)
        req["nul\x00key"] = "a\x00b"
    elif shape == 5:  # deep nesting
        req.update(base)
        req["data"] = _deep(rng.randint(30, 80))
    elif shape == 6:  # wrong-typed everything
        for key in list(base):
            base[key] = rng.choice([None, 0, 3.14, True, [], {}, [1, 2],
                                    {"a": 1}, 10**30, float("nan"), ""])
        req.update(base)
    else:  # harness gen_json_safe soup
        req.update(base)
        extra = gen_json_safe(rng)
        extra.pop("command", None)
        req.update(extra)
    req["command"] = cmd
    # Containment: any worktree value (whatever shape injected it) must stay
    # inside the sandbox — disk writes follow the worktree everywhere.
    if "worktree" in req:
        req["worktree"] = map_wt(req["worktree"], i)
    return ((json.dumps(req, default=str, allow_nan=True),), {})


# ---------------------------------------------------------------------------
# A. bridge main() — every command + protocol-level hostility
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cmd", sorted(bridge._COMMANDS))
def test_a_bridge_main_command_fuzz(cmd: str) -> None:
    """2000 hostile request lines per bridge command through the real main()."""
    report = fuzz_fail_open(
        lambda raw: _check_main_out(run_bridge_main(raw)),
        n=N,
        make_args=lambda i: main_args(cmd, i),
        label=f"bridge.main.{cmd}",
    )
    assert report.ok, report.summary()


PROTOCOL_RAW: dict[str, Any] = {
    "unknown_command": lambda i: json.dumps(
        {"command": random.Random(i).choice(["zzz", "STATUS", "\x00status", "status ",
                                             "🔥", "x" * 5000, "Status", "skill_",
                                             "recall\ud800"]),
         "worktree": WT_BASE}),
    "missing_command": lambda i: json.dumps(
        {"worktree": WT_BASE, "content": "x", **({"cmd": ""} if i % 2 else {})}),
    "non_json": lambda i: random.Random(i).choice(
        ["not json {{{", "\ufeff{\"command\": \"status\"}", "{", "}", "{\"a\":",
         "{\"command\": \"status\",}", "'single quotes'", "undefined",
         "{\"command\": \"status\"}\n{\"command\": \"recall\"}", "\\x00\\xff",
         "NaN", "undefined", "x" * 1000, "<xml/>", "\t \r\n"]),
    "empty_line": lambda i: random.Random(i).choice(["", " ", "\n", "\t", "\r\n", "   \n  "]),
    "non_object": lambda i: random.Random(i).choice(
        ["null", "[]", "[1, 2, 3]", "3.14", "-0.0", "true", "false", "\"str\"",
         "\"\"", "1e999", "NaN", "[[[]]]", "{}"]),
    "unhashable_command": lambda i: random.Random(i).choice([
        '{"command": ["status"]}', '{"command": {"a": 1}}', '{"command": [[]]}',
        '{"command": {"command": {}}}', '{"command": [null, 1, "x"]}',
        '{"command": {"__proto__": {}}}', '{"command": [[[[[]]]]]}']),
    "huge_payload": lambda i: (
        '{"command": "remember", "worktree": "' + WT_BASE.replace("\\", "\\\\") +
        '", "content": "' + "X" * (200_000 + (i % 50) * 2000) + '"}'),
}


@pytest.mark.parametrize("case", sorted(PROTOCOL_RAW))
def test_a_bridge_main_protocol_fuzz(case: str) -> None:
    """Protocol-level hostility: the wire must always answer with valid JSON."""
    builder = PROTOCOL_RAW[case]
    report = fuzz_fail_open(
        lambda raw: _check_main_out(run_bridge_main(raw)),
        n=N,
        make_args=lambda i: ((builder(i),), {}),
        label=f"bridge.main.{case}",
    )
    assert report.ok, report.summary()


def test_a_bridge_oneshot_subprocess_smoke() -> None:
    """True one-shot processes: every command + hostile shapes, exit is clean."""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    cases: list[str] = []
    for cmd in sorted(bridge._COMMANDS):
        req = valid_req(cmd)
        req["command"] = cmd
        cases.append(json.dumps(req, default=str))
    cases += [PROTOCOL_RAW[k](i) for i, k in enumerate(sorted(PROTOCOL_RAW))]
    for raw in cases:
        proc = subprocess.run(
            [sys.executable, "-c", "from school.bridge import main; main()"],
            input=raw, capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=env, cwd=SANDBOX, timeout=120,
        )
        assert proc.returncode == 0, f"bridge one-shot rc={proc.returncode}: {proc.stderr[:300]}"
        _check_main_out(proc.stdout)


def test_a_bridge_subprocess_roundtrip_fuzz() -> None:
    """2000 hostile request lines, each a real one-shot bridge subprocess.

    This is the exact production shape of the JSON bridge: a fresh process per
    request, hostile JSON on stdin, JSON on stdout. The 2000 iterations cycle
    through all 40 commands and all 7 protocol-level hostile shapes.
    """
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    commands = sorted(bridge._COMMANDS)
    cases = sorted(PROTOCOL_RAW)

    def one(i: int) -> None:
        if i % 47 < len(commands):
            raw = main_args(commands[i % 47], i)[0][0]
        else:
            raw = PROTOCOL_RAW[cases[i % len(cases)]](i)
        proc = subprocess.run(
            [sys.executable, "-c", "from school.bridge import main; main()"],
            input=raw, capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=env, cwd=SANDBOX, timeout=120,
        )
        assert proc.returncode == 0, (
            f"bridge one-shot crashed (rc={proc.returncode}): {proc.stderr[:300]}"
        )
        _check_main_out(proc.stdout)

    report = fuzz_fail_open(
        one, n=N,
        make_args=lambda i: ((i,), {}),
        label="bridge.subprocess.roundtrip",
    )
    assert report.ok, report.summary()


# ---------------------------------------------------------------------------
# B. _dispatch_to_orchestrator + _safe_dump
# ---------------------------------------------------------------------------

def test_b_dispatch_to_orchestrator_fuzz() -> None:
    """Hostile (tool_name, req) must always come back as a dict."""
    tools = sorted(bridge._COMMANDS)

    def one(i: int) -> None:
        rng = random.Random(i)
        tool = rng.choice(tools + ["zzz_tool", "", None, 5, ["x"], {"a": 1},
                                   "school_remember", "x" * 1000])
        if i % 4 == 0:
            req: Any = {"worktree": map_wt(WT_BASE, i), "content": "x", "query": "y"}
        elif i % 4 == 1:
            req = {k: _jvalue(rng) for k in ("worktree", "content", "query", "text")}
            if "worktree" in req:
                req["worktree"] = map_wt(req["worktree"], i)
        elif i % 4 == 2:
            req = HOSTILE[i % len(HOSTILE)]
        else:
            req = gen_json_safe(rng)
            if isinstance(req, dict) and "worktree" in req:
                req["worktree"] = map_wt(req["worktree"], i)
        resp = bridge._dispatch_to_orchestrator(tool, req)
        assert isinstance(resp, dict), f"dispatch returned {type(resp)}"

    report = fuzz_fail_open(
        one, n=N, make_args=lambda i: ((i,), {}),
        label="bridge.dispatch.hostile",
    )
    assert report.ok, report.summary()


def test_b_safe_dump_fuzz() -> None:
    """_safe_dump must emit strict JSON for ANY hostile response object."""
    def one(i: int) -> None:
        rng = random.Random(i)
        if i % 5 == 0:
            resp: Any = {"ok": True, **{k: _jvalue(rng)
                                        for k in ("a", "b", "c")}}
        elif i % 5 == 1:
            resp = {"ok": True, "when": __import__("datetime").datetime.now(),
                    "set": {1, 2}, "nan": float("nan"), "inf": float("inf")}
        elif i % 5 == 2:
            resp = HOSTILE[i % len(HOSTILE)]
        elif i % 5 == 3:
            resp = {"ok": True, "data": _deep(rng.randint(30, 80)),
                    "huge": "X" * rng.randint(10_000, 100_000)}
        else:
            resp = {"ok": True, "bad": object(), "tuple": (1, 2),
                    "bytes": b"\x00\xff", "s": "\ud800"}
        old_out = sys.stdout
        sys.stdout = io.StringIO()
        try:
            bridge._safe_dump(resp)
            out = sys.stdout.getvalue()
        finally:
            sys.stdout = old_out
        _strict_load(out)  # any JSON value is fine — but strictly valid

    report = fuzz_fail_open(
        one, n=N, make_args=lambda i: ((i,), {}),
        label="bridge.safe_dump.hostile",
    )
    assert report.ok, report.summary()


# ---------------------------------------------------------------------------
# C. MCP server routing (requires the optional `mcp` package)
# ---------------------------------------------------------------------------

def _check_mcp_result(res: Any) -> None:
    assert hasattr(res, "content"), f"not a tool result: {type(res)}"
    texts = [c.text for c in res.content]
    assert texts, "tool result has no content"
    _strict_load(texts[0])


@requires_mcp
def test_c_route_result_fuzz() -> None:
    """Hostile result objects must always wrap into a graceful MCP result."""
    def one(i: int) -> None:
        rng = random.Random(i)
        pick = i % 9
        if pick == 0:
            data: Any = None
        elif pick == 1:
            data = b"\x00\xff\xfe"
        elif pick == 2:
            data = HOSTILE[i % len(HOSTILE)]
        elif pick == 3:
            data = {"ok": True, "nan": float("nan"), "inf": float("inf"),
                    "when": __import__("datetime").datetime.now()}
        elif pick == 4:
            data = {"ok": False, "error": {"type": "x", "message": "\ud800"}}
        elif pick == 5:
            data = [1, 2, {"a": _jvalue(rng)}]
        elif pick == 6:
            data = {"ok": True, "data": _deep(rng.randint(30, 80))}
        elif pick == 7:
            data = {"ok": True, "huge": "X" * rng.randint(10_000, 100_000)}
        else:
            data = _jvalue(rng)
        _check_mcp_result(mcp_server._route_result(data))

    report = fuzz_fail_open(
        one, n=N, make_args=lambda i: ((i,), {}),
        label="mcp.route_result.hostile",
    )
    assert report.ok, report.summary()


@requires_mcp
def test_c_bridge_call_unknown_fuzz() -> None:
    """Unknown/unhashable commands must return graceful dicts (never raise)."""
    known = sorted(bridge._COMMANDS)

    def one(i: int) -> None:
        rng = random.Random(i)
        pick = i % 6
        if pick == 0:
            cmd: Any = rng.choice(["zzz", "", "STATUS", "x" * 5000, "\x00"])
        elif pick == 1:
            cmd = rng.choice([["status"], {"a": 1}, [[[]]], {"command": "x"}])
        elif pick == 2:
            cmd = rng.choice([None, 5, 3.14, True, b"x"])
        elif pick == 3:
            cmd = HOSTILE[i % len(HOSTILE)]
        else:
            cmd = rng.choice(known)
        req: Any = {"worktree": map_wt(WT_BASE, i), "content": "x", "query": "y"}
        if i % 3 == 2:
            req = {k: _jvalue(rng) for k in ("worktree", "content", "query")}
        resp = mcp_server._bridge_call(cmd, req)
        assert isinstance(resp, dict), f"_bridge_call returned {type(resp)}"

    report = fuzz_fail_open(
        one, n=N, make_args=lambda i: ((i,), {}),
        label="mcp.bridge_call.unknown",
    )
    assert report.ok, report.summary()


@requires_mcp
def test_c_build_request_fuzz() -> None:
    """_build_request must survive hostile tools/args (ValueError is contract)."""
    tools = sorted(mcp_server._TOOLS)

    def one(i: int) -> None:
        rng = random.Random(i)
        tool = rng.choice(tools + ["school_bogus", "", "x" * 1000, None, ["x"], {}])
        if i % 3 == 0:
            args: Any = {k: _jvalue(rng) for k in ("content", "query", "agent_id",
                                                   "project", "session", "limit")}
        elif i % 3 == 1:
            args = HOSTILE[i % len(HOSTILE)]
        else:
            args = gen_json_safe(rng)
        req = mcp_server._build_request(WT_BASE, tool, args)
        assert isinstance(req, dict), f"_build_request returned {type(req)}"

    def guarded(i: int) -> None:
        with contextlib.suppress(ValueError):
            one(i)  # ValueError = sanctioned "Unknown tool" contract

    report = fuzz_fail_open(
        guarded, n=N, make_args=lambda i: ((i,), {}),
        label="mcp.build_request.hostile",
    )
    assert report.ok, report.summary()


@requires_mcp
def test_c_call_tool_unknown_fuzz() -> None:
    """Unknown/hostile tool names: ValueError contract or result — never other."""
    def one(i: int) -> None:
        rng = random.Random(i)
        name = rng.choice(["school_bogus", "", "status", "school_", "x" * 5000,
                           "\x00", ["school_status"], {"a": 1}, None, 5, b"x",
                           HOSTILE[i % len(HOSTILE)]])
        try:
            res = mcp_server._call_tool(WT_BASE, name, {"content": "x"})
        except ValueError as exc:
            assert "Unknown tool" in str(exc), f"unexpected ValueError: {exc}"
            return
        _check_mcp_result(res)

    report = fuzz_fail_open(
        one, n=N, make_args=lambda i: ((i,), {}),
        label="mcp.call_tool.unknown",
    )
    assert report.ok, report.summary()


@requires_mcp
@pytest.mark.parametrize("tool", ["school_route", "school_route_stats",
                                  "school_dashboard", "school_read", "school_grep"])
def test_c_call_tool_bespoke_fuzz(tool: str) -> None:
    """The bespoke MCP tools with hostile arguments (ValueError is contract)."""
    def one(i: int) -> None:
        rng = random.Random(i)
        wt = os.path.join(WT_BASE, f"batch{i // 100}")  # fresh store per batch
        pick = i % 5
        if pick == 0:
            args: Any = {"path": rng.choice(["", ".", "..", "nope.txt", "L0",
                                             "\x00", "x" * 1000, "..\\..\\x"]),
                         "pattern": rng.choice(["", "(", "a{2,1}", "(a+)+$", "*",
                                                "fuzz", "\\d+", "x" * 1000]),
                         "limit": rng.choice([1, -1, 0, 10**9, 3.14, None, "x"]),
                         "offset": rng.choice([1, -5, 0, 10**9, "x", None])}
        elif pick == 1:
            args = {k: _jvalue(rng) for k in ("path", "pattern", "limit", "offset",
                                              "mode", "situation", "severity",
                                              "lesson", "outcome")}
        elif pick == 2:
            args = HOSTILE[i % len(HOSTILE)]
        elif pick == 3:
            args = {"mode": rng.choice(["assess", "report", "", "zzz", None]),
                    "situation": rng.choice(["x", "", "y" * 600, "\x00"]),
                    "severity": rng.choice(["light", "medium", "high", "", None, 5]),
                    "lesson": rng.choice(["x", "", None, 5]),
                    "outcome": rng.choice(["helpful", "useless", "neutral", "zzz"])}
        else:
            args = gen_json_safe(rng)
        try:
            res = mcp_server._call_tool(wt, tool, args)
        except ValueError:
            return  # sanctioned validation contract (pinned by unit tests)
        _check_mcp_result(res)

    report = fuzz_fail_open(
        one, n=N, make_args=lambda i: ((i,), {}),
        label=f"mcp.call_tool.{tool.removeprefix('school_')}",
    )
    assert report.ok, report.summary()


@requires_mcp
def test_c_call_tool_all_tools_fuzz() -> None:
    """Routing across the whole 42-tool surface with hostile arguments."""
    tools = sorted(mcp_server._TOOLS)

    def one(i: int) -> None:
        rng = random.Random(i)
        wt = os.path.join(WT_BASE, f"batch{i // 100}")  # fresh store per batch
        tool = tools[i % len(tools)]
        if i % 4 == 0:
            args: Any = {k: _jvalue(rng) for k in ("content", "query", "action",
                                                   "name", "data", "limit")}
        elif i % 4 == 1:
            args = HOSTILE[i % len(HOSTILE)]
        elif i % 4 == 2:
            args = {}
        else:
            args = gen_json_safe(rng)
        if tool == "school_execute":
            args = {"command": rng.choice(EXEC_CMDS), "timeout_ms": 3000}
        try:
            res = mcp_server._call_tool(wt, tool, args)
        except ValueError:
            return  # sanctioned validation contract
        _check_mcp_result(res)

    report = fuzz_fail_open(
        one, n=N, make_args=lambda i: ((i,), {}),
        label="mcp.call_tool.all_tools",
    )
    assert report.ok, report.summary()


@requires_mcp
def test_c_tools_dominance_fuzz() -> None:
    """SCHOOL_PREFERRED dominance suffix on ALL tool descriptions (2000x)."""
    def one(i: int) -> None:
        assert len(mcp_server._TOOLS) == 48, f"tool count {len(mcp_server._TOOLS)}"
        for t in mcp_server._list_tools().tools:
            name = t.name
            desc = t.description
            assert isinstance(desc, str), f"{name}: description not str"
            assert "[SCHOOL — PREFERRED]" in desc, f"{name}: missing dominance suffix"
            assert desc.count("[SCHOOL — PREFERRED]") == 1, f"{name}: duplicated suffix"

    report = fuzz_fail_open(
        one, n=N, make_args=lambda i: ((i,), {}),
        label="mcp.tools.dominance",
    )
    assert report.ok, report.summary()


# ---------------------------------------------------------------------------
# D. CLI: argparse + every subcommand + _cmd_visualize
# ---------------------------------------------------------------------------

def run_cli(argv: list[Any], stdin_text: str = "") -> tuple[int, str, str]:
    """Run school.cli.main() on argv. SystemExit -> code; anything else escapes."""
    old = (sys.argv, sys.stdin, sys.stdout, sys.stderr)
    out, err = io.StringIO(), io.StringIO()
    sys.argv = ["school", *argv]
    sys.stdin = io.StringIO(stdin_text)
    sys.stdout, sys.stderr = out, err
    code = 0
    try:
        school_cli.main()
    except SystemExit as exc:
        raw = exc.code
        code = raw if isinstance(raw, int) else (0 if raw is None else 1)
    finally:
        sys.argv, sys.stdin, sys.stdout, sys.stderr = old
    return code, out.getvalue(), err.getvalue()


def _check_cli(result: tuple[int, str, str]) -> None:
    code, out, err = result
    assert isinstance(code, int), f"exit code not int: {code!r}"
    assert code in (0, 1, 2), f"unexpected exit code {code}"
    combined = out + err
    assert "Traceback (most recent call last)" not in combined, "traceback leaked to output"


CLI_LABELS = [
    "no_command", "help", "unknown_command", "version", "status", "install",
    "doctor", "uninstall", "mcp_config", "skills_list", "skills_search",
    "skills_github_search", "skills_discover", "skills_analyze", "skills_compare",
    "skills_import", "context_status", "context_compress", "context_restore",
    "context_switch", "context_keep", "visualize",
]


def cli_base(label: str) -> list[str]:
    """Base argv per subcommand (built lazily: WT_BASE exists only at runtime)."""
    wt = WT_BASE
    return {
        "no_command": [],
        "help": ["--help"],
        "unknown_command": ["zzz_subcommand"],
        "version": ["version"],
        "status": ["status"],
        "install": ["install"],
        "doctor": ["doctor"],
        "uninstall": ["uninstall"],
        "mcp_config": ["mcp", "config"],
        "skills_list": ["skills", "list"],
        "skills_search": ["skills", "search", "fuzz query"],
        "skills_github_search": ["skills", "github-search", "--task", "t", "--gap", "g"],
        "skills_discover": ["skills", "discover", "--task", "t", "--max-files", "2"],
        "skills_analyze": ["skills", "analyze", "--owner", "o", "--repo", "r"],
        "skills_compare": ["skills", "compare", "--owner", "o", "--repo", "r"],
        "skills_import": ["skills", "import", "--owner", "o", "--repo", "r", "--approve"],
        "context_status": ["context", "status", "--worktree", wt],
        "context_compress": ["context", "compress", "--worktree", wt],
        "context_restore": ["context", "restore", "--worktree", wt, "block1"],
        "context_switch": ["context", "switch", "--worktree", wt],
        "context_keep": ["context", "keep", "--worktree", wt],
        "visualize": ["visualize", "sparkline", "--data", '{"values":[1,2,3]}'],
    }[label]


@pytest.mark.parametrize("label", sorted(CLI_LABELS))
def test_d_cli_subcommand_fuzz(label: str) -> None:
    """Every CLI subcommand × hostile argv (incl. non-str entries)."""
    base = cli_base(label)

    def one(i: int) -> None:
        rng = random.Random((zlib.crc32(label.encode()) & 0xFFFF) * 7919 + i)
        argv = list(base)
        pick = i % 6
        if pick == 0:
            pass  # base argv as given
        elif pick == 1:
            argv.append(rng.choice([h for h in JHOSTILE if isinstance(h, str)]))
        elif pick == 2:  # non-str argv entries ("None-ish args via list")
            if len(argv) > 1:
                argv[rng.randrange(len(argv))] = rng.choice([None, 0, 42, 3.14, [], {}])
            else:
                argv.append(rng.choice([None, 42, [], {"a": 1}, b"bytes"]))
        elif pick == 3:
            argv += [rng.choice(["--worktree", "--data", "--label", "--width",
                                 "--force", "--json", "--zzz-flag"]),
                     str(map_wt(_jvalue(rng), i))]
        elif pick == 4:
            argv += [str(_jvalue(rng)) for _ in range(rng.randint(1, 3))]
        else:
            argv.append("🔥" * rng.randint(1, 100))
        stdin_text = rng.choice(["", "not json", "[]", '[{"role":"user","content":"x"}]',
                                 "[1,2,3]", "null"])
        result = run_cli(argv, stdin_text)
        _check_cli(result)
        if label in ("no_command", "help") and pick == 0:
            # The clean invocation must exit 0 and print help; perturbed argv
            # legitimately hits argparse's pinned exit-2 usage contract.
            assert result[0] == 0 and "usage" in result[1].lower(), "help not printed"

    report = fuzz_fail_open(
        one, n=N, make_args=lambda i: ((i,), {}),
        label=f"cli.main.{label}",
    )
    assert report.ok, report.summary()


VIZ_TYPES = [
    "sparkline", "heatmap", "donut", "radar", "gauge", "timeline", "tree", "flow",
    "spinner", "waterfall", "braille", "subcell", "status_matrix", "network",
    "dashboard", "gradient", "emoji", "comparison", "bar_chart", "histogram",
    "stats_box", "delta", "kanban", "kpi", "pie", "scatter", "funnel",
    "calendar_heatmap", "word_cloud", "mini_ring",
]


def test_d_cli_visualize_render_fuzz() -> None:
    """_cmd_visualize over many viz types with hostile data -> str, stdout intact."""
    def one(i: int) -> None:
        rng = random.Random(i)
        viz_type = rng.choice(VIZ_TYPES + ["", "zzz_type", "🔥", "\x00", "x" * 500,
                                           "SPARKLINE", "sparkline "])
        pick = i % 6
        if pick == 0:
            data: Any = '{"values":[1,2,3]}'
        elif pick == 1:
            data = rng.choice(["{bad json", "", "null", "[]", "5", '"x"', "NaN",
                               '{"values":"notalist"}', '{"values":' * 50,
                               "[1,2,]", "{'a':1}"])
        elif pick == 2:
            data = json.dumps({"values": [_jvalue(rng) for _ in range(3)],
                               **{_safe_str(k): _jvalue(rng)
                                  for k in range(3)}}, default=str)
        elif pick == 3:
            data = json.dumps(_deep(rng.randint(5, 30)), default=str)
        elif pick == 4:
            data = rng.choice([None, 5, [], {"values": [1]}, b"x", True])
        else:
            data = '{"values":[' + ",".join(str(rng.randint(-99, 999)) for _ in
                                            range(rng.randint(0, 20))) + "]}"
        args = SimpleNamespace(
            type=viz_type, label=rng.choice(["", "label", "\x00", "🔥", None, 5]),
            data=data, width=rng.choice([20, 0, -5, 200, 10**6, 3.14, None, "x"]),
        )

        # Real TextIOWrapper over a real buffer: catches any stdout-corrupting
        # wrapper (closing sys.stdout.buffer must fail the fuzz).
        buf = io.BytesIO()
        old = (sys.stdout, sys.stderr)
        sys.stdout = io.TextIOWrapper(buf, encoding="utf-8", errors="replace")
        sys.stderr = io.StringIO()
        try:
            try:
                out = school_cli._cmd_visualize(args)
            except SystemExit as exc:
                out = f"<graceful-exit:{exc.code}>"
            sys.stdout.write("")  # probe: stdout must still be writable
            sys.stdout.flush()
        finally:
            sys.stdout, sys.stderr = old
        assert isinstance(out, str), f"_cmd_visualize returned {type(out)}"

    report = fuzz_fail_open(
        one, n=N, make_args=lambda i: ((i,), {}),
        label="cli.visualize.render",
    )
    assert report.ok, report.summary()


# ---------------------------------------------------------------------------
# E. TS plugin source: invariants, hostile rendering, node --check
# ---------------------------------------------------------------------------

_TOOL_BLOCK_RE = re.compile(r"^\s+(school_[a-z_0-9]+):\s*tool\(\{", re.MULTILINE)
_CMD_KEY_RE = re.compile(r'command:\s*"([a-z_0-9]+)"')


def assert_plugin_invariants(src: str, version: Any = None) -> None:
    """Structural fail-open invariants of the bundled TypeScript plugin."""
    if version is None:
        version = plugin_source._SCHOOL_VERSION
    assert isinstance(src, str) and src, "plugin source empty"
    if "__SCHOOL_VERSION__" not in str(version):
        assert "__SCHOOL_VERSION__" not in src, "version placeholder not substituted"
    assert "export default School" in src, "plugin default export missing"
    assert "withVis" in src, "withVis wrapper missing"
    assert "invokeBridge" in src, "invokeBridge missing"
    assert "const SCHOOL_PREFERRED =" in src, "dominance constant missing"
    assert "[SCHOOL — PREFERRED]" in src, "dominance suffix literal missing"
    assert "const tool: any = ((opts: any) =>" in src, "dominance wrapper missing"
    assert "school_visualize: tool({" in src, "school_visualize tool missing"

    blocks = _TOOL_BLOCK_RE.findall(src)
    assert len(blocks) == 46, f"expected 46 tool blocks, found {len(blocks)}"
    assert len(set(blocks)) == 46, f"duplicate tool block names: {blocks}"

    # No tool block may register two `command:` keys (silent-override bug).
    starts = [m.start() for m in _TOOL_BLOCK_RE.finditer(src)]
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(src)
        cmds = _CMD_KEY_RE.findall(src[start:end])
        assert len(cmds) == len(set(cmds)), f"duplicate command keys in {blocks[idx]}: {cmds}"

    # Every command key maps to a real bridge command; together they cover all.
    all_cmds = set(_CMD_KEY_RE.findall(src))
    assert all_cmds <= set(bridge._COMMANDS), f"unknown commands in plugin: {all_cmds}"
    assert all_cmds == set(bridge._COMMANDS), (
        f"plugin/bridge command parity broken: {set(bridge._COMMANDS) ^ all_cmds}"
    )

    version_line = re.search(r'const SCHOOL_VERSION = ("(?:[^"\\]|\\.)*")', src)
    assert version_line, "SCHOOL_VERSION literal missing or unparseable"
    assert json.loads(version_line.group(1)) == str(version)


def test_e_plugin_invariants_direct() -> None:
    """One direct (non-fuzz) assertion of the shipped source."""
    assert_plugin_invariants(plugin_source.TS_PLUGIN_SOURCE)


def test_e_plugin_invariants_fuzz() -> None:
    """Re-verify structural invariants 2000 times (fail-open scanners)."""
    report = fuzz_fail_open(
        lambda i: assert_plugin_invariants(plugin_source.TS_PLUGIN_SOURCE),
        n=N, make_args=lambda i: ((i,), {}),
        label="plugin.invariants",
    )
    assert report.ok, report.summary()


HOSTILE_VERSIONS = [
    "", " ", "\x00", '"; process.exit(1); const x = "', "2.6.0\nline2",
    "`${process.exit(1)}`", "\\u0000", "\\", "'", '"', "/*", "*/", "🔥" * 50,
    "X" * 5000, "__SCHOOL_VERSION__", "${x}", "</script>", "\r\n\t",
    "2.6.0'; alert('x'); //", "-1", "null", "undefined",
]


def test_e_plugin_render_hostile_fuzz() -> None:
    """render_plugin must safely embed ANY version string into the TS literal."""
    def one(i: int) -> None:
        rng = random.Random(i)
        version = rng.choice(HOSTILE_VERSIONS + [_jvalue(rng)])
        src = plugin_source.render_plugin(version)
        assert isinstance(src, str), f"render_plugin returned {type(src)}"
        # The version literal must round-trip exactly (JSON-escaped TS string).
        match = re.search(r'const SCHOOL_VERSION = ("(?:[^"\\]|\\.)*")', src)
        assert match, "SCHOOL_VERSION literal broken by version injection"
        assert json.loads(match.group(1)) == str(version)
        # Full structural invariants must still hold for any version.
        assert_plugin_invariants(src, version=version)

    report = fuzz_fail_open(
        one, n=N, make_args=lambda i: ((i,), {}),
        label="plugin.render_hostile",
    )
    assert report.ok, report.summary()


@requires_node
def test_e_plugin_node_check_pristine() -> None:
    """The shipped plugin source must pass a real `node --check`."""
    path = os.path.join(SANDBOX, "pristine.ts")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(plugin_source.TS_PLUGIN_SOURCE)
    proc = subprocess.run([NODE, "--check", path], capture_output=True,
                          text=True, errors="replace", timeout=60)
    assert proc.returncode == 0, f"node --check failed: {proc.stderr[:800]}"


@requires_node
def test_e_plugin_node_check_fuzz() -> None:
    """2000 mutated sources through real `node --check` (definite verdicts)."""
    path = os.path.join(SANDBOX, "mutant.ts")
    src = plugin_source.TS_PLUGIN_SOURCE

    def one(i: int) -> None:
        rng = random.Random(i)
        pick = i % 4
        if pick == 0:
            mutant = src[:rng.randrange(len(src))]
        elif pick == 1:
            pos = rng.randrange(len(src))
            mutant = src[:pos] + rng.choice([str(h) for h in JHOSTILE]) + src[pos:]
        elif pick == 2:
            mutant = src + rng.choice(["\nconst zzz = ", "\n}}}", "\n'unclosed",
                                       "\n" + "X" * 5000])
        else:
            mutant = src
        with open(path, "w", encoding="utf-8", errors="surrogatepass") as fh:
            fh.write(mutant)
        proc = subprocess.run([NODE, "--check", path], capture_output=True,
                              text=True, errors="replace", timeout=60)
        assert proc.returncode in (0, 1), (
            f"node died on mutant (rc={proc.returncode}): {proc.stderr[:300]}"
        )

    report = fuzz_fail_open(
        one, n=N, make_args=lambda i: ((i,), {}),
        label="plugin.node_check",
    )
    assert report.ok, report.summary()


# ---------------------------------------------------------------------------
# Live smoke: the real network paths (once each, graceful-only assertions)
# ---------------------------------------------------------------------------

def test_live_network_smoke() -> None:
    """Bounded live check of network-backed commands (graceful, never fatal)."""
    import socket

    saved = {k: os.environ.pop(k, None)
             for k in ("SCHOOL_SKILLGEN_GITHUB_DISABLED", "SCHOOL_DOCS")}
    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(10)  # hard cap: no network call may hang this suite
    try:
        for cmd in ("skill_search_github", "skill_discover", "skill_analyze_external",
                    "skill_compare", "skill_import", "docs"):
            req = valid_req(cmd)
            req["command"] = cmd
            out = run_bridge_main(json.dumps(req, default=str))
            _check_main_out(out)  # must be valid JSON whatever the network does
    finally:
        socket.setdefaulttimeout(old_timeout)
        for key, value in saved.items():
            if value is not None:
                os.environ[key] = value


# ---------------------------------------------------------------------------
# Coverage ledger
# ---------------------------------------------------------------------------

def test_zz_fuzz_ledger_coverage() -> None:
    """Prove 2000 iterations per surface label and zero recorded failures."""
    expected = {f"bridge.main.{cmd}" for cmd in bridge._COMMANDS}
    expected |= {f"bridge.main.{case}" for case in PROTOCOL_RAW}
    expected |= {"bridge.subprocess.roundtrip", "bridge.dispatch.hostile",
                 "bridge.safe_dump.hostile", "cli.visualize.render",
                 "plugin.invariants", "plugin.render_hostile"}
    expected |= {f"cli.main.{label}" for label in CLI_LABELS}
    if mcp_server is not None:
        expected |= {"mcp.route_result.hostile", "mcp.bridge_call.unknown",
                     "mcp.build_request.hostile", "mcp.call_tool.unknown",
                     "mcp.call_tool.all_tools", "mcp.tools.dominance"}
        expected |= {f"mcp.call_tool.{t.removeprefix('school_')}"
                     for t in ("school_route", "school_route_stats",
                               "school_dashboard", "school_read", "school_grep")}
    if NODE is not None:
        expected |= {"plugin.node_check"}

    print(ledger_summary())
    missing = expected - set(FUZZ_LEDGER)
    assert not missing, f"labels never executed: {sorted(missing)}"
    short = {label: FUZZ_LEDGER[label] for label in expected if FUZZ_LEDGER[label] < N}
    assert not short, f"labels below {N} iterations: {short}"
    # Scope to this suite's labels only: the ledger is shared across suites
    # and sibling quarantine findings must not fail this coverage gate.
    failures = {label: len(FUZZ_FAILURES[label]) for label in expected
                if FUZZ_FAILURES.get(label)}
    assert not failures, f"recorded fuzz failures: {failures}"
    print(f"[fuzz-total] {sum(FUZZ_LEDGER.values())} iterations "
          f"across {len(FUZZ_LEDGER)} labels")
