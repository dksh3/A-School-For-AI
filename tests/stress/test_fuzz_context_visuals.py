"""Adversarial fail-open fuzz campaign: context engine + all 101 visual renderers.

Every renderer / context tool must, given ANY input, return a usable result and
NEVER raise at the boundary.  This suite hammers:

  A. all 101 render_* (direct) + the render_visual dispatcher  — 2000 iters each
  B. ContextEngine (compress/view/restore/should_compress) + BlockStore
  C. chip / progress / graph / cumulative
  D. tool_guard (11 layers + school_tool_for + guard_banner + helpers)

Inputs are drawn from the shared fuzz_harness HOSTILE corpus plus targeted
hostile shapes: None-in-sequences, NaN/inf, wrong-length tuples, empty, huge,
unicode/emoji, None labels, huge/zero/negative widths, str-vs-num, dict-vs-list.
"""
from __future__ import annotations

import inspect
import pathlib
import sys
import tempfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from fuzz_harness import HOSTILE, fuzz_fail_open, gen_str, ledger_summary  # noqa: E402

import core.context.coding_visuals as _cv  # noqa: E402
import core.context.general_visuals as _gv  # noqa: E402
import core.context.tool_guard as tg  # noqa: E402
import core.context.visuals as _uv  # noqa: E402
from core.context.chip import build_chip, fmt_tokens  # noqa: E402
from core.context.cumulative import CumulativeStats  # noqa: E402
from core.context.engine import ContextEngine  # noqa: E402
from core.context.graph import render_bar_graph  # noqa: E402
from core.context.progress import render_bar, render_eta  # noqa: E402
from core.context.store import BlockStore  # noqa: E402
from core.context.visual_dispatch import (  # noqa: E402
    RENDER_SPEC,
    VISUAL_TYPES,
    render_visual,
)

NAN = float("nan")
INF = float("inf")


# ── checks (must RAISE to register a fuzz failure) ──────────────────────────
def _nonempty_str(r):
    assert isinstance(r, str) and bool(r), f"non-empty str expected, got {type(r).__name__}={r!r}"


def _expect(*types):
    def chk(r):
        assert isinstance(r, types), f"expected {types}, got {type(r).__name__}={r!r}"

    return chk


def _has_messages_ok(r):
    assert hasattr(r, "to_dict"), f"expected CumulativeStats, got {type(r).__name__}"


# ── hostile value pools ─────────────────────────────────────────────────────
def _evilish():
    return [h for h in HOSTILE if type(h).__name__ in
            ("_Evil", "_Cyclic", "_BadDict", "_BadList", "_Throws")]


EVIL = _evilish()

NUM = [0, 1, -1, 20, 32, 10**6, -10**6, NAN, INF, -INF, "5", "x", None,
       3.5, True, 2**63, -0.0, {"w": 1}, [3]] + EVIL
TXT = ["", "label", "🔥" * 50, "\x00", "a\x00b", "\n\t", None, 12345,
       "x" * 5000, " ", "émoji ünïcödé", "{}{}{}"] + EVIL

TUPLE_ROWS = [
    [], None, [None], [("a", 1)], [("a", 1, 2, 3, 4)], [("a",)],
    [("a", None, None)], [(1, 2), ("b", "x"), None, 5, {"k": 1}],
    "notalist", list(range(20)), [("🔥", NAN)], [(None,) * 3],
] + EVIL
GRID = [[], None, [[1, 2], [3, None]], [[NAN]], ["row", None, [1, 2, 3]],
        [[1, 2, 3]], "x", [[INF, -INF]]] + EVIL
DICTS = [{}, {"a": 1}, {"a": [1, None], None: "x", 5: "y"}, {"5": "x"},
         None, [], {"b": NAN}, {"k": {"deep": [1, None]}}] + EVIL
LISTS = [[], None, [None, 1, NAN, "x", (1,)], [1, 2, 3], "str",
         list(range(100)), [INF, -INF], {"a": 1}] + EVIL
TREES = [[], None, [{"name": "a", "children": [{"name": "b"}]}, 5, "x"],
         {"name": "root"}, [{"name": 1, "children": "x"}], [None]] + EVIL
ROWS = [[], None, [{"a": 1}], [5, "x", {"a": "b"}], {"a": 1},
        [{"a": None, "b": 5}]] + EVIL


def hostile(code: str, i: int):
    c = code or ""
    if c == "str":
        return TXT[i % len(TXT)]
    if c in ("float", "int", "width", "bool"):
        return NUM[i % len(NUM)]
    if c.startswith("("):
        return TUPLE_ROWS[i % len(TUPLE_ROWS)]
    if c == "grid":
        return GRID[i % len(GRID)]
    if c == "tree":
        return TREES[i % len(TREES)]
    if c == "rows":
        return ROWS[i % len(ROWS)]
    if c.startswith("dict:"):
        return DICTS[i % len(DICTS)]
    if c.startswith("list:"):
        return LISTS[i % len(LISTS)]
    return HOSTILE[i % len(HOSTILE)]


def _pos_params(fn):
    try:
        return [
            p for p in inspect.signature(fn).parameters.values()
            if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]
    except Exception:  # noqa: BLE001
        return []


def make_args(fn, spec):
    params = _pos_params(fn)
    n = len(params)

    def _make(i):
        args = tuple(hostile(spec[j] if j < len(spec) else "", i + j) for j in range(n))
        return (args, {})

    return _make


def _collect(*mods):
    out = {}
    for m in mods:
        for name, fn in vars(m).items():
            if name.startswith("render_") and callable(fn):
                out[name] = fn
    return out


RENDERERS = _collect(_uv, _cv, _gv)
RENDERER_NAMES = sorted(RENDERERS)

# engine message payloads
MSGS = [
    None, [], [None], [{"role": "user", "content": "hello"}], [{"content": None}],
    [{"role": "tool", "content": "error failed boom"}],
    [{"role": "tool", "content": "Traceback failed"}] * 3,
    [1, 2, 3], {"a": 1}, "juststring", [{"content": "x" * 5000}],
    [{"role": "assistant", "tool_calls": 1}], [{"content": NAN}],
] + EVIL


def hostile_msgs(i):
    return MSGS[i % len(MSGS)]


WORKTREES = ["", ".", "\x00", "a\x00b", None, 123, "C:\\nope", "x" * 1000, NAN]
SIDS = ["", "sess", "\x00", "..\\..", None, 999, "a" * 500, NAN]


@pytest.fixture(scope="session", autouse=True)
def _ledger():
    yield
    print("\n" + ledger_summary())


# ── A. all 101 renderers + dispatcher ───────────────────────────────────────
def test_renderer_count():
    assert len(RENDERERS) == 101, f"expected 101 renderers, got {len(RENDERERS)}"
    assert len(VISUAL_TYPES) == 101, f"expected 101 visual types, got {len(VISUAL_TYPES)}"
    assert set(RENDERER_NAMES) == set(RENDER_SPEC), "RENDER_SPEC must cover all renderers"


@pytest.mark.parametrize("name", RENDERER_NAMES)
def test_renderer_fail_open(name):
    fn = RENDERERS[name]
    report = fuzz_fail_open(
        fn, n=2000, make_args=make_args(fn, RENDER_SPEC.get(name, [])),
        label=f"renderer.{name}", check=_nonempty_str,
    )
    assert report.ok, report.summary()


PLACEHOLDER_MARK = "coerced to a safe fallback"


def valid_for(code):
    c = code or ""
    if c == "str":
        return "x"
    if c == "float":
        return 0.5
    if c in ("int", "width"):
        return 3
    if c == "bool":
        return True
    if c == "list:str":
        return ["a"]
    if c == "list:float":
        return [1.0]
    if c == "list:int":
        return [1]
    if c == "list:bool":
        return [True]
    if c == "grid":
        return [[1.0, 2.0]]
    if c == "tree":
        return [{"name": "n", "children": []}]
    if c == "rows":
        return [{"a": "1"}]
    if c == "dict:str->int":
        return {"a": 1}
    if c == "dict:int->int":
        return {1: 1}
    if c == "dict:str->list:str":
        return {"a": ["b"]}
    if c == "dict:str->list:float":
        return {"a": [1.0]}
    if c == "dict:str->str":
        return {"a": "b"}
    if c.startswith("pair("):
        return tuple(valid_for(s) for s in c[5:-1].split(","))
    if c.startswith("("):
        return [tuple(valid_for(s) for s in c[1:-1].split(","))]
    return "x"


@pytest.mark.parametrize("name", RENDERER_NAMES)
def test_renderer_real_output(name):
    """Valid input must render real content, not the blanket fail-open card."""
    fn = RENDERERS[name]
    spec = RENDER_SPEC[name]
    n = len(_pos_params(fn))
    args = tuple(valid_for(spec[j]) if j < len(spec) else "x" for j in range(n))
    r = fn(*args)
    assert isinstance(r, str) and r, f"{name}: empty result"
    assert PLACEHOLDER_MARK not in r, f"{name}: fallback on valid input -> {r!r}"


def test_dispatch_render_visual():
    types = VISUAL_TYPES + ["", "nope", None, 123, "bogus-type"]
    data_shapes = [{}, {"items": [None, 1, ("a", "b")]}, {"values": [NAN, None]},
                   {"grid": [[1, None]]}, None, {"x": _evilish()[0]}]

    def _make(i):
        return ((types[i % len(types)], data_shapes[i % len(data_shapes)],
                 TXT[i % len(TXT)], NUM[i % len(NUM)]), {})

    report = fuzz_fail_open(
        render_visual, n=2000, make_args=_make,
        label="dispatch.render_visual", check=_nonempty_str,
    )
    assert report.ok, report.summary()


# ── B. ContextEngine + BlockStore ──────────────────────────────────────────
def test_engine_compress():
    E = ContextEngine(worktree=tempfile.mkdtemp(), session_id="fz")
    report = fuzz_fail_open(
        lambda m: E.compress(m).to_dict(), n=2000,
        make_args=lambda i: ((hostile_msgs(i),), {}),
        label="engine.compress", check=_expect(dict),
    )
    assert report.ok, report.summary()


def test_engine_view():
    E = ContextEngine(worktree=tempfile.mkdtemp(), session_id="fz")

    def call(m):
        v = E.view(m)
        return {"messages": v.messages, "blocks": v.blocks_included}

    report = fuzz_fail_open(
        call, n=2000, make_args=lambda i: ((hostile_msgs(i),), {}),
        label="engine.view", check=_expect(dict),
    )
    assert report.ok, report.summary()


def test_engine_restore():
    E = ContextEngine(worktree=tempfile.mkdtemp(), session_id="fz")
    report = fuzz_fail_open(
        lambda b: E.restore(b), n=2000,
        make_args=lambda i: ((TXT[i % len(TXT)],), {}),
        label="engine.restore", check=_expect(dict),
    )
    assert report.ok, report.summary()


def test_engine_should_compress():
    E = ContextEngine(worktree=tempfile.mkdtemp(), session_id="fz")
    report = fuzz_fail_open(
        lambda m: E.should_compress(m), n=2000,
        make_args=lambda i: ((hostile_msgs(i),), {}),
        label="engine.should_compress", check=_expect(bool),
    )
    assert report.ok, report.summary()


def test_store_constructor():
    def call(w, s):
        return BlockStore(w, s).load()

    report = fuzz_fail_open(
        call, n=2000,
        make_args=lambda i: ((WORKTREES[i % len(WORKTREES)], SIDS[i % len(SIDS)]), {}),
        label="store.constructor", check=_expect(list),
    )
    assert report.ok, report.summary()


def test_store_lifecycle():
    S = BlockStore(worktree=tempfile.mkdtemp(), session_id="fz")
    reports = [
        fuzz_fail_open(lambda: S.load(), n=2000, make_args=lambda i: ((), {}),
                       label="store.load", check=_expect(list)),
        fuzz_fail_open(lambda b: S.save(b), n=2000,
                       make_args=lambda i: (([hostile_msgs(i), i],), {}),
                       label="store.save", check=_expect(type(None))),
        fuzz_fail_open(lambda b: S.add(b), n=2000,
                       make_args=lambda i: ((hostile_msgs(i),), {}),
                       label="store.add", check=_expect(type(None))),
        fuzz_fail_open(lambda b: S.update(b), n=2000,
                       make_args=lambda i: ((hostile_msgs(i),), {}),
                       label="store.update", check=_expect(type(None))),
        fuzz_fail_open(lambda b: S.get(b), n=2000,
                       make_args=lambda i: ((TXT[i % len(TXT)],), {}),
                       label="store.get", check=_expect(type(None), object)),
    ]
    for r in reports:
        assert r.ok, r.summary()


# ── C. chip / progress / graph / cumulative ─────────────────────────────────
def test_chip_progress_graph():
    reports = [
        fuzz_fail_open(build_chip, n=2000, make_args=lambda i: ((), {
            "blocks_added": NUM[i % len(NUM)], "restores": NUM[i % len(NUM)],
            "saved_tokens": NUM[i % len(NUM)], "used_ratio": NUM[i % len(NUM)],
            "spend_usd": NUM[i % len(NUM)],
        }), label="chip.build_chip", check=_expect(str)),
        fuzz_fail_open(fmt_tokens, n=2000,
                       make_args=lambda i: ((NUM[i % len(NUM)],), {}),
                       label="chip.fmt_tokens", check=_expect(str)),
        fuzz_fail_open(render_bar, n=2000, make_args=lambda i: (
            (NUM[i % len(NUM)], NUM[i % len(NUM)], TXT[i % len(TXT)]), {}),
            label="progress.render_bar", check=_nonempty_str),
        fuzz_fail_open(render_eta, n=2000, make_args=lambda i: (
            (NUM[i % len(NUM)], NUM[i % len(NUM)]), {}),
            label="progress.render_eta", check=_nonempty_str),
        fuzz_fail_open(render_bar_graph, n=2000, make_args=lambda i: (
            (TUPLE_ROWS[i % len(TUPLE_ROWS)], NUM[i % len(NUM)]), {}),
            label="graph.render_bar_graph", check=_nonempty_str),
    ]
    for r in reports:
        assert r.ok, r.summary()


def test_cumulative():
    C = CumulativeStats(worktree=tempfile.mkdtemp())
    reports = [
        fuzz_fail_open(lambda: C.to_dict(), n=2000, make_args=lambda i: ((), {}),
                       label="cumulative.to_dict", check=_expect(dict)),
        fuzz_fail_open(lambda: C.render_chip(), n=2000, make_args=lambda i: ((), {}),
                       label="cumulative.render_chip", check=_nonempty_str),
        fuzz_fail_open(lambda: C.refresh(), n=2000, make_args=lambda i: ((), {}),
                       label="cumulative.refresh", check=_expect(type(None))),
        fuzz_fail_open(lambda w: CumulativeStats.load(w), n=2000,
                       make_args=lambda i: ((WORKTREES[i % len(WORKTREES)],), {}),
                       label="cumulative.load", check=_has_messages_ok),
    ]
    for r in reports:
        assert r.ok, r.summary()


# ── D. tool_guard ──────────────────────────────────────────────────────────
def _tool_name(i):
    return gen_str() if i % 3 == 0 else HOSTILE[i % len(HOSTILE)]


def test_guard_layers():
    for lid, surface, fn in tg.GUARD_LAYERS:
        report = fuzz_fail_open(
            fn, n=2000, make_args=lambda i, f=fn: (( _tool_name(i),), {}),
            label=f"guard.{lid}_{surface}", check=_expect(str),
        )
        assert report.ok, report.summary()


def test_guard_core():
    reports = [
        fuzz_fail_open(tg.school_tool_for, n=2000,
                       make_args=lambda i: ((_tool_name(i),), {}),
                       label="guard.school_tool_for", check=_expect(tuple)),
        fuzz_fail_open(tg.guard_banner, n=2000,
                       make_args=lambda i: ((_tool_name(i),), {}),
                       label="guard.guard_banner", check=_expect(str)),
        fuzz_fail_open(tg.is_school_tool, n=2000,
                       make_args=lambda i: ((_tool_name(i),), {}),
                       label="guard.is_school_tool", check=_expect(bool)),
        fuzz_fail_open(tg.run_all_layers, n=2000,
                       make_args=lambda i: ((_tool_name(i),), {}),
                       label="guard.run_all_layers", check=_expect(dict)),
        fuzz_fail_open(tg.run_layer, n=2000, make_args=lambda i: (
            (f"L{i % 11 + 1}", _tool_name(i)), {}),
            label="guard.run_layer", check=_expect(str)),
        fuzz_fail_open(tg.brand_response, n=2000, make_args=lambda i: (
            (HOSTILE[i % len(HOSTILE)], _tool_name(i)), {}),
            label="guard.brand_response", check=None),
    ]
    for r in reports:
        assert r.ok, r.summary()
