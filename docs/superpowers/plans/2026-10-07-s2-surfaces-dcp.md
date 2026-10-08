# S2: Surfaces & DCP Coexistence — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put the S1 context engine on every surface: OpenCode plugin apply-view (request-time compressed view), MCP mirror (`school_context_status|compress|restore`), `school context` CLI, DCP coexistence (detect → quiet offer → clean break), and Apple-grade chips on footer/CLI/MCP — fail-open everywhere.

**Architecture:** The engine stays in Python (`core/context/`, S1). The plugin asks the bridge for a *view* at request time via `experimental.chat.messages.transform` (verified spike: `output.messages: {info, parts}[]`, request-time only — session history never mutated). The bridge answers with **segments** (`{index, role, content|null}`) aligned to the original messages; the plugin rebuilds `output.messages` from the original wrappers (drop/replace only — never synthesizes messages). DCP coexistence is a tiny state machine in `core/context/coexist.py`: absent → School owns view; present → view off until the user picks `switch`/`keep`; the third-party plugin is never disabled, patched, or written to. All five bridge commands (`context_status|compress|restore|view|coexist`) are the single source of truth; MCP, CLI, and the plugin are thin clients over them.

**Tech Stack:** Python 3.14 stdlib only; existing TS plugin (no new imports beyond the allowed set); zod via `tool.schema` for plugin args; node v24 (native TS type stripping) for the live harness. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-06-school-context-engine-design.md` (authoritative — re-read **§6**, §10 S2 exit criteria, §11 constraints when in doubt). Spike: `.superpowers/sdd/2026-10-06-s2-surfaces/spike-apply-view.md` (binding: apply-view = `experimental.chat.messages.transform`; supporting hooks `config`, `experimental.session.compacting`, `client.tui.showToast`).

**Baseline (verified 2026-10-07):** 3049 tests collected; `school/plugin_source.py` ruff = exactly 16 E501 (exit 1); HEAD `c62e3ce`; ruff line-length 100.

## Global Constraints

- **Do NOT commit** at any point unless the user explicitly asks. Steps below have no commit steps on purpose. Do not touch `.superpowers/`, `.opencode/goals/`, or unrelated dirty working-tree files (`core/routing/v26/*`, `core/skillgen/*`, `tests/unit/test_skillgen_*`, etc. — leave them exactly as found).
- **Fail-open everywhere:** any exception in any new path → original messages/payload unchanged; hooks never break a request, tool, or response.
- Kill switches: `SCHOOL_COMPRESS=0` (view/compress off), `SCHOOL_CTX=0` (all context surfaces report disabled/off), `SCHOOL_HOOKS=0` (plugin hooks off). Existing `SCHOOL_ROUTE`/ctx-optimizer behavior unchanged.
- Model budget: only `ContextEngine.compress` may spend model calls (S1 ladder, `SCHOOL_COMPRESS_MAX_CALLS_PER_TASK`, default 4). **apply-view never calls a model** — `context_view` is prompt-side only.
- Originals never mutated: `context_view`/`view_segments` must not modify the caller's `messages`; the plugin only rewrites `output.messages` (request-time view), never session history.
- Never disable, patch, write, or delete the third-party DCP plugin or its files; all coexistence state lives in `<context_dir>/coexistence.json` (inside `.school/context/`). Clean break on `switch` (no state import).
- No secrets in logs/JSON responses; summaries stay redacted (S1 engine handles this).
- Product name **School only** — the previous brand word must never appear anywhere in this plan's code, tests, or docs.
- Apple-grade chip voice (spec §6): `[school] ctx 62% · −18.4k tok` / `[school] compacted 2 blocks · restorable` — one calm monospace line, middle-dot segments, same voice across footer, CLI, MCP. Token cost (`$0.07`) is S3 — omit `spend_usd` in S2.
- Backward compat: existing 7 Phase-1 skill tools, 5 Phase-2 GitHub tools, memory, routing, footer, MCP parity — all stay green. Existing hook/transform behavior (recall injection, footer idempotency) must keep its asserted substrings byte-for-byte.
- Ruff `E,W,F,I,B,UP,SIM` line-length 100 on every touched Python file; **`school/plugin_source.py` must stay exactly 16 E501** — every new TS line (it lives in a Python string) must be ≤ 100 chars.
- Testing: no live network, no real opencode, no real LLM. Models mocked (`judge=None`); bridge/MCP talk through in-process handlers or local subprocesses only.
- Verification commands (use verbatim):
  - unit: `& ".venv\Scripts\python.exe" -m pytest -q --no-header -p no:cacheprovider tests/unit/<file>`
  - battery: `& ".venv\Scripts\python.exe" -m pytest -q --no-header -p no:cacheprovider`
  - ruff: `& ".venv\Scripts\python.exe" -m ruff check <files>`
  - TS syntax gate: `& ".venv\Scripts\python.exe" -m pytest -q --no-header -p no:cacheprovider tests/integration/test_plugin_live.py` (runs the real plugin through node; `node --check` cannot parse TS — see Self-Review Notes).

## File Structure

| File | Responsibility |
|---|---|
| `core/context/coexist.py` (create) | `ctx_enabled`, `load/save_state`, `detect_dcp` (+ cache), `view_mode`, `OFFER_TEXT` |
| `core/context/view.py` (extend) | `view_segments(messages, blocks)` + `apply_segments(messages, segments)` — the adapter-side contract of the view |
| `school/bridge.py` (extend) | `context_status/compress/restore/view/coexist` handlers registered in `_COMMANDS` |
| `school/mcp/server.py` (extend) | 3 tools appended to `_TOOLS` (byte-equal TS descriptions, annotations) |
| `school/plugin_source.py` (extend) | apply-view transform, DCP detection + offer, footer chip, compacting nudge, 3 TS tools |
| `school/cli.py` (extend) | `school context status\|compress\|restore\|switch\|keep` (`--json`, stdin messages) |
| `tests/unit/test_context_coexist.py` (create) | Task 1 |
| `tests/unit/test_bridge_context.py` (create) | Task 2 (segments + bridge ops) |
| `tests/unit/test_school_plugin_hooks.py` (extend) | Tasks 3, 4, 8 (append classes at END) |
| `tests/unit/test_mcp_server.py`, `tests/integration/test_mcp_stdio.py`, `tests/unit/test_school_plugin_bridge.py` (extend) | Task 5 list updates + new class at END |
| `tests/unit/test_cli.py` (extend) | Task 6 (append at END) |
| `tests/unit/test_context_chip_wiring.py` (create) | Task 7 |
| `tests/integration/test_context_surfaces.py` (create) | Task 9 (bridge subprocess + live node apply-view) |

**Adapter contract (spec §6) → S2 mapping:** `on_tool_result(payload)` = existing `tool.execute.after` (skeletonization, unchanged); `apply_view(view)` = `experimental.chat.messages.transform` + `context_view` (Task 3); `emit_chip(status)` = footer `experimental.text.complete` + chip fields on CLI/MCP (Tasks 2/5/7). Framework adapters ship in S4 — the contract is exercised here only through the OpenCode surface.

**Consumed existing code (do not modify beyond the noted additions):**
- `core.context.ContextEngine(worktree, session_id, judge=_AUTO, budget=None, clock=...)` with `.compress(messages) -> CompressionReport`, `.view(messages) -> ViewResult`, `.restore(block_id="") -> dict`, `.store`, `.window`.
- `core.context.build_chip(*, blocks_added=0, restores=0, saved_tokens=0, used_ratio=None, spend_usd=None) -> str`.
- `core.context.layer0.total_tokens(messages)`; `core.context.store.context_dir(worktree)` = `resolve_memory_dir(worktree).parent / "context"` (creates `.school/memory` on demand; `.school/` is gitignored).
- `school.bridge._COMMANDS` / `school.mcp.server._bridge_call` / `_build_request` (auto-dispatches `school_X` → bridge command `X`).
- TS plugin: `invokeBridge(python, bridgePath, req, timeoutMs?)`, `hooksEnabled()`, `ctxEnabled()`, `ctxEstimate`, `schoolStatus`/`schoolStatusParts()`/`schoolFooter()`, `recordCtxSavings`.
- Test helpers: `_hook_block(name)`, `_fn_block(name)` (`tests/unit/test_school_plugin_hooks.py`), `_tool_block(name)` (`tests/unit/test_school_plugin_bridge.py`), `plugin_dir` fixture pattern (`tests/integration/test_plugin_live.py`).

## Task Batches

- **Batch 1** — Tasks 1–2: coexistence core + segment protocol + all five bridge commands.
- **Batch 2** — Tasks 3–4: plugin apply-view, then DCP detection/offer/ownership gate.
- **Batch 3** — Tasks 5–6: MCP 3-tool mirror + `school context` CLI.
- **Batch 4** — Tasks 7–8: chip rendering across surfaces + compaction nudge.
- **Batch 5** — Task 9: integration suite (subprocess bridge + live node) and full regression gates.

---

### Task 1: Coexistence core (`core/context/coexist.py`)

**Files:**
- Create: `core/context/coexist.py`
- Test: `tests/unit/test_context_coexist.py`

**Interfaces:**
- Produces: `ctx_enabled() -> bool`, `state_path(worktree) -> Path`, `load_state(worktree) -> dict`, `save_state(worktree, patch) -> dict`, `detect_dcp(worktree, home=None) -> bool`, `detect_dcp_cached(worktree) -> bool`, `clear_cache()`, `view_mode(worktree, dcp_hint=False) -> "off"|"school"|"dcp"`, constants `STATE_FILE`, `DCP_TOKEN`, `MAX_READ_BYTES`, `OFFER_TEXT`. Later tasks import these exact names.

- [ ] **Step 1: Write the failing tests**

```python
"""S2 Task 1: DCP coexistence state, detection, and view mode."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.context.coexist import (
    DCP_TOKEN,
    OFFER_TEXT,
    clear_cache,
    ctx_enabled,
    detect_dcp,
    detect_dcp_cached,
    load_state,
    save_state,
    state_path,
    view_mode,
)


@pytest.fixture(autouse=True)
def _fresh_cache():
    clear_cache()
    yield
    clear_cache()


def test_ctx_enabled_kill_switch(monkeypatch) -> None:
    monkeypatch.delenv("SCHOOL_CTX", raising=False)
    assert ctx_enabled() is True
    monkeypatch.setenv("SCHOOL_CTX", "0")
    assert ctx_enabled() is False


def test_view_mode_off_when_compress_disabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SCHOOL_COMPRESS", "0")
    assert view_mode(str(tmp_path)) == "off"
    monkeypatch.delenv("SCHOOL_COMPRESS", raising=False)
    assert view_mode(str(tmp_path)) == "school"


def test_state_defaults_and_roundtrip(tmp_path) -> None:
    wt = str(tmp_path)
    assert load_state(wt) == {
        "version": 1,
        "dcp_seen": False,
        "offer_shown": False,
        "decision": "",
    }
    save_state(wt, {"offer_shown": True, "dcp_seen": True})
    state = load_state(wt)
    assert state["offer_shown"] is True
    assert state["dcp_seen"] is True
    save_state(wt, {"decision": "switch"})
    assert load_state(wt)["decision"] == "switch"
    expected = tmp_path / ".school" / "context" / "coexistence.json"
    assert state_path(wt) == expected


def test_state_rejects_unknown_decision(tmp_path) -> None:
    save_state(str(tmp_path), {"decision": "destroy"})
    assert load_state(str(tmp_path))["decision"] == ""


def test_corrupt_state_fails_open(tmp_path) -> None:
    path = state_path(str(tmp_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    state = load_state(str(tmp_path))
    assert state["decision"] == ""
    assert state["offer_shown"] is False


def test_detect_dcp_project_config(tmp_path) -> None:
    (tmp_path / "opencode.json").write_text(
        json.dumps({"plugin": ["@tarquinen/opencode-dcp"]}), encoding="utf-8"
    )
    assert detect_dcp(str(tmp_path), home=tmp_path / "home") is True


def test_detect_dcp_absent(tmp_path) -> None:
    (tmp_path / "opencode.json").write_text(
        json.dumps({"plugin": []}), encoding="utf-8"
    )
    assert detect_dcp(str(tmp_path), home=tmp_path / "home") is False


def test_detect_dcp_jsonc_and_tuple_entry(tmp_path) -> None:
    (tmp_path / "opencode.jsonc").write_text(
        '// comment\n{"plugin": [["@tarquinen/opencode-dcp", {"depth": 3}]]}',
        encoding="utf-8",
    )
    assert detect_dcp(str(tmp_path), home=tmp_path / "home") is True


def test_detect_dcp_project_subdir_config(tmp_path) -> None:
    sub = tmp_path / ".opencode"
    sub.mkdir()
    (sub / "opencode.json").write_text(
        '{"plugin": ["@tarquinen/opencode-dcp"]}', encoding="utf-8"
    )
    assert detect_dcp(str(tmp_path), home=tmp_path / "home") is True


def test_detect_dcp_global_config_uses_home_param(tmp_path) -> None:
    home = tmp_path / "home"
    cfg = home / ".config" / "opencode"
    cfg.mkdir(parents=True)
    (cfg / "opencode.json").write_text(
        '{"plugin": ["@tarquinen/opencode-dcp"]}', encoding="utf-8"
    )
    assert detect_dcp(str(tmp_path / "empty"), home=home) is True


def test_detect_dcp_plugin_dir_by_name(tmp_path) -> None:
    plug = tmp_path / ".opencode" / "plugins"
    plug.mkdir(parents=True)
    (plug / "dcp.ts").write_text("// nothing", encoding="utf-8")
    assert detect_dcp(str(tmp_path), home=tmp_path / "home") is True


def test_detect_dcp_plugin_dir_by_token(tmp_path) -> None:
    plug = tmp_path / ".opencode" / "plugins"
    plug.mkdir(parents=True)
    (plug / "other.ts").write_text(f'import "{DCP_TOKEN}"', encoding="utf-8")
    assert detect_dcp(str(tmp_path), home=tmp_path / "home") is True


def test_detect_dcp_bounded_read(tmp_path) -> None:
    pad = "x" * 1_200_000
    (tmp_path / "opencode.json").write_text(
        f'{{"plugin": ["{DCP_TOKEN}"], "pad": "{pad}"}}', encoding="utf-8"
    )
    assert detect_dcp(str(tmp_path), home=tmp_path / "home") is True


def test_detect_dcp_cached(tmp_path) -> None:
    wt = str(tmp_path)
    assert detect_dcp_cached(wt) is False
    (tmp_path / "opencode.json").write_text(
        json.dumps({"plugin": [DCP_TOKEN]}), encoding="utf-8"
    )
    assert detect_dcp_cached(wt) is False  # negative answer is cached
    clear_cache()
    assert detect_dcp_cached(wt) is True


def test_view_mode_switch_overrides_dcp(tmp_path) -> None:
    wt = str(tmp_path)
    (tmp_path / "opencode.json").write_text(
        json.dumps({"plugin": [DCP_TOKEN]}), encoding="utf-8"
    )
    assert view_mode(wt) == "dcp"
    save_state(wt, {"decision": "switch"})
    assert view_mode(wt) == "school"


def test_view_mode_keep_and_dcp_hint(tmp_path, monkeypatch) -> None:
    wt = str(tmp_path)
    assert view_mode(wt) == "school"
    assert view_mode(wt, dcp_hint=True) == "dcp"
    save_state(wt, {"decision": "keep"})
    assert view_mode(wt) == "dcp"
    monkeypatch.setenv("SCHOOL_CTX", "0")
    assert view_mode(wt) == "off"


def test_offer_text_matches_spec() -> None:
    assert OFFER_TEXT.startswith(
        "School can now handle compression — with restore, budgets, and status."
    )
    assert "school context switch" in OFFER_TEXT
    assert "school context keep" in OFFER_TEXT
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `& ".venv\Scripts\python.exe" -m pytest -q --no-header -p no:cacheprovider tests/unit/test_context_coexist.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.context.coexist'`

- [ ] **Step 3: Implement coexist.py**

```python
# core/context/coexist.py
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from core.context.store import context_dir

STATE_FILE = "coexistence.json"
DCP_TOKEN = "@tarquinen/opencode-dcp"
MAX_READ_BYTES = 1_048_576
OFFER_TEXT = (
    "School can now handle compression — with restore, budgets, and status. "
    "Keep DCP, or switch? Run `school context switch` or "
    "`school context keep` to decide."
)

_DCP_CACHE: dict[str, bool] = {}


def ctx_enabled() -> bool:
    return os.environ.get("SCHOOL_CTX", "") != "0"


def state_path(worktree: str) -> Path:
    return context_dir(worktree) / STATE_FILE


def load_state(worktree: str) -> dict[str, Any]:
    try:
        data = json.loads(state_path(worktree).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            decision = str(data.get("decision", "") or "")
            return {
                "version": 1,
                "dcp_seen": bool(data.get("dcp_seen")),
                "offer_shown": bool(data.get("offer_shown")),
                "decision": decision if decision in {"switch", "keep"} else "",
            }
    except (OSError, ValueError, TypeError):
        pass
    return {"version": 1, "dcp_seen": False, "offer_shown": False, "decision": ""}


def save_state(worktree: str, patch: dict[str, Any]) -> dict[str, Any]:
    try:
        state = load_state(worktree)
        merged = {**state, **{k: v for k, v in patch.items() if k in state}}
        if merged.get("decision") not in {"", "switch", "keep"}:
            merged["decision"] = state["decision"]
        path = state_path(worktree)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(merged, indent=1), encoding="utf-8")
        return merged
    except OSError:
        return load_state(worktree)


def _read_bounded(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            return handle.read(MAX_READ_BYTES)
    except OSError:
        return ""


def detect_dcp(worktree: str, home: Path | None = None) -> bool:
    home_path = Path.home() if home is None else Path(home)
    root = Path(worktree)
    configs = [
        root / "opencode.json",
        root / "opencode.jsonc",
        root / ".opencode" / "opencode.json",
        root / ".opencode" / "opencode.jsonc",
        home_path / ".config" / "opencode" / "opencode.json",
        home_path / ".config" / "opencode" / "opencode.jsonc",
    ]
    for path in configs:
        if DCP_TOKEN in _read_bounded(path):
            return True
    dirs = [
        root / ".opencode" / "plugins",
        root / "plugins",
        home_path / ".config" / "opencode" / "plugins",
    ]
    for folder in dirs:
        try:
            names = sorted(p.name for p in folder.iterdir() if p.is_file())[:200]
        except OSError:
            continue
        if any("dcp" in name.lower() for name in names):
            return True
        for name in names:
            if name.endswith((".ts", ".js", ".mjs")):
                if DCP_TOKEN in _read_bounded(folder / name):
                    return True
    return False


def detect_dcp_cached(worktree: str) -> bool:
    key = str(Path(worktree))
    if key not in _DCP_CACHE:
        _DCP_CACHE[key] = detect_dcp(key)
    return _DCP_CACHE[key]


def clear_cache() -> None:
    _DCP_CACHE.clear()


def view_mode(worktree: str, dcp_hint: bool = False) -> str:
    if not ctx_enabled():
        return "off"
    if os.environ.get("SCHOOL_COMPRESS", "") == "0":
        return "off"
    state = load_state(worktree)
    decision = state.get("decision", "")
    if decision == "switch":
        return "school"
    if decision == "keep":
        return "dcp"
    if dcp_hint or detect_dcp_cached(worktree):
        return "dcp"
    return "school"


__all__ = [
    "DCP_TOKEN",
    "MAX_READ_BYTES",
    "OFFER_TEXT",
    "STATE_FILE",
    "clear_cache",
    "ctx_enabled",
    "detect_dcp",
    "detect_dcp_cached",
    "load_state",
    "save_state",
    "state_path",
    "view_mode",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `& ".venv\Scripts\python.exe" -m pytest -q --no-header -p no:cacheprovider tests/unit/test_context_coexist.py`
Expected: 16 passed

- [ ] **Step 5: Ruff**

Run: `& ".venv\Scripts\python.exe" -m ruff check core/context/coexist.py tests/unit/test_context_coexist.py`
Expected: All checks passed!

---

### Task 2: Segment protocol + five bridge commands

**Files:**
- Edit: `core/context/view.py` (append `view_segments`, `apply_segments`)
- Edit: `school/bridge.py` (five handlers + `_COMMANDS` registration)
- Test: `tests/unit/test_bridge_context.py`

**Interfaces:**
- Produces: `view_segments(messages, blocks) -> list[dict]` where each dict is `{"index": int, "role": str, "content": str | None}` (`None` = drop the message; only changed indices are listed); `apply_segments(messages, segments) -> list` (never mutates input).
- Bridge commands (all JSON over the existing protocol, all fail-open): `context_status`, `context_compress`, `context_restore`, `context_view`, `context_coexist`. MCP (`school_context_*`), CLI, and the plugin dispatch to these in Tasks 3/5/6.

- [ ] **Step 1: Write the failing tests**

```python
"""S2 Task 2: view segments and the five context bridge commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.context import ContextEngine, build_chip, build_view
from core.context.view import apply_segments, view_segments
from school import bridge


def big_msgs(n: int = 8) -> list[dict]:
    return [
        {"role": "user" if i % 2 == 0 else "assistant", "content": chr(97 + i) * 300}
        for i in range(n)
    ]


@pytest.fixture()
def compressed(tmp_path, monkeypatch) -> tuple[str, list[dict], list]:
    monkeypatch.setenv("SCHOOL_COMPRESS_WINDOW_TOKENS", "200")
    monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
    messages = big_msgs()
    engine = ContextEngine(str(tmp_path), "s1", judge=None)
    report = engine.compress(messages)
    assert report.blocks_added >= 1
    return str(tmp_path), messages, engine.store.load()


def call(command: str, req: dict) -> dict:
    return bridge._COMMANDS[command](req)


class TestSegments:
    def test_segments_match_build_view(self, compressed) -> None:
        _, messages, blocks = compressed

        def roles(items):
            return [(m.get("role"), m.get("content")) for m in items]

        applied = apply_segments(messages, view_segments(messages, blocks))
        assert roles(applied) == roles(build_view(messages, blocks).messages)

    def test_segments_do_not_mutate_input(self, compressed) -> None:
        _, messages, blocks = compressed
        snapshot = [dict(m) for m in messages]
        view_segments(messages, blocks)
        assert messages == snapshot

    def test_no_blocks_means_identity(self) -> None:
        messages = big_msgs(4)
        assert view_segments(messages, []) == []
        assert apply_segments(messages, []) == messages

    def test_skeleton_lines_become_replacements(self) -> None:
        messages = [
            {"role": "user", "content": "q"},
            {"role": "tool", "content": "one\nkeep … marker\nthree"},
            {"role": "assistant", "content": "a"},
        ]
        segments = view_segments(messages, [])
        assert segments == [
            {"index": 1, "role": "", "content": "keep … marker"},
        ]

    def test_apply_segments_never_mutates(self) -> None:
        messages = [{"role": "user", "content": "keep"}]
        out = apply_segments(
            messages, [{"index": 0, "role": "system", "content": "replaced"}]
        )
        assert messages[0]["content"] == "keep"
        assert out[0]["content"] == "replaced"
        assert out[0]["role"] == "system"


class TestContextView:
    def test_returns_segments_and_ctx_chip(self, compressed) -> None:
        worktree, messages, _ = compressed
        resp = call(
            "context_view",
            {"worktree": worktree, "session": "s1", "messages": messages},
        )
        assert resp["ok"] is True
        assert resp["mode"] == "school"
        assert resp["segments"], "compressed session must yield segments"
        assert resp["segments"][0]["content"].startswith(
            "[school] compacted b"
        )
        assert resp["chip"].startswith("[school] ctx")
        assert "tok" in resp["chip"]

    def test_kill_switch_returns_no_segments(self, compressed, monkeypatch) -> None:
        worktree, messages, _ = compressed
        monkeypatch.setenv("SCHOOL_COMPRESS", "0")
        resp = call(
            "context_view",
            {"worktree": worktree, "session": "s1", "messages": messages},
        )
        assert resp == {"ok": True, "mode": "off", "segments": [], "chip": ""}

    def test_disabled_by_school_ctx(self, compressed, monkeypatch) -> None:
        worktree, messages, _ = compressed
        monkeypatch.setenv("SCHOOL_CTX", "0")
        resp = call(
            "context_view",
            {"worktree": worktree, "session": "s1", "messages": messages},
        )
        assert resp["mode"] == "off"
        assert resp["segments"] == []

    def test_dcp_keep_decision_yields_no_segments(self, compressed) -> None:
        worktree, messages, _ = compressed
        from core.context.coexist import save_state

        save_state(worktree, {"decision": "keep"})
        resp = call(
            "context_view",
            {"worktree": worktree, "session": "s1", "messages": messages},
        )
        assert resp["mode"] == "dcp"
        assert resp["segments"] == []
        assert resp["chip"] == ""

    def test_junk_messages_fail_open(self, compressed) -> None:
        worktree, _, _ = compressed
        resp = call(
            "context_view",
            {"worktree": worktree, "session": "s1", "messages": "nope"},
        )
        assert resp["ok"] is True
        assert resp["segments"] == []


class TestContextStatusCompressRestore:
    def test_status_reports_blocks_and_chip(self, compressed) -> None:
        worktree, _, _ = compressed
        resp = call(
            "context_status", {"worktree": worktree, "session": "s1"}
        )
        assert resp["ok"] is True
        assert resp["mode"] == "school"
        assert resp["dcp"] is False
        assert resp["blocks"] >= 1
        assert resp["chip"].startswith("[school] compacted")
        assert resp["tokens_saved"] > 0

    def test_status_empty_session(self, tmp_path) -> None:
        resp = call(
            "context_status",
            {"worktree": str(tmp_path), "session": "fresh"},
        )
        assert resp["ok"] is True
        assert resp["blocks"] == 0
        assert resp["chip"] == ""
        assert resp["decision"] == ""

    def test_status_disabled(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("SCHOOL_CTX", "0")
        resp = call(
            "context_status", {"worktree": str(tmp_path), "session": "s1"}
        )
        assert resp["disabled"] is True
        assert resp["mode"] == "off"
        assert resp["chip"] == ""

    def test_compress_writes_blocks(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("SCHOOL_COMPRESS_WINDOW_TOKENS", "200")
        monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
        resp = call(
            "context_compress",
            {"worktree": str(tmp_path), "session": "c1", "messages": big_msgs()},
        )
        assert resp["ok"] is True
        assert resp["triggered"] is True
        assert resp["blocks_added"] >= 1
        assert resp["tokens_saved"] > 0
        assert resp["chip"].startswith("[school] compacted")

    def test_compress_empty_messages_skips(self, tmp_path) -> None:
        resp = call(
            "context_compress",
            {"worktree": str(tmp_path), "session": "c1", "messages": []},
        )
        assert resp["ok"] is True
        assert resp["triggered"] is False
        assert resp["skipped"] in {"empty", "below_threshold"}
        assert resp["chip"] == ""

    def test_restore_roundtrip_is_idempotent(self, compressed) -> None:
        worktree, _, _ = compressed
        first = call(
            "context_restore", {"worktree": worktree, "session": "s1"}
        )
        assert first["ok"] is True
        assert first["messages"]
        assert first["chip"].startswith("[school] compacted")
        assert first["restores"] >= 1
        second = call(
            "context_restore", {"worktree": worktree, "session": "s1"}
        )
        assert second["restores"] == first["restores"] + 1

    def test_restore_unknown_block(self, tmp_path) -> None:
        resp = call(
            "context_restore",
            {"worktree": str(tmp_path), "session": "s1", "block_id": "b999"},
        )
        assert resp["ok"] is False
        assert resp["reason"] in {"no_blocks", "block_not_found"}
        assert resp["chip"] == ""

    def test_status_survives_corrupt_store(self, tmp_path) -> None:
        from core.context.store import session_file

        path = session_file(str(tmp_path), "bad")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{{{", encoding="utf-8")
        resp = call(
            "context_status", {"worktree": str(tmp_path), "session": "bad"}
        )
        assert resp["ok"] is True
        assert resp["blocks"] == 0


class TestContextCoexist:
    def test_get_defaults(self, tmp_path) -> None:
        resp = call(
            "context_coexist",
            {"worktree": str(tmp_path), "action": "get"},
        )
        assert resp["ok"] is True
        assert resp["dcp"] is False
        assert resp["decision"] == ""
        assert resp["mode"] == "school"
        assert resp["offer"].startswith("School can now handle compression")

    def test_set_offer_and_decision(self, tmp_path) -> None:
        wt = str(tmp_path)
        set_offer = call(
            "context_coexist",
            {"worktree": wt, "action": "set_offer"},
        )
        assert set_offer == {"ok": True, "offer_shown": True}
        switch = call(
            "context_coexist",
            {"worktree": wt, "action": "set_decision", "decision": "switch"},
        )
        assert switch["ok"] is True
        assert switch["mode"] == "school"
        state = json.loads(
            Path(wt, ".school", "context", "coexistence.json").read_text(
                encoding="utf-8"
            )
        )
        assert state["decision"] == "switch"
        assert state["offer_shown"] is True

    def test_rejects_bad_inputs(self, tmp_path) -> None:
        wt = str(tmp_path)
        bad = call(
            "context_coexist",
            {"worktree": wt, "action": "set_decision", "decision": "delete"},
        )
        assert bad["ok"] is False
        assert bad["error"]["type"] == "validation"
        unknown = call(
            "context_coexist", {"worktree": wt, "action": "explode"}
        )
        assert unknown["ok"] is False

    def test_hint_marks_dcp_seen(self, tmp_path) -> None:
        wt = str(tmp_path)
        resp = call(
            "context_coexist",
            {"worktree": wt, "action": "get", "dcp": True},
        )
        assert resp["dcp"] is True
        assert resp["mode"] == "dcp"
        state = json.loads(
            Path(wt, ".school", "context", "coexistence.json").read_text(
                encoding="utf-8"
            )
        )
        assert state["dcp_seen"] is True


class TestWiring:
    def test_all_five_commands_registered(self) -> None:
        for name in (
            "context_status",
            "context_compress",
            "context_restore",
            "context_view",
            "context_coexist",
        ):
            assert name in bridge._COMMANDS, name

    def test_chip_voice_helpers(self, compressed) -> None:
        worktree, messages, _ = compressed
        view = call(
            "context_view",
            {"worktree": worktree, "session": "s1", "messages": messages},
        )
        assert build_chip(used_ratio=0.62, saved_tokens=18400) == (
            "[school] ctx 62% · −18.4k tok"
        )
        assert view["chip"].startswith("[school] ctx")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `& ".venv\Scripts\python.exe" -m pytest -q --no-header -p no:cacheprovider tests/unit/test_bridge_context.py`
Expected: FAIL — `ImportError: cannot import name 'view_segments' from 'core.context.view'` (and `KeyError: 'context_status'` once past the import)

- [ ] **Step 3: Add `view_segments` / `apply_segments` to `core/context/view.py`**

Append after `build_view` (keep everything above untouched):

```python
def view_segments(messages: list[Any], blocks: list[Block]) -> list[dict[str, Any]]:
    """Per-index edits that turn `messages` into the view. Never mutates.

    Walk mirrors build_view exactly: block start -> marker replacement,
    block interior -> drop (`content: None`), skeleton candidates ->
    skeletonized content. Only changed indices appear in the output.
    """
    try:
        valid = [b for b in blocks if b.id and 0 <= b.start < b.end <= len(messages)]
        valid.sort(key=lambda b: b.start)
        out: list[dict[str, Any]] = []
        i, bidx = 0, 0
        while i < len(messages):
            while bidx < len(valid) and valid[bidx].end <= i:
                bidx += 1
            block = None
            if bidx < len(valid) and valid[bidx].start == i:
                block = valid[bidx]
                bidx += 1
            if block is not None:
                out.append(
                    {
                        "index": i,
                        "role": "system",
                        "content": f"[school] compacted {block.id}: {block.summary}",
                    }
                )
                for j in range(i + 1, block.end):
                    out.append({"index": j, "role": "", "content": None})
                i = block.end
                continue
            message = messages[i]
            if isinstance(message, dict) and _is_skeleton_candidate(message):
                out.append(
                    {
                        "index": i,
                        "role": "",
                        "content": _skeletonize(str(message["content"])),
                    }
                )
            i += 1
        return out
    except Exception:  # fail open — never raise into the caller
        return []


def apply_segments(messages: list[Any], segments: list[dict[str, Any]]) -> list[Any]:
    """Apply view segments the way adapters must. Never mutates `messages`."""
    try:
        edits: dict[int, dict[str, Any]] = {}
        for seg in segments:
            if isinstance(seg, dict) and "index" in seg:
                edits[int(seg["index"])] = seg
        out: list[Any] = []
        for i, message in enumerate(messages):
            edit = edits.get(i)
            if edit is not None and edit.get("content") is None:
                continue
            if edit is None:
                out.append(copy.deepcopy(message))
                continue
            replacement = copy.deepcopy(message)
            if not isinstance(replacement, dict):
                replacement = {"content": ""}
            role = str(edit.get("role") or "")
            if role:
                replacement["role"] = role
            replacement["content"] = str(edit.get("content") or "")
            out.append(replacement)
        return out
    except Exception:  # fail open
        try:
            return copy.deepcopy(list(messages))
        except Exception:
            return []


__all__ = ["apply_segments", "build_view", "view_segments"]
```

Also replace the existing `__all__ = ["build_view"]` line (do not leave two).

- [ ] **Step 4: Add the five bridge handlers**

In `school/bridge.py`, insert after `_handle_skeleton` and before the `_COMMANDS` dict:

```python
# --- Context engine surfaces (S2) --------------------------------------


def _engine_for(req: dict[str, Any]) -> Any:
    from core.context import ContextEngine

    worktree = str(req.get("worktree", "") or ".")
    session = str(req.get("session", "") or "default")
    return ContextEngine(worktree, session)


def _ctx_messages(req: dict[str, Any]) -> list[dict[str, Any]]:
    messages = req.get("messages")
    return messages if isinstance(messages, list) else []


def _handle_context_status(req: dict[str, Any]) -> dict[str, Any]:
    from core.context import build_chip
    from core.context.coexist import detect_dcp, load_state, view_mode

    worktree = str(req.get("worktree", "") or ".")
    from core.context.coexist import ctx_enabled

    if not ctx_enabled():
        return {"ok": True, "mode": "off", "disabled": True, "chip": ""}
    engine = _engine_for(req)
    blocks = engine.store.load()
    restores = sum(b.restores for b in blocks)
    saved = sum(max(0, b.tokens_original - b.tokens_summary) for b in blocks)
    chip = build_chip(blocks_added=len(blocks), restores=restores) if blocks else ""
    return {
        "ok": True,
        "mode": view_mode(worktree),
        "dcp": detect_dcp(worktree),
        "decision": load_state(worktree)["decision"],
        "offer_shown": load_state(worktree)["offer_shown"],
        "session": engine.session_id,
        "blocks": len(blocks),
        "restores": restores,
        "tokens_saved": saved,
        "chip": chip,
    }


def _handle_context_view(req: dict[str, Any]) -> dict[str, Any]:
    from core.context import build_chip
    from core.context.coexist import ctx_enabled, view_mode
    from core.context.layer0 import total_tokens
    from core.context.view import build_view, view_segments

    worktree = str(req.get("worktree", "") or ".")
    if not ctx_enabled():
        return {"ok": True, "mode": "off", "segments": [], "chip": ""}
    mode = view_mode(worktree, dcp_hint=bool(req.get("dcp")))
    messages = _ctx_messages(req)
    if mode != "school" or not messages:
        return {"ok": True, "mode": mode, "segments": [], "chip": ""}
    engine = _engine_for(req)
    blocks = engine.store.load()
    segments = view_segments(messages, blocks)
    if not segments:
        return {"ok": True, "mode": mode, "segments": [], "chip": ""}
    before = total_tokens(messages)
    after = total_tokens(build_view(messages, blocks).messages)
    ratio = after / engine.window if engine.window > 0 else None
    chip = build_chip(used_ratio=ratio, saved_tokens=max(0, before - after))
    return {"ok": True, "mode": mode, "segments": segments, "chip": chip}


def _handle_context_compress(req: dict[str, Any]) -> dict[str, Any]:
    from core.context import build_chip
    from core.context.coexist import ctx_enabled, view_mode

    worktree = str(req.get("worktree", "") or ".")
    if not ctx_enabled():
        return {"ok": True, "disabled": True, "chip": ""}
    engine = _engine_for(req)
    report = engine.compress(_ctx_messages(req))
    chip = ""
    if report.triggered and report.blocks_added > 0:
        chip = build_chip(
            blocks_added=report.blocks_added,
            saved_tokens=max(0, report.tokens_before - report.tokens_after),
        )
    return {
        "ok": True,
        "mode": view_mode(worktree),
        "triggered": report.triggered,
        "skipped": report.skipped,
        "layer_used": report.layer_used,
        "blocks_added": report.blocks_added,
        "tokens_before": report.tokens_before,
        "tokens_after": report.tokens_after,
        "tokens_saved": max(0, report.tokens_before - report.tokens_after),
        "chip": chip,
    }


def _handle_context_restore(req: dict[str, Any]) -> dict[str, Any]:
    from core.context import build_chip
    from core.context.coexist import ctx_enabled, view_mode

    worktree = str(req.get("worktree", "") or ".")
    if not ctx_enabled():
        return {"ok": True, "disabled": True, "chip": ""}
    engine = _engine_for(req)
    payload = engine.restore(str(req.get("block_id", "") or ""))
    chip = ""
    if payload.get("ok"):
        blocks = engine.store.load()
        chip = build_chip(
            blocks_added=len(blocks), restores=int(payload.get("restores", 0))
        )
    return {**payload, "mode": view_mode(worktree), "chip": chip}


def _handle_context_coexist(req: dict[str, Any]) -> dict[str, Any]:
    from core.context.coexist import (
        OFFER_TEXT,
        detect_dcp,
        load_state,
        save_state,
        view_mode,
    )

    worktree = str(req.get("worktree", "") or ".")
    hint = bool(req.get("dcp"))
    action = str(req.get("action", "get") or "get")
    if action == "get":
        if hint:
            save_state(worktree, {"dcp_seen": True})
        state = load_state(worktree)
        return {
            "ok": True,
            "dcp": detect_dcp(worktree) or hint,
            "decision": state["decision"],
            "offer_shown": state["offer_shown"],
            "mode": view_mode(worktree, dcp_hint=hint),
            "offer": OFFER_TEXT,
        }
    if action == "set_offer":
        save_state(worktree, {"offer_shown": True})
        return {"ok": True, "offer_shown": True}
    if action == "set_decision":
        decision = str(req.get("decision", "") or "")
        if decision not in {"switch", "keep"}:
            return {
                "ok": False,
                "error": {
                    "type": "validation",
                    "message": "decision must be switch or keep",
                },
            }
        save_state(worktree, {"decision": decision})
        return {
            "ok": True,
            "decision": decision,
            "mode": view_mode(worktree, dcp_hint=hint),
        }
    return {
        "ok": False,
        "error": {"type": "validation", "message": f"unknown action: {action}"},
    }
```

Then register in `_COMMANDS` (append after the `"skeleton"` entry):

```python
    "context_status": _handle_context_status,
    "context_compress": _handle_context_compress,
    "context_restore": _handle_context_restore,
    "context_view": _handle_context_view,
    "context_coexist": _handle_context_coexist,
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `& ".venv\Scripts\python.exe" -m pytest -q --no-header -p no:cacheprovider tests/unit/test_bridge_context.py`
Expected: all passed (≈30)

- [ ] **Step 6: Regression + ruff**

Run: `& ".venv\Scripts\python.exe" -m pytest -q --no-header -p no:cacheprovider tests/unit/test_context_view.py tests/unit/test_context_engine.py tests/unit/test_school_plugin_bridge.py`
Expected: all passed (view builder untouched except additions)

Run: `& ".venv\Scripts\python.exe" -m ruff check core/context/view.py school/bridge.py tests/unit/test_bridge_context.py`
Expected: All checks passed!

---

### Task 3: Plugin apply-view (`experimental.chat.messages.transform`)

**Files:**
- Edit: `school/plugin_source.py` (module consts, `viewTextOf`, `applyView`, transform hook restructure)
- Test: append `class TestApplyView` to `tests/unit/test_school_plugin_hooks.py`

**Interfaces:**
- Produces (TS): `const VIEW_TIMEOUT_MS = 4000`, module fn `viewTextOf(m)`, School-closure `const applyView = async (output) => Promise<void>` sending `command: "context_view"` with `{worktree, session, messages}`, rebuilding `output.messages` from originals.
- Consumes: bridge `context_view` (Task 2). Kills itself on `SCHOOL_HOOKS=0`, `SCHOOL_CTX=0`, `SCHOOL_COMPRESS=0`, missing bridge, timeout, or any error — in all cases messages stay untouched.

- [ ] **Step 1: Write the failing tests**

Append at the END of `tests/unit/test_school_plugin_hooks.py`:

```python
class TestApplyView:
    """apply-view: request-time compressed view via context_view segments."""

    def _block(self, name: str) -> str:
        match = re.search(
            rf"const {name} = async \([\s\S]*?\n  \}}", TS_PLUGIN_SOURCE
        )
        assert match is not None, f"const {name} not found"
        return match.group(0)

    def test_transform_calls_apply_view_first(self) -> None:
        block = _hook_block("experimental.chat.messages.transform")
        assert "await applyView(output)" in block
        assert block.index("await applyView(output)") < block.index(
            'info.role !== "user"'
        )

    def test_apply_view_defined_in_school_scope(self) -> None:
        source = TS_PLUGIN_SOURCE
        assert "const applyView = async" in source
        assert source.index("const recallForExecution = async") < source.index(
            "const applyView = async"
        )

    def test_apply_view_gates_kill_switches(self) -> None:
        block = self._block("applyView")
        assert "hooksEnabled()" in block
        assert "ctxEnabled()" in block
        assert 'process.env.SCHOOL_COMPRESS === "0"' in block

    def test_apply_view_is_timeboxed(self) -> None:
        assert "const VIEW_TIMEOUT_MS = 4000" in TS_PLUGIN_SOURCE
        block = self._block("applyView")
        assert "VIEW_TIMEOUT_MS" in block

    def test_apply_view_sends_context_view_command(self) -> None:
        block = self._block("applyView")
        assert 'command: "context_view"' in block
        assert "messages: plain" in block
        assert 'session: String(messages[0]?.info?.sessionID ?? "")' in block

    def test_apply_view_fails_open(self) -> None:
        block = self._block("applyView")
        assert "try {" in block
        assert "catch" in block
        assert "if (!resp.ok) return" in block
        assert "if (!bridge" in block

    def test_apply_view_rebuilds_from_originals(self) -> None:
        block = self._block("applyView")
        assert "if (edit && edit.content === null) continue" in block
        assert "rebuilt.push(src)" in block
        assert "synthetic: true" in block
        assert "output.messages = rebuilt" in block

    def test_apply_view_stores_footer_chip(self) -> None:
        block = self._block("applyView")
        assert "schoolStatus.chip = chip" in block

    def test_view_text_of_prefers_text_parts(self) -> None:
        match = re.search(
            r"function viewTextOf\([\s\S]*?\n\}", TS_PLUGIN_SOURCE
        )
        assert match is not None
        assert 'p.type === "text"' in match.group(0)
        assert "info?.content" in match.group(0)

    def test_mode_gate_skips_when_not_school(self) -> None:
        block = self._block("applyView")
        assert 'if (mode !== "school") return' in block
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `& ".venv\Scripts\python.exe" -m pytest -q --no-header -p no:cacheprovider tests/unit/test_school_plugin_hooks.py`
Expected: FAIL — new `TestApplyView` tests fail (`const applyView = async` not found); all pre-existing tests still pass.

- [ ] **Step 3: Implement apply-view in `school/plugin_source.py`**

3a. Module scope — add right after the `HOOK_*` constants block (after `const HOOK_BUDGET = 400`):

```ts
const VIEW_TIMEOUT_MS = 4000
```

3b. Module scope — add `viewTextOf` right after the `strList` function (after line `function strList(...)`):

```ts
function viewTextOf(m: any): string {
  const parts = Array.isArray(m?.parts) ? m.parts : []
  const text = parts
    .filter((p: any) => p && p.type === "text")
    .map((p: any) => String(p.text ?? ""))
    .join("\n")
  return text || String(m?.info?.content ?? "")
}
```

3c. School closure — insert `applyView` immediately after the `recallForExecution` definition (before `interface RouteDecision`):

```ts
  const applyView = async (output: any): Promise<void> => {
    try {
      if (!hooksEnabled() || !ctxEnabled()) return
      if (process.env.SCHOOL_COMPRESS === "0") return
      if (!bridge || !output || !Array.isArray(output.messages)) return
      const messages = output.messages
      if (!messages.length) return
      const plain = messages.map((m: any) => ({
        role: String(m?.info?.role ?? "user"),
        content: viewTextOf(m),
      }))
      const resp = await invokeBridge(
        python,
        bridgePath,
        {
          command: "context_view",
          worktree: ctx.worktree,
          session: String(messages[0]?.info?.sessionID ?? ""),
          messages: plain,
        },
        VIEW_TIMEOUT_MS,
      )
      if (!resp.ok) return
      schoolStatus.chip = String((resp as any).chip ?? "")
      const mode = String((resp as any).mode ?? "")
      if (mode !== "school") return
      const raw = (resp as any).segments
      const segs = Array.isArray(raw) ? raw : []
      if (!segs.length) return
      const edits = new Map<number, any>()
      for (const seg of segs) edits.set(Number(seg.index), seg)
      const rebuilt: any[] = []
      for (let i = 0; i < messages.length; i++) {
        const edit = edits.get(i)
        if (edit && edit.content === null) continue
        const src = messages[i]
        if (!edit) {
          rebuilt.push(src)
          continue
        }
        const role = String(edit.role ?? "")
        const info =
          role && role !== src?.info?.role
            ? { ...src?.info, role }
            : src?.info
        rebuilt.push({
          info,
          parts: [{
            id: `school-view-${src?.info?.id ?? i}`,
            sessionID: src?.info?.sessionID,
            messageID: src?.info?.id,
            type: "text",
            synthetic: true,
            text: String(edit.content ?? ""),
          }],
        })
      }
      output.messages = rebuilt
    } catch {
      // Apply-view is best-effort; failures leave messages untouched.
    }
  }
```

3d. Restructure the transform hook so apply-view runs before the recall injection's early returns. Replace the whole existing `"experimental.chat.messages.transform"` block with:

```ts
    "experimental.chat.messages.transform": async (_input, output) => {
      try {
        await applyView(output)
        const messages = output.messages ?? []
        if (!messages.length) return
        const last = messages[messages.length - 1]
        const info: any = last.info
        if (!info || info.role !== "user" || !info.sessionID) return
        const rec = promptRecalls.get(info.sessionID)
        if (!rec) return
        promptRecalls.delete(info.sessionID)
        last.parts.push({
          id: `school-context-${info.id}`,
          sessionID: info.sessionID,
          messageID: info.id,
          type: "text",
          synthetic: true,
          text: `[school context]\n${rec.lines.join("\n")}\n[/school]`,
        })
      } catch {
        // Context injection and apply-view are best-effort.
      }
    },
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `& ".venv\Scripts\python.exe" -m pytest -q --no-header -p no:cacheprovider tests/unit/test_school_plugin_hooks.py`
Expected: all passed (old + new)

- [ ] **Step 5: Live TS syntax/regression gate**

Run: `& ".venv\Scripts\python.exe" -m pytest -q --no-header -p no:cacheprovider tests/integration/test_plugin_live.py`
Expected: all passed — the harness compiles and runs the real TS through node (this is the TS syntax check; `node --check` cannot parse TypeScript).

- [ ] **Step 6: Ruff (E501 budget!)**

Run: `& ".venv\Scripts\python.exe" -m ruff check school/plugin_source.py`
Expected: **16 errors** (exactly the baseline — every new TS line must be ≤ 100 chars; if 17+, find the long line and wrap it).

---

### Task 4: Plugin DCP coexistence (detect → quiet offer → ownership gate)

**Files:**
- Edit: `school/plugin_source.py` (module `DCP_TOKEN`, School-closure coexist state + `checkCoexist`, `applyView` wiring)
- Test: append `class TestDcpCoexist` to `tests/unit/test_school_plugin_hooks.py`

**Interfaces:**
- Produces (TS, inside the School closure): module `const DCP_TOKEN = "@tarquinen/opencode-dcp"`; closure state `let coexistDone = false` / `let dcpHinted = false`; `const checkCoexist = async (): Promise<void>` which calls bridge `context_coexist` (`action: "get"`, then one-time `action: "set_offer"` + `client.tui.showToast` with the offer); `applyView` now awaits `checkCoexist()` before requesting `context_view` and forwards `dcp: dcpHinted` on that request.
- Consumes: bridge `context_coexist` + `OFFER_TEXT` (Task 2), `applyView` (Task 3). Fail-open: any coexist error leaves the view request and messages untouched; coexist runs at most once per process (`coexistDone`); `SCHOOL_HOOKS=0` / `SCHOOL_CTX=0` / `SCHOOL_COMPRESS=0` all disable it.

- [ ] **Step 1: Write the failing tests**

Append at the END of `tests/unit/test_school_plugin_hooks.py`:

```python
class TestDcpCoexist:
    """DCP coexistence in the plugin: detect, one quiet offer, ownership gate."""

    def _block(self, name: str) -> str:
        match = re.search(
            rf"const {name} = async \([\s\S]*?\n  \}}", TS_PLUGIN_SOURCE
        )
        assert match is not None, f"const {name} not found"
        return match.group(0)

    def test_dcp_token_constant(self) -> None:
        assert 'const DCP_TOKEN = "@tarquinen/opencode-dcp"' in TS_PLUGIN_SOURCE

    def test_check_coexist_talks_to_bridge(self) -> None:
        block = self._block("checkCoexist")
        assert 'command: "context_coexist"' in block
        assert 'action: "get"' in block
        assert 'action: "set_offer"' in block

    def test_check_coexist_gates_kill_switches(self) -> None:
        block = self._block("checkCoexist")
        assert "hooksEnabled()" in block
        assert "ctxEnabled()" in block
        assert 'process.env.SCHOOL_COMPRESS === "0"' in block

    def test_check_coexist_runs_once_and_fails_open(self) -> None:
        block = self._block("checkCoexist")
        assert "coexistDone = true" in block
        assert "try {" in block
        assert "catch" in block

    def test_dcp_hint_probed_from_client_config(self) -> None:
        block = self._block("checkCoexist")
        assert "client?.config?.get?.()" in block
        assert "dcpHinted = plugins.some(" in block
        assert "DCP_TOKEN" in block

    def test_offer_is_one_quiet_toast(self) -> None:
        block = self._block("checkCoexist")
        assert "showToast" in block
        assert "offer_shown" in block

    def test_apply_view_runs_gate_before_view_request(self) -> None:
        block = self._block("applyView")
        assert "await checkCoexist()" in block
        assert block.index("await checkCoexist()") < block.index(
            'command: "context_view"'
        )

    def test_apply_view_forwards_dcp_hint(self) -> None:
        block = self._block("applyView")
        assert "dcp: dcpHinted" in block
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `& ".venv\Scripts\python.exe" -m pytest -q --no-header -p no:cacheprovider tests/unit/test_school_plugin_hooks.py`
Expected: FAIL — the new `TestDcpCoexist` tests fail (`const checkCoexist not found`); all pre-existing tests still pass.

- [ ] **Step 3: Implement DCP coexistence in `school/plugin_source.py`**

3a. Module scope — add right after the line `const VIEW_TIMEOUT_MS = 4000`:

```ts
const DCP_TOKEN = "@tarquinen/opencode-dcp"
```

3b. School closure — insert immediately before the line `const applyView = async (output: any): Promise<void> => {`:

```ts
  let coexistDone = false
  let dcpHinted = false

  const checkCoexist = async (): Promise<void> => {
    if (coexistDone) return
    if (!bridge || !hooksEnabled() || !ctxEnabled()) return
    if (process.env.SCHOOL_COMPRESS === "0") return
    coexistDone = true
    try {
      if (!dcpHinted) {
        const cfg: any = await (ctx as any).client?.config?.get?.()
        const plugins = Array.isArray(cfg?.plugin) ? cfg.plugin : []
        dcpHinted = plugins.some(
          (p: any) => JSON.stringify(p).includes(DCP_TOKEN),
        )
      }
      const resp = await invokeBridge(
        python,
        bridgePath,
        {
          command: "context_coexist",
          worktree: ctx.worktree,
          action: "get",
          dcp: dcpHinted,
        },
        VIEW_TIMEOUT_MS,
      )
      if (!resp.ok) return
      const info = resp as any
      if (!info.dcp || info.offer_shown) return
      const shown = await invokeBridge(
        python,
        bridgePath,
        {
          command: "context_coexist",
          worktree: ctx.worktree,
          action: "set_offer",
          dcp: dcpHinted,
        },
        VIEW_TIMEOUT_MS,
      )
      if (!shown.ok) return
      const offer = String(info.offer ?? "")
      if (offer) {
        try {
          (ctx as any).client?.tui?.showToast?.({
            message: offer,
            variant: "info",
          })
        } catch {
          // Toasts are best-effort.
        }
      }
    } catch {
      // Coexistence checks are best-effort.
    }
  }
```

3c. `applyView` wiring — two edits inside the existing `applyView` body:

- After the line `      if (!bridge || !output || !Array.isArray(output.messages)) return` insert:
```ts
      await checkCoexist()
```
- Inside the `context_view` request object, after the `session:` line, insert:
```ts
          dcp: dcpHinted,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `& ".venv\Scripts\python.exe" -m pytest -q --no-header -p no:cacheprovider tests/unit/test_school_plugin_hooks.py`
Expected: all passed (old + new)

- [ ] **Step 5: Live TS syntax/regression gate**

Run: `& ".venv\Scripts\python.exe" -m pytest -q --no-header -p no:cacheprovider tests/integration/test_plugin_live.py`
Expected: all passed — the load-time config probe is optional-chained (`ctx.client` is undefined in the harness) and fails open.

- [ ] **Step 6: Ruff (E501 budget!)**

Run: `& ".venv\Scripts\python.exe" -m ruff check school/plugin_source.py`
Expected: **16 errors** (exactly the baseline — every new TS line must be ≤ 100 chars; if 17+, find the long line and wrap it).

Run: `& ".venv\Scripts\python.exe" -m ruff check tests/unit/test_school_plugin_hooks.py`
Expected: All checks passed!

---

### Task 5: MCP 3-tool mirror + TS tools (`school_context_*`)

**Files:**
- Modify: `school/mcp/server.py` (append 3 entries to `_TOOLS`)
- Modify: `school/plugin_source.py` (append 3 TS tool blocks)
- Modify: `tests/unit/test_school_plugin_hooks.py` (tool count 26 → 29)
- Modify: `tests/unit/test_school_plugin_bridge.py` (tool list + count 26 → 29)
- Modify: `tests/unit/test_mcp_server.py` (`EXPECTED_TOOL_ORDER` + annotations set + new class at END)
- Modify: `tests/integration/test_mcp_stdio.py` (`EXPECTED_TOOLS` + 3)
- Test: new `class TestContextToolsMCP` at END of `tests/unit/test_mcp_server.py`; new `class TestContextToolsTS` at END of `tests/unit/test_school_plugin_bridge.py`

**Interfaces:**
- Produces MCP tools: `school_context_status` (annotations `read_only_hint` + `idempotent_hint`), `school_context_compress` (no annotations), `school_context_restore` (annotation `idempotent_hint` only). All three dispatch through `_call_tool` → `_build_request` → `_bridge_call(name.removeprefix("school_"))` → bridge commands from Task 2 — zero new dispatch code. Schemas: all take optional `session`; compress takes `messages` (array of `{role, content}`); restore takes `block_id`.
- Produces TS tools: `school_context_status` / `school_context_compress` / `school_context_restore`, registered in the plugin `tool:` object right after `school_skill_import` (tool surface 26 → 29). Descriptions are **byte-identical** between `_TOOLS` and the TS blocks (existing parity test enforces this).

- [ ] **Step 1: Write the failing tests (list updates + new classes)**

1a. `tests/unit/test_school_plugin_hooks.py` — replace the `test_tool_surface_unchanged` body:

```python
    def test_tool_surface_unchanged(self) -> None:
        """The tool surface: 26 approved tools + three S2 context mirrors."""
        names = re.findall(r"^\s+(school_\w+): tool\(", TS_PLUGIN_SOURCE, re.MULTILINE)
        assert len(names) == 29, f"tool surface changed: {names}"
```

1b. `tests/unit/test_school_plugin_bridge.py` — append to `EXPECTED_OPENCODE_TOOLS` (after `"school_skill_import",`):

```python
    "school_context_status",
    "school_context_compress",
    "school_context_restore",
```

and update the surface test (docstring, name, count):

```python
    """The plugin must expose exactly the approved 29-tool surface."""

    def test_exposes_exactly_29_tools(self) -> None:
        names = _tool_names()
        assert len(names) == 29, f"expected 29 tools, got {len(names)}: {names}"
        assert set(names) == set(EXPECTED_OPENCODE_TOOLS)
```

1c. `tests/unit/test_mcp_server.py` — append to `EXPECTED_TOOL_ORDER` (after `"school_skill_import",`):

```python
    "school_context_status",
    "school_context_compress",
    "school_context_restore",
```

and add `"school_context_status",` to the `read_only` set in `test_read_only_annotations` (after `"school_skill_compare",`).

1d. `tests/integration/test_mcp_stdio.py` — append the same three names to `EXPECTED_TOOLS` (after `"school_skill_import",`).

1e. Append at the END of `tests/unit/test_mcp_server.py`:

```python
class TestContextToolsMCP:
    """The three context mirror tools over MCP (S2)."""

    def test_status_reports_mode_and_blocks(self, worktree: str) -> None:
        result = mcp_server._call_tool(worktree, "school_context_status", {})
        assert result.is_error is False
        payload = json.loads(result.content[0].text)
        assert payload["ok"] is True
        assert payload["mode"] == "school"
        assert payload["blocks"] == 0
        assert "chip" in payload
        assert result.structured_content == payload

    def test_compress_then_status_chip(
        self, worktree: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SCHOOL_COMPRESS_WINDOW_TOKENS", "200")
        monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
        messages = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": chr(97 + i) * 300}
            for i in range(8)
        ]
        done = mcp_server._call_tool(
            worktree, "school_context_compress", {"messages": messages}
        )
        assert json.loads(done.content[0].text)["blocks_added"] >= 1
        status = mcp_server._call_tool(worktree, "school_context_status", {})
        payload = json.loads(status.content[0].text)
        assert payload["blocks"] >= 1
        assert payload["chip"].startswith("[school] compacted")

    def test_restore_roundtrip_is_idempotent(
        self, worktree: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SCHOOL_COMPRESS_WINDOW_TOKENS", "200")
        monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
        messages = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": chr(97 + i) * 300}
            for i in range(8)
        ]
        mcp_server._call_tool(
            worktree, "school_context_compress", {"messages": messages}
        )
        results = []
        for _ in range(2):
            result = mcp_server._call_tool(
                worktree, "school_context_restore", {"block_id": ""}
            )
            results.append(json.loads(result.content[0].text))
        assert all(r["ok"] for r in results), results
        assert results[0]["restores"] >= 1

    def test_unknown_arguments_are_filtered(self, worktree: str) -> None:
        result = mcp_server._call_tool(
            worktree, "school_context_status", {"bogus": 1}
        )
        assert result.is_error is False
        assert json.loads(result.content[0].text)["ok"] is True

    def test_annotations_match_surface(self) -> None:
        tools = {t.name: t for t in mcp_server._list_tools().tools}
        status = tools["school_context_status"].annotations
        assert status.read_only_hint is True
        assert status.idempotent_hint is True
        restore = tools["school_context_restore"].annotations
        assert restore.read_only_hint is None
        assert restore.idempotent_hint is True
        assert tools["school_context_compress"].annotations is None
```

1f. Append at the END of `tests/unit/test_school_plugin_bridge.py`:

```python
class TestContextToolsTS:
    """The three context tools on the OpenCode plugin surface (S2)."""

    def test_status_sends_context_status(self) -> None:
        block = _tool_block("school_context_status")
        assert 'command: "context_status"' in block
        assert "School Context Status" in block
        assert "if (!bridge)" in block

    def test_compress_sends_context_compress(self) -> None:
        block = _tool_block("school_context_compress")
        assert 'command: "context_compress"' in block
        assert "messages: args.messages ?? []" in block

    def test_restore_sends_context_restore(self) -> None:
        block = _tool_block("school_context_restore")
        assert 'command: "context_restore"' in block
        assert 'block_id: args.block_id ?? ""' in block

    def test_context_descriptions_match_mcp(self) -> None:
        from school.mcp import server as mcp_server

        for name in (
            "school_context_status",
            "school_context_compress",
            "school_context_restore",
        ):
            block = _tool_block(name)
            match = re.search(r"description:\s*\n(.*?),\n\s*args:", block, re.S)
            assert match, name
            ts_desc = "".join(re.findall(r'"([^"]*)"', match.group(1)))
            assert ts_desc == mcp_server._TOOLS[name]["description"], name
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `& ".venv\Scripts\python.exe" -m pytest -q --no-header -p no:cacheprovider tests/unit/test_school_plugin_hooks.py tests/unit/test_school_plugin_bridge.py tests/unit/test_mcp_server.py tests/integration/test_mcp_stdio.py`
Expected: FAIL — tool counts still 26/28, `no TS description block for 'school_context_status'`, `KeyError`/missing entries for the new MCP tools; all other tests still pass.

- [ ] **Step 3: Add the three MCP entries**

In `school/mcp/server.py`, append after the `school_skill_import` entry (before the closing `}` of `_TOOLS`):

```python
    "school_context_status": {
        "description": (
            "Use school_context_status to report the School context engine: "
            "blocks stored, restores, tokens saved, view mode (school|dcp|off), "
            "DCP decision, and a chip one-liner. Read-only - call before "
            "compress or restore."
        ),
        "annotations": {"read_only_hint": True, "idempotent_hint": True},
        "schema": {
            "type": "object",
            "properties": {
                "session": {
                    "type": "string",
                    "description": "Session id for scope isolation.",
                },
            },
        },
    },
    "school_context_compress": {
        "description": (
            "Use school_context_compress to compress session messages through "
            "the School context engine, returning blocks added, tokens saved, "
            "and a chip. Explicit action only - never automatic; "
            "SCHOOL_COMPRESS=0 disables it."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "session": {
                    "type": "string",
                    "description": "Session id for scope isolation.",
                },
                "messages": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Session messages to compress: [{role, content}].",
                },
            },
        },
    },
    "school_context_restore": {
        "description": (
            "Use school_context_restore to restore compressed blocks by "
            "block_id (empty id restores all) - idempotent, returning restores "
            "count, store state, and a chip. Call school_context_status first "
            "to list block ids."
        ),
        "annotations": {"idempotent_hint": True},
        "schema": {
            "type": "object",
            "properties": {
                "session": {
                    "type": "string",
                    "description": "Session id for scope isolation.",
                },
                "block_id": {
                    "type": "string",
                    "description": "Block id to restore (empty = restore all).",
                },
            },
        },
    },
```

- [ ] **Step 4: Add the three TS tool blocks**

In `school/plugin_source.py`, insert after the `school_skill_import` block (still inside the `tool: { ... }` object, before its closing `    },`):

```ts
      school_context_status: tool({
        description:
          "Use school_context_status to report the School context engine: " +
          "blocks stored, restores, tokens saved, view mode (school|dcp|off), " +
          "DCP decision, and a chip one-liner. Read-only - call before " +
          "compress or restore.",
        args: {
          session: tool.schema
            .string()
            .optional()
            .describe("Session id for scope isolation."),
        },
        async execute(args, context) {
          if (!bridge) {
            return {
              title: "School Context Status",
              output: "School: unavailable.",
            }
          }
          const resp = await invokeBridge(python, bridgePath, {
            command: "context_status",
            worktree: context.worktree,
            session: args.session,
          })
          if (!resp.ok) {
            const msg = (resp as any).error?.message ?? "failed"
            return {
              title: "School Context Status - Failed",
              output: `Error: ${msg}`,
            }
          }
          return {
            title: "School Context Status",
            output: JSON.stringify(resp, null, 2),
            metadata: resp,
          }
        },
      }),

      school_context_compress: tool({
        description:
          "Use school_context_compress to compress session messages through " +
          "the School context engine, returning blocks added, tokens saved, " +
          "and a chip. Explicit action only - never automatic; " +
          "SCHOOL_COMPRESS=0 disables it.",
        args: {
          session: tool.schema
            .string()
            .optional()
            .describe("Session id for scope isolation."),
          messages: tool.schema
            .array(tool.schema.any())
            .optional()
            .describe("Session messages to compress: [{role, content}]."),
        },
        async execute(args, context) {
          if (!bridge) {
            return {
              title: "School Context Compress",
              output: "School: unavailable.",
            }
          }
          const resp = await invokeBridge(python, bridgePath, {
            command: "context_compress",
            worktree: context.worktree,
            session: args.session,
            messages: args.messages ?? [],
          })
          if (!resp.ok) {
            const msg = (resp as any).error?.message ?? "failed"
            return {
              title: "School Context Compress - Failed",
              output: `Error: ${msg}`,
            }
          }
          return {
            title: "School Context Compress",
            output: JSON.stringify(resp, null, 2),
            metadata: resp,
          }
        },
      }),

      school_context_restore: tool({
        description:
          "Use school_context_restore to restore compressed blocks by " +
          "block_id (empty id restores all) - idempotent, returning restores " +
          "count, store state, and a chip. Call school_context_status first " +
          "to list block ids.",
        args: {
          session: tool.schema
            .string()
            .optional()
            .describe("Session id for scope isolation."),
          block_id: tool.schema
            .string()
            .optional()
            .describe("Block id to restore (empty = restore all)."),
        },
        async execute(args, context) {
          if (!bridge) {
            return {
              title: "School Context Restore",
              output: "School: unavailable.",
            }
          }
          const resp = await invokeBridge(python, bridgePath, {
            command: "context_restore",
            worktree: context.worktree,
            session: args.session,
            block_id: args.block_id ?? "",
          })
          if (!resp.ok) {
            const msg = (resp as any).error?.message ?? "failed"
            return {
              title: "School Context Restore - Failed",
              output: `Error: ${msg}`,
            }
          }
          const result = (resp as any).result ?? resp
          return {
            title: "School Context Restore",
            output: JSON.stringify(result, null, 2),
            metadata: result,
          }
        },
      }),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `& ".venv\Scripts\python.exe" -m pytest -q --no-header -p no:cacheprovider tests/unit/test_school_plugin_hooks.py tests/unit/test_school_plugin_bridge.py tests/unit/test_mcp_server.py tests/integration/test_mcp_stdio.py`
Expected: all passed (old + new; this also runs the byte-equal TS/MCP description parity test)

- [ ] **Step 6: Live TS registration gate**

Run: `& ".venv\Scripts\python.exe" -m pytest -q --no-header -p no:cacheprovider tests/integration/test_plugin_live.py`
Expected: all passed — the three new tool blocks evaluate through the stubbed `tool.schema` proxy at `School()` load.

- [ ] **Step 7: Ruff (E501 budget!)**

Run: `& ".venv\Scripts\python.exe" -m ruff check school/mcp/server.py tests/unit/test_mcp_server.py tests/unit/test_school_plugin_bridge.py tests/unit/test_school_plugin_hooks.py tests/integration/test_mcp_stdio.py`
Expected: All checks passed!

Run: `& ".venv\Scripts\python.exe" -m ruff check school/plugin_source.py`
Expected: **16 errors** (unchanged baseline)

---

### Task 6: `school context` CLI

**Files:**
- Modify: `school/cli.py` (`_read_messages`, `_cmd_context`, `context` subparsers, `commands` dict entry)
- Modify: `tests/unit/test_cli.py` (import `StringIO`, append `class TestContextCommand`, fix 1 pre-existing E501)
- Test: append `class TestContextCommand` at END of `tests/unit/test_cli.py`

**Interfaces:**
- Produces: CLI `school context {status,compress,restore,switch,keep}` — every subcommand accepts `--json` (raw bridge JSON), `--session`, `--worktree` (default: cwd). `compress` reads a JSON array of messages from stdin; `restore [block_id]` (default: all); `switch`/`keep` → bridge `context_coexist` `set_decision` (the exact commands `OFFER_TEXT` tells users to run). Human output prints the chip line and, when DCP is present undecided, the offer.
- Consumes: bridge `context_status|compress|restore|coexist` (Task 2) dispatched **in-process** via `school.bridge._COMMANDS` — same pattern as the MCP server. `switch`/`keep` exit 0 even when no DCP is detected (decision is recorded; clean break on `switch`).

- [ ] **Step 1: Write the failing tests**

1a. In `tests/unit/test_cli.py`, extend the top imports (after `from pathlib import Path`):

```python
from io import StringIO
```

1b. Append at the END of `tests/unit/test_cli.py`:

```python
class TestContextCommand:
    """S2 Task 6: `school context` subcommands over the in-process bridge."""

    def _compress(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> dict:
        monkeypatch.setenv("SCHOOL_COMPRESS_WINDOW_TOKENS", "200")
        monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
        messages = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": chr(97 + i) * 300}
            for i in range(8)
        ]
        argv = ["school", "context", "compress", "--json", "--worktree", str(tmp_path)]
        with (
            patch("sys.argv", argv),
            patch("school.cli.SchoolConfig"),
            patch("sys.stdin", StringIO(json.dumps(messages))),
        ):
            main()
        return json.loads(capsys.readouterr().out)

    def test_status_json(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        argv = ["school", "context", "status", "--json", "--worktree", str(tmp_path)]
        with patch("sys.argv", argv), patch("school.cli.SchoolConfig"):
            main()
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True
        assert payload["mode"] == "school"
        assert payload["blocks"] == 0
        assert "chip" in payload

    def test_missing_subcommand_exits(self) -> None:
        with (
            patch("sys.argv", ["school", "context"]),
            patch("school.cli.SchoolConfig"),
            pytest.raises(SystemExit) as excinfo,
        ):
            main()
        assert excinfo.value.code == 2

    def test_switch_and_keep_persist(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        for decision in ("switch", "keep"):
            argv = ["school", "context", decision, "--json", "--worktree", str(tmp_path)]
            with patch("sys.argv", argv), patch("school.cli.SchoolConfig"):
                main()
            payload = json.loads(capsys.readouterr().out)
            assert payload["ok"] is True
            assert payload["decision"] == decision
        argv = ["school", "context", "status", "--json", "--worktree", str(tmp_path)]
        with patch("sys.argv", argv), patch("school.cli.SchoolConfig"):
            main()
        assert json.loads(capsys.readouterr().out)["decision"] == "keep"

    def test_compress_reads_messages_from_stdin(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        payload = self._compress(tmp_path, monkeypatch, capsys)
        assert payload["ok"] is True
        assert payload["blocks_added"] >= 1
        assert payload["chip"].startswith("[school] compacted")

    def test_restore_roundtrip_is_idempotent(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._compress(tmp_path, monkeypatch, capsys)
        results = []
        for _ in range(2):
            argv = ["school", "context", "restore", "--json", "--worktree", str(tmp_path)]
            with patch("sys.argv", argv), patch("school.cli.SchoolConfig"):
                main()
            results.append(json.loads(capsys.readouterr().out))
        assert all(r["ok"] for r in results), results
        assert results[0]["restores"] >= 1

    def test_status_human_prints_dcp_offer(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / "opencode.json").write_text(
            json.dumps({"plugin": ["@tarquinen/opencode-dcp"]}),
            encoding="utf-8",
        )
        argv = ["school", "context", "status", "--worktree", str(tmp_path)]
        with patch("sys.argv", argv), patch("school.cli.SchoolConfig"):
            main()
        out = capsys.readouterr().out
        assert "mode: dcp" in out
        assert "Keep DCP, or switch?" in out
        assert "school context switch" in out

    def test_status_human_prints_chip(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._compress(tmp_path, monkeypatch, capsys)
        argv = ["school", "context", "status", "--worktree", str(tmp_path)]
        with patch("sys.argv", argv), patch("school.cli.SchoolConfig"):
            main()
        out = capsys.readouterr().out
        assert "[school] compacted" in out
        assert "blocks: " in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `& ".venv\Scripts\python.exe" -m pytest -q --no-header -p no:cacheprovider tests/unit/test_cli.py`
Expected: FAIL — argparse rejects `context` as an invalid choice (`SystemExit: 2`); `test_missing_subcommand_exits` may already pass (same exit code). All pre-existing tests still pass.

- [ ] **Step 3: Implement `school context` in `school/cli.py`**

3a. Insert after the end of `_cmd_skills` (immediately before `def main()`):

```python
def _read_messages() -> list[dict]:
    """Read a JSON array of messages from stdin (empty when unavailable)."""
    import json

    try:
        if sys.stdin is None or sys.stdin.isatty():
            return []
        data = json.load(sys.stdin)
    except (ValueError, OSError):
        return []
    return data if isinstance(data, list) else []


def _cmd_context(args: argparse.Namespace) -> None:
    """school context: status | compress | restore | switch | keep."""
    import json

    from school import bridge

    action = args.context_command
    if action is None:
        print("school context: missing subcommand", file=sys.stderr)
        sys.exit(2)

    worktree = args.worktree or str(Path.cwd())
    command = "context_status"
    req: dict = {"worktree": worktree}
    if args.session:
        req["session"] = args.session
    if action == "compress":
        command = "context_compress"
        req["messages"] = _read_messages()
    elif action == "restore":
        command = "context_restore"
        req["block_id"] = args.block_id or ""
    elif action in ("switch", "keep"):
        command = "context_coexist"
        req["action"] = "set_decision"
        req["decision"] = action

    handler = bridge._COMMANDS.get(command)
    if handler is None:
        resp = {
            "ok": False,
            "error": {"type": "protocol", "message": f"unknown: {command}"},
        }
    else:
        resp = handler(req)

    if args.json:
        print(json.dumps(resp, ensure_ascii=False))
    elif action == "status":
        print(f"mode: {resp.get('mode', '?')}")
        print(f"decision: {resp.get('decision') or '-'}")
        blocks = resp.get("blocks", 0)
        restores = resp.get("restores", 0)
        print(f"blocks: {blocks}  restores: {restores}")
        if resp.get("chip"):
            print(resp["chip"])
        if resp.get("dcp") and not resp.get("decision"):
            from core.context.coexist import OFFER_TEXT

            print(OFFER_TEXT)
    else:
        print(f"ok: {resp.get('ok')}  mode: {resp.get('mode', '')}")
        if resp.get("chip"):
            print(resp["chip"])
    if not resp.get("ok"):
        sys.exit(1)
```

3b. In `main()`, insert the subparser registration after the `import_parser` argument block (immediately before `args = parser.parse_args()`):

```python
    context_common = argparse.ArgumentParser(add_help=False)
    context_common.add_argument(
        "--json", action="store_true", help="Print the raw bridge JSON response"
    )
    context_common.add_argument("--session", default="", help="Session id")
    context_common.add_argument(
        "--worktree", default="", help="Worktree root (default: current directory)"
    )

    context_parser = subparsers.add_parser(
        "context",
        help="Context engine: status, compress, restore, switch, keep",
    )
    context_subparsers = context_parser.add_subparsers(dest="context_command")
    context_subparsers.add_parser(
        "status",
        parents=[context_common],
        help="Blocks, view mode, chip, DCP offer",
    )
    context_subparsers.add_parser(
        "compress",
        parents=[context_common],
        help="Compress messages read as a JSON array from stdin",
    )
    restore_parser = context_subparsers.add_parser(
        "restore",
        parents=[context_common],
        help="Restore blocks by id (default: all)",
    )
    restore_parser.add_argument(
        "block_id", nargs="?", default="", help="Block id to restore"
    )
    context_subparsers.add_parser(
        "switch",
        parents=[context_common],
        help="School owns compression from now on (clean break)",
    )
    context_subparsers.add_parser(
        "keep",
        parents=[context_common],
        help="Keep DCP for message-level compression",
    )
```

3c. Add the dispatch entry in the `commands` dict (after `"skills": _cmd_skills,`):

```python
        "context": _cmd_context,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `& ".venv\Scripts\python.exe" -m pytest -q --no-header -p no:cacheprovider tests/unit/test_cli.py`
Expected: all passed (old + new)

- [ ] **Step 5: Fix the pre-existing lint errors in `tests/unit/test_cli.py`**

The file enters this task with 2 pre-existing ruff errors; both must end green:

- `import json` becomes used by the new tests (no action needed).
- Wrap the over-long signature (line ~55):

```python
    def test_install_skip_existing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
```

Run: `& ".venv\Scripts\python.exe" -m ruff check school/cli.py tests/unit/test_cli.py`
Expected: All checks passed!

- [ ] **Step 6: Regression**

Run: `& ".venv\Scripts\python.exe" -m pytest -q --no-header -p no:cacheprovider tests/unit/test_cli.py tests/unit/test_bridge_context.py`
Expected: all passed

---

### Task 7: Chip rendering across surfaces (`emit_chip`)

**Files:**
- Modify: `school/plugin_source.py` (`experimental.text.complete` appends the stored chip line)
- Create: `tests/unit/test_context_chip_wiring.py`

**Interfaces:**
- Produces: footer wire format — after the existing status line, one extra raw line `schoolStatus.chip` (e.g. `[school] ctx 62% · −18.4k tok`) whenever Task 3's `applyView` stored a chip; idempotency guard unchanged. Chips on bridge/MCP/CLI already flow from Task 2/5 (`chip` key in every context response) — this task pins the voice contract with tests and renders the footer chip.
- Consumes: `core.context.build_chip` (S1), `schoolStatus.chip` (Task 3), context responses with `chip` (Task 2/5). Voice (spec §6): one calm monospace line, middle-dot segments, **no `$` in S2** (`spend_usd` is S3).

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_context_chip_wiring.py`:

```python
"""S2 Task 7: Apple-grade chip voice across bridge, MCP, and the footer."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from core.context import build_chip
from school import bridge
from school.plugin_source import TS_PLUGIN_SOURCE


def big_msgs(n: int = 8) -> list[dict]:
    return [
        {"role": "user" if i % 2 == 0 else "assistant", "content": chr(97 + i) * 300}
        for i in range(n)
    ]


class TestChipVoice:
    """Spec §6 chip voice: calm, sparse, middle-dot segments."""

    def test_ctx_chip_matches_spec(self) -> None:
        assert build_chip(used_ratio=0.62, saved_tokens=18400) == (
            "[school] ctx 62% · −18.4k tok"
        )

    def test_compacted_chip_matches_spec(self) -> None:
        assert build_chip(blocks_added=2, restores=1) == (
            "[school] compacted 2 blocks · restorable · 1 restored"
        )

    def test_silence_without_data(self) -> None:
        assert build_chip() == ""

    def test_no_dollar_in_s2(self) -> None:
        for chip in (
            build_chip(used_ratio=0.5),
            build_chip(used_ratio=0.5, saved_tokens=100),
            build_chip(blocks_added=1),
        ):
            assert "$" not in chip


class TestBridgeChip:
    """Bridge context responses carry the chip (Tasks 2/5/6 rely on this)."""

    def test_compress_and_status_chips(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SCHOOL_COMPRESS_WINDOW_TOKENS", "200")
        monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
        wt = str(tmp_path)
        resp = bridge._COMMANDS["context_compress"](
            {"worktree": wt, "session": "chip1", "messages": big_msgs()}
        )
        assert resp["chip"].startswith("[school] compacted")
        status = bridge._COMMANDS["context_status"](
            {"worktree": wt, "session": "chip1"}
        )
        assert status["chip"].startswith("[school] compacted")

    def test_view_chip_is_ctx_voice(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SCHOOL_COMPRESS_WINDOW_TOKENS", "200")
        monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
        wt = str(tmp_path)
        bridge._COMMANDS["context_compress"](
            {"worktree": wt, "session": "chip2", "messages": big_msgs()}
        )
        view = bridge._COMMANDS["context_view"](
            {"worktree": wt, "session": "chip2", "messages": big_msgs()}
        )
        assert view["chip"].startswith("[school] ctx")


class TestMcpChip:
    """MCP surfaces expose the same chip field byte-for-byte."""

    def test_status_tool_returns_chip(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from school.mcp import server as mcp_server

        monkeypatch.setenv("SCHOOL_COMPRESS_WINDOW_TOKENS", "200")
        monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
        wt = str(tmp_path)
        mcp_server._call_tool(
            wt, "school_context_compress", {"messages": big_msgs()}
        )
        result = mcp_server._call_tool(wt, "school_context_status", {})
        payload = json.loads(result.content[0].text)
        assert payload["chip"].startswith("[school] compacted")


class TestFooterChipWiring:
    """Footer chip: applyView stores it, text.complete renders it."""

    def _apply_view_block(self) -> str:
        match = re.search(
            r"const applyView = async \([\s\S]*?\n  \}", TS_PLUGIN_SOURCE
        )
        assert match is not None, "applyView not found"
        return match.group(0)

    def _complete_block(self) -> str:
        match = re.search(
            r'"experimental\.text\.complete": async \([\s\S]*?\n    \},',
            TS_PLUGIN_SOURCE,
        )
        assert match is not None, "text.complete hook not found"
        return match.group(0)

    def test_apply_view_persists_chip(self) -> None:
        assert "schoolStatus.chip = String(" in self._apply_view_block()

    def test_footer_appends_chip_after_status_line(self) -> None:
        block = self._complete_block()
        footer_at = block.index("[school] ${schoolFooter()}")
        chip_at = block.index("if (schoolStatus.chip)")
        assert footer_at < chip_at

    def test_footer_stays_idempotent(self) -> None:
        block = self._complete_block()
        assert 'output.text.includes("[school] route:")' in block
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `& ".venv\Scripts\python.exe" -m pytest -q --no-header -p no:cacheprovider tests/unit/test_context_chip_wiring.py`
Expected: FAIL — `test_footer_appends_chip_after_status_line` fails (`if (schoolStatus.chip)` not in the text.complete hook); all other tests already pass (they pin S1/Task-2 behavior).

- [ ] **Step 3: Render the chip in the footer**

In `school/plugin_source.py`, inside the `"experimental.text.complete"` hook, change:

```ts
        output.text = `${output.text}\n\n[school] ${schoolFooter()}`
```

to:

```ts
        output.text = `${output.text}\n\n[school] ${schoolFooter()}`
        if (schoolStatus.chip) output.text += `\n${schoolStatus.chip}`
```

The idempotency guard (`output.text.includes("[school] route:")`) and everything else in the hook stay byte-for-byte unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `& ".venv\Scripts\python.exe" -m pytest -q --no-header -p no:cacheprovider tests/unit/test_context_chip_wiring.py`
Expected: all passed

- [ ] **Step 5: Regression (footer + full hooks + live footer)**

Run: `& ".venv\Scripts\python.exe" -m pytest -q --no-header -p no:cacheprovider tests/unit/test_school_plugin_hooks.py tests/unit/test_bridge_context.py tests/integration/test_plugin_live.py`
Expected: all passed — the live footer harness stores no chip, so `first == second` idempotency is unchanged.

- [ ] **Step 6: Ruff (E501 budget!)**

Run: `& ".venv\Scripts\python.exe" -m ruff check tests/unit/test_context_chip_wiring.py`
Expected: All checks passed!

Run: `& ".venv\Scripts\python.exe" -m ruff check school/plugin_source.py`
Expected: **16 errors** (unchanged baseline)

---

### Task 8: Compaction nudge (`experimental.session.compacting`)

**Files:**
- Modify: `school/plugin_source.py` (new hook between `experimental.text.complete` and `experimental.chat.messages.transform`)
- Modify: `tests/unit/test_school_plugin_hooks.py` (`EXPECTED_HOOKS` + docstring + append `class TestCompactingNudge`)
- Test: append `class TestCompactingNudge` at END of `tests/unit/test_school_plugin_hooks.py`

**Interfaces:**
- Produces (TS): hook `"experimental.session.compacting": async (_input, output) => {...}` which, only when hooks+ctx are on and `SCHOOL_COMPRESS != "0"`, estimates `output.context` via the existing `ctxEstimate`, and when it reaches `CTX_THRESHOLD` pushes one calm line onto the compaction context: `[school] compaction · school_context_compress keeps blocks restorable`.
- Consumes: `hooksEnabled()`, `ctxEnabled()`, `ctxEstimate`, `CTX_THRESHOLD` (all S1-exists). Never touches session history — only the `output.context` array of the compaction event. Fail-open: any error → compaction proceeds unmodified.

- [ ] **Step 1: Write the failing tests**

1a. In `tests/unit/test_school_plugin_hooks.py`, extend `EXPECTED_HOOKS` (after `"experimental.text.complete",`):

```python
    "experimental.session.compacting",
```

and add one bullet to the module docstring after the text.complete line:

```python
- ``experimental.session.compacting`` - budget-pressure nudge during auto-compaction
```

1b. Append at the END of `tests/unit/test_school_plugin_hooks.py`:

```python
class TestCompactingNudge:
    """experimental.session.compacting: quiet budget-pressure nudge (S2)."""

    def _block(self) -> str:
        return _hook_block("experimental.session.compacting")

    def test_gates_kill_switches(self) -> None:
        block = self._block()
        assert "hooksEnabled()" in block
        assert "ctxEnabled()" in block
        assert 'process.env.SCHOOL_COMPRESS === "0"' in block

    def test_nudges_only_above_threshold(self) -> None:
        block = self._block()
        assert "Array.isArray" in block
        assert "ctxEstimate(" in block
        assert "CTX_THRESHOLD" in block
        assert "context.push(" in block

    def test_nudge_is_school_voice(self) -> None:
        block = self._block()
        assert "[school] compaction ·" in block
        assert "school_context_compress" in block

    def test_fails_open(self) -> None:
        block = self._block()
        assert "try {" in block
        assert "catch" in block
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `& ".venv\Scripts\python.exe" -m pytest -q --no-header -p no:cacheprovider tests/unit/test_school_plugin_hooks.py`
Expected: FAIL — `missing hook: experimental.session.compacting` and `hook not found: experimental.session.compacting`; everything else passes.

- [ ] **Step 3: Implement the compacting hook**

In `school/plugin_source.py`, insert between the end of the `"experimental.text.complete"` hook (`    },`) and the line `    "experimental.chat.messages.transform": async (_input, output) => {`:

```ts
    "experimental.session.compacting": async (_input, output) => {
      try {
        if (!hooksEnabled() || !ctxEnabled()) return
        if (process.env.SCHOOL_COMPRESS === "0") return
        const context = (output as any)?.context
        if (!Array.isArray(context) || !context.length) return
        const est = ctxEstimate(context.join("\n"))
        if (est < CTX_THRESHOLD) return
        context.push(
          "[school] compaction · school_context_compress keeps blocks restorable",
        )
      } catch {
        // Compaction nudges are best-effort.
      }
    },
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `& ".venv\Scripts\python.exe" -m pytest -q --no-header -p no:cacheprovider tests/unit/test_school_plugin_hooks.py`
Expected: all passed (old + new)

- [ ] **Step 5: Live TS syntax/regression gate**

Run: `& ".venv\Scripts\python.exe" -m pytest -q --no-header -p no:cacheprovider tests/integration/test_plugin_live.py`
Expected: all passed — the new hook is registered but never invoked by the harness.

- [ ] **Step 6: Ruff (E501 budget!)**

Run: `& ".venv\Scripts\python.exe" -m ruff check school/plugin_source.py`
Expected: **16 errors** (unchanged baseline)

Run: `& ".venv\Scripts\python.exe" -m ruff check tests/unit/test_school_plugin_hooks.py`
Expected: All checks passed!

---

### Task 9: Integration suite (subprocess bridge + live node) and full regression gates

**Files:**
- Create: `tests/integration/test_context_surfaces.py`

**Interfaces:**
- Consumes: everything — five bridge commands over a real `python -m school.bridge` subprocess, apply-view + coexist gate through node running the real TS, kill switches, and the final regression gates.
- Produces: the S2 exit evidence (spec §10): all surfaces live; DCP-present and absent modes both tested; parity/counts green; battery green.

- [ ] **Step 1: Write the integration tests**

Create `tests/integration/test_context_surfaces.py`:

```python
"""S2 Task 9: end-to-end context surfaces (bridge subprocess + live node)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
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
    return env


def run_bridge(req: dict, env: dict | None = None) -> dict:
    """One JSON request through a real ``python -m school.bridge`` process."""
    proc_env = dict(os.environ)
    proc_env["PYTHONPATH"] = str(REPO_ROOT)
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
def plugin_dir(tmp_path: Path) -> Path:
    d = tmp_path / "plugin"
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
            {"command": "context_status", "worktree": wt, "session": "sub1"}
        )
        assert status["blocks"] >= 1
        restored = run_bridge(
            {"command": "context_restore", "worktree": wt, "session": "sub1"}
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
        self, plugin_dir: Path, tmp_path: Path
    ) -> None:
        worktree = tmp_path / "wt"
        worktree.mkdir()
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
        self, plugin_dir: Path, tmp_path: Path
    ) -> None:
        worktree = tmp_path / "wt"
        worktree.mkdir()
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
```

- [ ] **Step 2: Run the suite**

Run: `& ".venv\Scripts\python.exe" -m pytest -q --no-header -p no:cacheprovider tests/integration/test_context_surfaces.py`
Expected: all passed — this suite verifies Tasks 1-8 end-to-end; if anything fails, the defect is in an earlier task (go back and fix it there — never weaken these tests).

- [ ] **Step 3: Full battery (S2 exit gate)**

Run: `& ".venv\Scripts\python.exe" -m pytest -q --no-header -p no:cacheprovider`
Expected: all passed — 3049 baseline + the new S2 tests, zero failures/errors; includes the tool-surface counts (29 TS / 31 MCP), byte-equal TS↔MCP description parity, and the read-only annotation set.

- [ ] **Step 4: Ruff over every touched Python file**

Run: `& ".venv\Scripts\python.exe" -m ruff check core/context/coexist.py core/context/view.py school/bridge.py school/cli.py school/mcp/server.py tests/unit/test_context_coexist.py tests/unit/test_bridge_context.py tests/unit/test_cli.py tests/unit/test_mcp_server.py tests/unit/test_school_plugin_bridge.py tests/unit/test_school_plugin_hooks.py tests/unit/test_context_chip_wiring.py tests/integration/test_mcp_stdio.py tests/integration/test_plugin_live.py tests/integration/test_context_surfaces.py`
Expected: All checks passed!

Run: `& ".venv\Scripts\python.exe" -m ruff check school/plugin_source.py`
Expected: **16 errors** (the unchanged baseline)

---

## Plan notes

- **Task 3 assertion typo (fix at execution time):** `test_apply_view_stores_footer_chip` asserts `"schoolStatus.chip = chip"`, but Task 3 Step 3c implements `schoolStatus.chip = String((resp as any).chip ?? "")`. Change the assertion to `assert "schoolStatus.chip = String(" in block` (the implementation stays as written). Task 7's `test_apply_view_persists_chip` already asserts the correct substring.
