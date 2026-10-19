"""Live end-to-end MCP tests — the real server over real transports.

These spawn ``python -m school_mcp.server`` as a subprocess and speak the actual
MCP JSON-RPC protocol over stdio and streamable-HTTP. They prove the packages
are fail-proof at the TRANSPORT layer, not just the registry layer.

If the ``mcp`` SDK is unavailable the HTTP client test is skipped; the stdio
test always runs (raw JSON-RPC, no client library needed).
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import subprocess
import sys
import threading
import time

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _server_env() -> dict:
    e = dict(os.environ)
    mp = [str(ROOT / "packages" / "mcp"), str(ROOT)]
    e["PYTHONPATH"] = os.pathsep.join(mp + [e.get("PYTHONPATH", "")])
    return e


def _rpc(proc, obj) -> None:
    proc.stdin.write(json.dumps(obj) + "\n")
    proc.stdin.flush()


class TestLiveStdio:
    def _spawn(self):
        return subprocess.Popen(
            [sys.executable, "-m", "school_mcp.server", "stdio"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=_server_env(), cwd=str(ROOT),
        )

    def _session(self, calls):
        proc = self._spawn()
        lines: list[str] = []
        t = threading.Thread(
            target=lambda: lines.extend(ln.rstrip() for ln in proc.stdout), daemon=True
        )
        t.start()
        _rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                               "clientInfo": {"name": "live", "version": "1"}}})
        _rpc(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        for req in calls:
            _rpc(proc, req)
        deadline = time.time() + 10
        want = 2 + len(calls)
        while time.time() < deadline and len(lines) < want:
            time.sleep(0.05)
        try:
            proc.stdin.close()
            proc.terminate()
        except Exception:  # noqa: BLE001
            pass
        t.join(timeout=2)
        return [json.loads(ln) for ln in lines if ln.strip()]

    def _by_id(self, msgs, rid):
        for m in msgs:
            if m.get("id") == rid:
                return m
        return None

    def test_initialize_and_list_48_tools(self):
        msgs = self._session([{"jsonrpc": "2.0", "id": 2, "method": "tools/list",
                               "params": {}}])
        init = self._by_id(msgs, 1)
        assert init and "result" in init
        assert init["result"]["serverInfo"]["name"]
        listing = self._by_id(msgs, 2)
        tools = listing["result"]["tools"]
        assert len(tools) == 48
        # Flat schema: worktree (or the tool's own params), never a tool_args wrapper.
        for tool in tools:
            props = tool["inputSchema"].get("properties", {})
            assert "tool_args" not in props

    def test_tool_call_real_result(self):
        msgs = self._session([
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "school_status", "arguments": {"worktree": "."}}},
        ])
        call = self._by_id(msgs, 3)
        assert call and not call["result"].get("isError")
        text = call["result"]["content"][0]["text"]
        payload = json.loads(text)
        assert payload.get("ok") is True

    def test_tool_call_invalid_is_fail_open(self):
        msgs = self._session([
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
             "params": {"name": "school_recall", "arguments": {"worktree": ".", "query": None}}},
        ])
        call = self._by_id(msgs, 4)
        assert call and not call["result"].get("isError")  # never a protocol crash
        text = call["result"]["content"][0]["text"]
        payload = json.loads(text)  # still structured JSON
        assert payload.get("ok") is False

    def test_tool_call_hostile_never_crashes_transport(self):
        hostile = [None, {"self": "x"}, [1, 2], float("nan"), "x" * 5000, {"$": "\u0000"}]
        calls = [
            {"jsonrpc": "2.0", "id": 100 + i, "method": "tools/call",
             "params": {"name": "school_research", "arguments": {"worktree": ".", "query": h}}}
            for i, h in enumerate(hostile)
        ]
        msgs = self._session(calls)
        assert len(msgs) >= len(hostile)  # every call got a response
        for i in range(len(hostile)):
            call = self._by_id(msgs, 100 + i)
            assert call is not None and "result" in call
            json.loads(call["result"]["content"][0]["text"])  # valid JSON back

    def test_unknown_tool_is_graceful(self):
        msgs = self._session([
            {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
             "params": {"name": "school_does_not_exist", "arguments": {}}},
        ])
        call = self._by_id(msgs, 7)
        assert call is not None  # got a response, transport never died


class TestLiveHttp:
    def test_http_transport_end_to_end(self):
        mcp = pytest.importorskip("mcp")
        assert mcp
        try:
            from mcp.client.streamable_http import streamable_http_client
        except Exception:  # noqa: BLE001
            pytest.skip("streamable-http client unavailable in this SDK build")
        import anyio

        proc = subprocess.Popen(
            [sys.executable, "-m", "school_mcp.server", "http"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=_server_env(), cwd=str(ROOT),
        )
        try:
            time.sleep(2.0)  # let the HTTP listener bind

            async def run():
                from mcp import ClientSession

                async with (
                    streamable_http_client("http://127.0.0.1:8765/mcp") as (r, w),
                    ClientSession(r, w) as sess,
                ):
                    await sess.initialize()
                    return await sess.list_tools()

            result = anyio.run(run)
            assert len(result.tools) == 48
        finally:
            with contextlib.suppress(Exception):
                proc.terminate()
