"""Adversarial fail-proof tests for the School MCP + Plugin distributions.

DESIGNED TO FAIL the packages: every function is hammered with hostile, wrong-
typed, and malformed input. The only pass condition is that nothing ever
raises and every call returns a sane dict/str. If the packages survive this,
they are fool-proof.

Iteration counts are bounded so the suite is thorough yet runs to completion;
the hostility (not the raw count) is what makes these "designed to fail".
"""

from __future__ import annotations

import pathlib
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
for p in (str(ROOT / "packages" / "mcp"), str(ROOT / "packages" / "plugin"), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from school_mcp import compat as mcp_compat  # noqa: E402
from school_mcp.server import available as sdk_available  # noqa: E402
from school_mcp.tools import (  # noqa: E402
    TOOL_NAMES,
    TOOLS,
    call_tool,
    describe,
)
from school_plugin import adapters as pg_adapters  # noqa: E402
from school_plugin import compat as pg_compat  # noqa: E402


class _Evil:
    def __str__(self):
        raise RuntimeError("evil str")

    def __bool__(self):
        raise RuntimeError("evil bool")

    def __hash__(self):
        raise RuntimeError("evil hash")

    def __eq__(self, other):
        raise RuntimeError("evil eq")

    def __len__(self):
        raise RuntimeError("evil len")

    def __iter__(self):
        raise RuntimeError("evil iter")

    def __call__(self, *a, **k):
        raise RuntimeError("evil call")

    def __getattr__(self, name):
        raise RuntimeError("evil getattr")


class _BadDict(dict):
    def items(self):
        raise RuntimeError("evil items")

    def get(self, k, d=None):
        raise RuntimeError("evil get")


# Core hostile corpus (full adversity).
HOSTILE = [
    None, "", "   ", 0, -1, 10**50, 3.14, float("nan"), float("inf"),
    [], {}, ["a"], {"b": 1}, b"bytes", True, False, object(),
    "\x00null", "bash\x00", "x" * 50000, "\ud800", "🏫🎓",
    _Evil(), _BadDict(), lambda: None,
]

# Leaner subset for the big per-tool sweeps (keeps runtime bounded).
BULK = [None, "", 0, -1, float("nan"), [], {}, b"bytes", _Evil(), "\x00n"]


def _wt():
    return tempfile.mkdtemp(prefix="school-dist-")


class TestMcpToolsFailProof:
    def test_registry_has_48(self):
        assert len(TOOL_NAMES) == 48
        assert len(TOOLS) == 48

    def test_every_tool_never_raises_bulk(self):
        wt = _wt()
        try:
            for tool in TOOL_NAMES:
                for _ in range(5):
                    for h in BULK:
                        res = call_tool(tool, {"arg": h, "content": h, "query": h}, h)
                        assert isinstance(res, dict), f"{tool} -> {type(res)}"
        finally:
            shutil.rmtree(wt, ignore_errors=True)

    def test_full_hostile_corpus_once_per_tool(self):
        for tool in TOOL_NAMES:
            for h in HOSTILE:
                res = call_tool(tool, {"q": h, "path": h, "cmd": h}, None)
                assert isinstance(res, dict)

    def test_unknown_tool_graceful(self):
        for name in HOSTILE:
            res = call_tool(name, {}, None)
            assert isinstance(res, dict)
            if isinstance(name, str) and name not in TOOLS:
                assert res.get("ok") is False

    def test_args_wrong_type_graceful(self):
        for tool in TOOL_NAMES:
            for bad_args in (None, [], "str", 123, _Evil(), _BadDict()):
                assert isinstance(call_tool(tool, bad_args, None), dict)

    def test_describe_never_raises(self):
        for tool in TOOL_NAMES:
            d = describe(tool)
            assert isinstance(d, dict) and ("name" in d or "error" in d)
        for bad in HOSTILE:
            assert isinstance(describe(bad), dict)

    def test_all_tools_have_schema_and_description(self):
        for tool in TOOL_NAMES:
            assert TOOLS[tool]["description"]
            assert TOOLS[tool]["schema"].get("type") == "object"


class TestMcpCompatFailProof:
    def test_all_clients_generate(self):
        for client in ("claude_desktop", "chatgpt", "cursor", "vscode", "zed", "generic"):
            cfg = mcp_compat.generate(client)
            assert isinstance(cfg, dict) and cfg

    def test_unknown_and_hostile_client(self):
        for bad in HOSTILE:
            assert isinstance(mcp_compat.generate(bad), dict)

    def test_hostile_url(self):
        for bad in HOSTILE:
            for client in ("chatgpt", "cursor", "generic"):
                assert isinstance(mcp_compat.generate(client, bad), dict)

    def test_all_configs_fail_open(self):
        cfgs = mcp_compat.all_configs(_Evil())
        assert isinstance(cfgs, dict)
        assert len(cfgs) == len(mcp_compat.CLIENTS)


class TestPluginAdaptersFailProof:
    def test_every_adapter_emits(self):
        for cli in pg_adapters.ADAPTERS:
            payload = pg_adapters.emit_plugin(cli)
            assert isinstance(payload, str) and payload

    def test_unknown_and_hostile_cli(self):
        for bad in HOSTILE:
            assert isinstance(pg_adapters.emit_plugin(bad), str)
            assert isinstance(pg_adapters.adapter_for(bad), dict)

    def test_config_for_every_cli(self):
        for cli in pg_compat.CLI_CLIENTS:
            cfg = pg_compat.config_for(cli)
            assert isinstance(cfg, dict) and cfg.get("payload")

    def test_config_for_hostile_cli(self):
        for bad in HOSTILE:
            assert isinstance(pg_compat.config_for(bad), dict)

    def test_install_plan_fail_open(self):
        plan = pg_compat.install_plan()
        assert isinstance(plan, dict) and "supported" in plan
        for bad in HOSTILE:
            assert isinstance(pg_compat.verify(bad), dict)


class TestCrossCuttingFailProof:
    def test_sdk_availability_is_bool(self):
        assert isinstance(sdk_available(), bool)

    def test_full_sweep_no_raise(self):
        for tool in TOOL_NAMES[:12]:
            for bad in BULK:
                call_tool(tool, {"q": bad}, bad)
                mcp_compat.generate("chatgpt", bad)
                pg_adapters.emit_plugin("opencode")
        assert True

    def test_tool_count_matches_documented(self):
        assert len(TOOL_NAMES) == 48


class _Throws:
    """Every dunder raises — worse than _Evil because it also breaks iteration."""

    def __iter__(self):
        raise TypeError("throws iter")

    def __next__(self):
        raise TypeError("throws next")

    def __getitem__(self, k):
        raise TypeError("throws getitem")

    def __getattr__(self, name):
        raise AttributeError(f"throws getattr {name}")

    def __call__(self, *a, **k):
        raise TypeError("throws call")


def _cyclic(depth=4):
    """Self-referencing structure that would blow naive recursion."""
    node = {}
    cur = node
    for _ in range(depth):
        nxt = {}
        cur["self"] = nxt
        cur["back"] = node
        cur = nxt
    node["root"] = node
    return node


def _deep_list(n=200):
    """Deeply nested list to trip type-confusion / recursion."""
    out: list = []
    cur = out
    for _ in range(n):
        nxt: list = []
        cur.append(nxt)
        cur = nxt
    return out


BRUTAL = [
    _Throws(),
    _cyclic(),
    _deep_list(),
    {"self": "recursive", "a": {"b": {"c": {"d": "deep"}}}},
    [None, [None, [None, [None, "bottom"]]]],
    float("nan"),
    float("inf"),
    -(10**308),
    b"\xff\xfe\x00binary",
    "x" * 20000,
    "\ud800lone-surrogate",
    {"k" * 200: "v" * 200},
]


class TestConcurrencyFailProof:
    """Concurrent calls must never interleave into a raise or corrupt state."""

    def test_threads_hammer_call_tool(self):
        import threading

        errors: list = []

        def worker(idx: int) -> None:
            try:
                for i in range(20):
                    tool = TOOL_NAMES[(idx + i) % len(TOOL_NAMES)]
                    r = call_tool(tool, {"worktree": ".", "q": f"t{idx}-{i}"}, ".")
                    assert isinstance(r, dict)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors, errors

    def test_threads_hammer_mixed_surfaces(self):
        import threading

        errors: list = []

        def worker(idx: int) -> None:
            try:
                for i in range(15):
                    call_tool(TOOL_NAMES[i % 48], {"worktree": "."}, ".")
                    mcp_compat.generate("cursor", f"http://h{i}.local/mcp")
                    pg_adapters.emit_plugin("codex")
                    describe(TOOL_NAMES[i % 48])
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors, errors


class TestTypeConfusionFailProof:
    """Chained and cyclic structures must never propagate a raise."""

    def test_every_tool_with_brutal_args(self):
        for tool in TOOL_NAMES:
            for bad in BRUTAL:
                r = call_tool(tool, {"worktree": bad, "q": bad, "content": bad}, bad)
                assert isinstance(r, dict)

    def test_brutal_as_tool_name(self):
        for bad in BRUTAL:
            r = call_tool(bad, {"worktree": "."}, ".")
            assert isinstance(r, dict)
            d = describe(bad)
            assert isinstance(d, dict)

    def test_cyclic_and_deep_structures(self):
        for structure in (_cyclic(), _deep_list(), _cyclic(20)):
            for tool in TOOL_NAMES[:10]:
                r = call_tool(
                    tool, {"worktree": ".", "data": structure, "items": structure}, "."
                )
                assert isinstance(r, dict)

    def test_compat_with_cyclic(self):
        for bad in (_cyclic(), _deep_list(), _Throws()):
            assert isinstance(mcp_compat.generate(bad, bad), dict)
            assert isinstance(mcp_compat.all_configs(bad), dict)
            assert isinstance(pg_adapters.emit_plugin(bad), str)
            assert isinstance(pg_compat.config_for(bad), dict)


# Every CLI + web interface the plugin/MCP must reach (Phase D compatibility).
UNIVERSAL_CLIENTS = [
    "opencode", "claude_code", "claude_desktop", "claude_ai", "chatgpt",
    "codex", "cursor", "windsurf", "cline", "vscode", "zed", "continue",
    "aider", "generic",
]


class TestUniversalClientCoverage:
    """Phase D: the plugin + MCP are compatible with every CLI and web UI."""

    def test_mcp_covers_every_client(self):
        for client in UNIVERSAL_CLIENTS:
            rec = mcp_compat.generate(client)
            assert isinstance(rec, dict) and rec
            assert rec.get("config") is not None
            assert rec.get("format") in {"json", "toml", "yaml"}
            assert rec.get("transport") in {"stdio", "http"}

    def test_plugin_covers_every_client(self):
        for client in UNIVERSAL_CLIENTS:
            payload = pg_adapters.emit_plugin(client)
            assert isinstance(payload, str) and payload.strip()

    def test_cli_client_lists_are_universal(self):
        for client in UNIVERSAL_CLIENTS:
            assert client in pg_compat.CLI_CLIENTS

    def test_web_interfaces_are_remote(self):
        for web_ui in ("chatgpt", "claude_ai"):
            rec = mcp_compat.generate(web_ui)
            assert rec["kind"] == "remote"
            assert rec["transport"] == "http"

    def test_local_clis_are_stdio(self):
        for cli in ("claude_desktop", "codex", "cursor", "windsurf", "cline", "aider"):
            rec = mcp_compat.generate(cli)
            assert rec["transport"] == "stdio"

    def test_describe_clients_index(self):
        rows = mcp_compat.describe_clients()
        assert isinstance(rows, list) and len(rows) == len(mcp_compat.CLIENTS)
        ids = {r["client"] for r in rows}
        for client in UNIVERSAL_CLIENTS:
            assert client in ids

    def test_as_json_serializable(self):
        for client in UNIVERSAL_CLIENTS:
            text = mcp_compat.as_json(client)
            assert isinstance(text, str) and text

    def test_known_config_key_shapes(self):
        # VS Code uses `servers`; Zed uses `context_servers`; rest use `mcpServers`.
        assert "servers" in mcp_compat.generate("vscode")["config"]
        assert "context_servers" in mcp_compat.generate("zed")["config"]
        assert "mcpServers" in mcp_compat.generate("cursor")["config"]
        assert "connector" in mcp_compat.generate("chatgpt")["config"]
