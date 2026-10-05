"""Live Node harness: run the real plugin TS through tool.execute.after."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from school.plugin_source import TS_PLUGIN_SOURCE

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FOOTER_ONE = re.compile(r"\[school ctx: \d+→\d+ tokens\]")

HARNESS = """\
import School from "./school.ts";
import { readFileSync } from "node:fs";
const [worktree, bigPath] = process.argv.slice(2);
const hooks = await School({ worktree, directory: worktree });
const text = readFileSync(bigPath, "utf8");
const output = { title: "read", output: text, args: { filePath: "big.py" } };
await hooks["tool.execute.after"](
  { callID: "c1", tool: "read", sessionID: "t" },
  output
);
process.stdout.write(
  JSON.stringify({ output: output.output, title: output.title })
);
"""

STUB_TOOL_JS = """\
const chain = new Proxy(() => chain, {
  get: (_t, p) => (p === "then" ? undefined : chain),
  apply: () => chain,
});
export const tool = (t) => t;
tool.schema = chain;
"""
STUB_INDEX_JS = "export {};\n"

FOOTER_HARNESS = """\
import School from "./school.ts";
const [worktree] = process.argv.slice(2);
const hooks = await School({ worktree, directory: worktree });
const output = { text: "Assistant reply." };
const hook = hooks["experimental.text.complete"];
await hook({ sessionID: "s", messageID: "m", partID: "p" }, output);
const first = output.text;
await hook({ sessionID: "s", messageID: "m", partID: "p" }, output);
const dash = await hooks.tool.school_dashboard.execute(
  {},
  { worktree, sessionID: "s" },
);
process.stdout.write(
  JSON.stringify({ first, second: output.text, dash: dash.output, title: dash.title }),
);
"""
STUB_PKG = json.dumps(
    {
        "name": "@opencode-ai/plugin",
        "version": "0.0.0",
        "type": "module",
        "exports": {".": "./index.js", "./tool": "./tool.js"},
    }
)


def _big_py() -> str:
    lines = ["def compute(a: int) -> int:"]
    for i in range(600):
        lines.append(f"    x = x + {i}")
    return "\n".join(lines)


@pytest.fixture
def plugin_dir(tmp_path: Path) -> Path:
    d = tmp_path / "plugin"
    (d / "node_modules" / "@opencode-ai" / "plugin").mkdir(parents=True)
    (d / "school.ts").write_text(TS_PLUGIN_SOURCE, encoding="utf-8")
    (d / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    stub = d / "node_modules" / "@opencode-ai" / "plugin"
    (stub / "package.json").write_text(STUB_PKG, encoding="utf-8")
    (stub / "index.js").write_text(STUB_INDEX_JS, encoding="utf-8")
    (stub / "tool.js").write_text(STUB_TOOL_JS, encoding="utf-8")
    (d / "harness.mjs").write_text(HARNESS, encoding="utf-8")
    (d / "footer.mjs").write_text(FOOTER_HARNESS, encoding="utf-8")
    return d


def _run(plugin_dir: Path, worktree: Path, big: Path, env: dict) -> dict:
    proc = subprocess.run(
        ["node", str(plugin_dir / "harness.mjs"), str(worktree), str(big)],
        cwd=str(plugin_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads(proc.stdout)


@pytest.mark.integration
class TestLiveContextOptimizer:
    def test_ts_fallback_compresses(self, plugin_dir: Path, tmp_path: Path):
        worktree = tmp_path / "wt"
        worktree.mkdir()
        big = tmp_path / "big.py"
        big.write_text(_big_py(), encoding="utf-8", newline="\n")
        env = dict(os.environ)
        env["SCHOOL_HOME"] = str(tmp_path / "nowhere")
        env["PATH"] = str(tmp_path / "nopath")
        env.pop("PYTHONPATH", None)
        out = _run(plugin_dir, worktree, big, env)
        assert out["output"] != out["output"][:0]  # sanity: ran
        original = big.read_text(encoding="utf-8")
        assert out["output"] != original
        assert len(out["output"]) < len(original)
        assert len(FOOTER_ONE.findall(out["output"])) == 1
        assert "def compute(a: int) -> int:" in out["output"]
        assert "school" in out["title"]

    def test_bridge_path_preferred(self, plugin_dir: Path, tmp_path: Path):
        worktree = tmp_path / "wt"
        worktree.mkdir()
        big = tmp_path / "big.py"
        big.write_text(_big_py(), encoding="utf-8", newline="\n")
        env = dict(os.environ)
        env["SCHOOL_HOME"] = str(REPO_ROOT)
        env["PYTHONPATH"] = str(REPO_ROOT)
        scripts = str(REPO_ROOT / ".venv" / "Scripts")
        env["PATH"] = scripts + os.pathsep + env.get("PATH", "")
        out = _run(plugin_dir, worktree, big, env)
        original = big.read_text(encoding="utf-8")
        assert len(out["output"]) < len(original)
        assert len(FOOTER_ONE.findall(out["output"])) == 1
        assert "def compute(a: int) -> int:" in out["output"]

    def test_kill_switch_raw(self, plugin_dir: Path, tmp_path: Path):
        worktree = tmp_path / "wt"
        worktree.mkdir()
        big = tmp_path / "big.py"
        big.write_text(_big_py(), encoding="utf-8", newline="\n")
        env = dict(os.environ)
        env["SCHOOL_CTX"] = "0"
        out = _run(plugin_dir, worktree, big, env)
        original = big.read_text(encoding="utf-8")
        assert out["output"] == original
        assert "school ctx" not in out["output"]


def _run_footer(plugin_dir: Path, worktree: Path, env: dict) -> dict:
    proc = subprocess.run(
        ["node", str(plugin_dir / "footer.mjs"), str(worktree)],
        cwd=str(plugin_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads(proc.stdout)


@pytest.mark.integration
class TestLiveStatusFooter:
    """The [school] footer and dashboard tool render on every response."""

    def _env(self, tmp_path: Path) -> dict:
        env = dict(os.environ)
        env["SCHOOL_HOME"] = str(tmp_path / "nowhere")
        env["PATH"] = str(tmp_path / "nopath")
        env.pop("PYTHONPATH", None)
        env.pop("SCHOOL_HOOKS", None)
        return env

    def test_footer_appends_and_is_idempotent(
        self, plugin_dir: Path, tmp_path: Path
    ):
        worktree = tmp_path / "wt"
        worktree.mkdir()
        out = _run_footer(plugin_dir, worktree, self._env(tmp_path))
        assert out["first"].startswith("Assistant reply.")
        assert "\n\n[school] route:" in out["first"]
        for chip in ("next: ", "ctx: ", "recall: ", "learn: ", "diag: "):
            assert chip in out["first"], chip
        assert out["second"] == out["first"]  # no double append

    def test_dashboard_tool_returns_status_lines(
        self, plugin_dir: Path, tmp_path: Path
    ):
        worktree = tmp_path / "wt"
        worktree.mkdir()
        out = _run_footer(plugin_dir, worktree, self._env(tmp_path))
        assert out["title"] == "School Dashboard"
        assert "route: " in out["dash"]
        assert "learn: off" in out["dash"]  # no bridge in sandbox
        assert "diag: off" in out["dash"]

    def test_footer_kill_switch(self, plugin_dir: Path, tmp_path: Path):
        worktree = tmp_path / "wt"
        worktree.mkdir()
        env = self._env(tmp_path)
        env["SCHOOL_HOOKS"] = "0"
        out = _run_footer(plugin_dir, worktree, env)
        assert out["first"] == "Assistant reply."  # untouched
