"""S2 Task 9: end-to-end context surfaces (bridge subprocess + live node)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from school.plugin_source import TS_PLUGIN_SOURCE

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

STUB_PKG = json.dumps(
    {
        "name": "@opencode-ai/plugin",
        "version": "0.0.0",
        "type": "module",
        "exports": {".": "./index.js", "./tool": "./tool.js"},
    }
)
STUB_INDEX_JS = "export {};\n"
STUB_TOOL_JS = """\
const chain = new Proxy(() => chain, {
  get: (_t, p) => (p === "then" ? undefined : chain),
  apply: () => chain,
});
export const tool = (t) => t;
tool.schema = chain;
"""

TRANSFORM_HARNESS = """\
import School from "./school.ts";
const [worktree] = process.argv.slice(2);
const hooks = await School({ worktree, directory: worktree });
const mk = (i) => ({
  info: {
    id: `m${i}`,
    sessionID: "live1",
    role: i % 2 === 0 ? "user" : "assistant",
  },
  parts: [
    { type: "text", text: (`msg${i} alpha bravo charlie delta `).repeat(20) },
  ],
});
const output = { messages: [0, 1, 2, 3, 4, 5, 6, 7].map(mk) };
const before = JSON.stringify(output.messages);
await hooks["experimental.chat.messages.transform"]({}, output);
process.stdout.write(
  JSON.stringify({ before, after: JSON.stringify(output.messages) })
);
"""


_CLEAN_HOME = Path(tempfile.mkdtemp(prefix="school_it_home_"))


def _clean_home_env(env: dict) -> dict:
    """Point HOME/USERPROFILE at one shared temp dir so DCP detection never sees the real host."""
    env["HOME"] = str(_CLEAN_HOME)
    env["USERPROFILE"] = str(_CLEAN_HOME)
    return env


def _live_env() -> dict:
    env = dict(os.environ)
    env["SCHOOL_HOME"] = str(REPO_ROOT)
    env["PYTHONPATH"] = str(REPO_ROOT)
    scripts = str(REPO_ROOT / ".venv" / "Scripts")
    env["PATH"] = scripts + os.pathsep + env.get("PATH", "")
    env["SCHOOL_COMPRESS_WINDOW_TOKENS"] = "200"
    env["SCHOOL_COMPRESS_TAIL_TOKENS"] = "0"
    for key in ("SCHOOL_HOOKS", "SCHOOL_CTX", "SCHOOL_COMPRESS"):
        env.pop(key, None)
    return _clean_home_env(env)


def run_bridge(req: dict, env: dict | None = None) -> dict:
    """One JSON request through a real ``python -m school.bridge`` process."""
    proc_env = dict(os.environ)
    proc_env["PYTHONPATH"] = str(REPO_ROOT)
    _clean_home_env(proc_env)
    if env:
        proc_env.update(env)
    proc = subprocess.run(
        [sys.executable, "-m", "school.bridge"],
        input=json.dumps(req),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        env=proc_env,
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads(proc.stdout)


def big_msgs(n: int = 8) -> list[dict]:
    return [
        {"role": "user" if i % 2 == 0 else "assistant", "content": chr(97 + i) * 300}
        for i in range(n)
    ]


def live_msgs() -> list[dict]:
    return [
        {
            "role": "user" if i % 2 == 0 else "assistant",
            "content": f"msg{i} alpha bravo charlie delta " * 20,
        }
        for i in range(8)
    ]


@pytest.fixture
def plugin_dir() -> Path:
    d = Path(tempfile.mkdtemp(prefix="school_plugin_"))
    (d / "node_modules" / "@opencode-ai" / "plugin").mkdir(parents=True)
    (d / "school.ts").write_text(TS_PLUGIN_SOURCE, encoding="utf-8")
    (d / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    stub = d / "node_modules" / "@opencode-ai" / "plugin"
    (stub / "package.json").write_text(STUB_PKG, encoding="utf-8")
    (stub / "index.js").write_text(STUB_INDEX_JS, encoding="utf-8")
    (stub / "tool.js").write_text(STUB_TOOL_JS, encoding="utf-8")
    (d / "transform.mjs").write_text(TRANSFORM_HARNESS, encoding="utf-8")
    return d


def _run_transform(plugin_dir: Path, worktree: Path, env: dict) -> dict:
    proc = subprocess.run(
        ["node", str(plugin_dir / "transform.mjs"), str(worktree)],
        cwd=str(plugin_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads(proc.stdout)


@pytest.mark.integration
class TestBridgeSubprocess:
    """All five context commands over the real bridge CLI (stdin/stdout JSON)."""

    def test_status_roundtrip(self, tmp_path: Path) -> None:
        resp = run_bridge(
            {
                "command": "context_status",
                "worktree": str(tmp_path),
                "session": "s1",
            }
        )
        assert resp["ok"] is True
        assert resp["mode"] == "school"
        assert resp["blocks"] == 0
        assert "chip" in resp

    def test_coexist_decision_roundtrip(self, tmp_path: Path) -> None:
        req = {"command": "context_coexist", "worktree": str(tmp_path)}
        got = run_bridge({**req, "action": "get"})
        assert got["ok"] is True
        assert got["decision"] == ""
        assert got["dcp"] is False
        switched = run_bridge(
            {**req, "action": "set_decision", "decision": "switch"}
        )
        assert switched["decision"] == "switch"
        again = run_bridge({**req, "action": "get"})
        assert again["decision"] == "switch"
        assert again["mode"] == "school"
        bad = run_bridge({**req, "action": "set_decision", "decision": "nope"})
        assert bad["ok"] is False
        assert bad["error"]["type"] == "validation"

    def test_view_fails_open_on_junk(self, tmp_path: Path) -> None:
        resp = run_bridge(
            {
                "command": "context_view",
                "worktree": str(tmp_path),
                "session": "s1",
                "messages": "junk",
            }
        )
        assert resp["ok"] is True
        assert resp["segments"] == []

    def test_unknown_command_is_protocol_error(self) -> None:
        resp = run_bridge({"command": "context_bogus"})
        assert resp["ok"] is False
        assert resp["error"]["type"] == "protocol"

    def test_compress_status_restore(self, tmp_path: Path) -> None:
        env = _live_env()
        wt = str(tmp_path)
        compressed = run_bridge(
            {
                "command": "context_compress",
                "worktree": wt,
                "session": "sub1",
                "messages": big_msgs(),
            },
            env=env,
        )
        assert compressed["ok"] is True
        assert compressed["blocks_added"] >= 1
        assert compressed["chip"].startswith("[school] compacted")
        status = run_bridge(
            {"command": "context_status", "worktree": wt, "session": "sub1"},
            env=env,
        )
        assert status["blocks"] >= 1
        restored = run_bridge(
            {"command": "context_restore", "worktree": wt, "session": "sub1"},
            env=env,
        )
        assert restored["ok"] is True
        assert restored["restores"] >= 1


@pytest.mark.integration
class TestLiveApplyView:
    """The real TS through node: apply-view, kill switches, DCP gate, offer."""

    def test_identity_without_blocks(
        self, plugin_dir: Path, tmp_path: Path
    ) -> None:
        worktree = tmp_path / "wt"
        worktree.mkdir()
        out = _run_transform(plugin_dir, worktree, _live_env())
        assert out["after"] == out["before"], "no blocks -> messages untouched"

    def test_kill_switch_identity(
        self, plugin_dir: Path, tmp_path: Path
    ) -> None:
        worktree = tmp_path / "wt"
        worktree.mkdir()
        env = _live_env()
        env["SCHOOL_COMPRESS"] = "0"
        out = _run_transform(plugin_dir, worktree, env)
        assert out["after"] == out["before"], "SCHOOL_COMPRESS=0 -> no rewrite"

    def test_compressed_blocks_are_applied(
        self, plugin_dir: Path
    ) -> None:
        worktree = Path(tempfile.mkdtemp(prefix="school_wt_"))
        env = _live_env()
        compressed = run_bridge(
            {
                "command": "context_compress",
                "worktree": str(worktree),
                "session": "live1",
                "messages": live_msgs(),
            },
            env=env,
        )
        assert compressed["blocks_added"] >= 1
        out = _run_transform(plugin_dir, worktree, env)
        assert out["after"] != out["before"], "view must replace block ranges"
        assert len(out["after"]) < len(out["before"])
        assert "school-view-" in out["after"]

    def test_dcp_present_blocks_view_and_offers_once(
        self, plugin_dir: Path
    ) -> None:
        worktree = Path(tempfile.mkdtemp(prefix="school_wt_"))
        (worktree / "opencode.json").write_text(
            json.dumps({"plugin": ["@tarquinen/opencode-dcp"]}),
            encoding="utf-8",
        )
        env = _live_env()
        out = _run_transform(plugin_dir, worktree, env)
        assert out["after"] == out["before"], "DCP owns the view until decided"
        state_path = worktree / ".school" / "context" / "coexistence.json"
        assert state_path.exists(), "coexist set_offer must persist state"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["offer_shown"] is True
        assert state["decision"] == ""
