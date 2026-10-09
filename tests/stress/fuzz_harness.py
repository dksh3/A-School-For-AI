"""Adversarial fuzz harness for the whole School tool ecosystem.

CONTRACT (what "fail-open" means here)
-------------------------------------
Every School tool, given ANY input — hostile, malformed, or valid — must
either (a) return a result object/dict/str, or (b) return a graceful error
result. It must NEVER raise out of the tool boundary. This harness is
*designed to make tools fail*: it generates adversarial inputs (wrong types,
cyclic structures, NaN/inf, huge payloads, unicode/NUL bytes, deep nesting,
callables, generators, exceptions-as-values) and records every crash.

Usage
-----
    from tests.stress.fuzz_harness import fuzz_fail_open, HOSTILE, gen_value

    def test_remember_fuzz():
        report = fuzz_fail_open(
            lambda a: remember(*a),
            n=2000,
            make_args=lambda i: ((gen_worktree(i), HOSTILE[i % len(HOSTILE)]), {}),
            label="school_remember",
        )
        assert report.ok, report.summary()

Iteration counts are tracked per label in FUZZ_LEDGER so we can prove each
tool/feature was exercised the required number of times (2000 each).
"""

from __future__ import annotations

import contextlib
import functools
import random
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Adversarial value corpus
# ---------------------------------------------------------------------------

class _Cyclic:
    def __init__(self) -> None:
        self.self_ref = self  # cyclic structure

    def __repr__(self) -> str:  # pragma: no cover
        return "<Cyclic>"


class _Evil:
    """An object whose dunders blow up or return garbage."""

    def __getattr__(self, name: str) -> Any:
        raise RuntimeError(f"evil getattr {name}")

    def __str__(self) -> str:
        raise RuntimeError("evil __str__")

    def __repr__(self) -> str:
        raise RuntimeError("evil __repr__")

    def __eq__(self, other: object) -> bool:
        raise RuntimeError("evil __eq__")

    def __hash__(self) -> int:
        raise RuntimeError("evil __hash__")

    def __bool__(self) -> bool:
        raise RuntimeError("evil __bool__")

    def __len__(self) -> int:
        raise RuntimeError("evil __len__")

    def __iter__(self):
        raise RuntimeError("evil __iter__")

    def __call__(self, *a, **k):
        raise RuntimeError("evil __call__")


class _BadDict(dict):
    def __iter__(self):
        raise RuntimeError("evil dict iter")

    def keys(self):
        raise RuntimeError("evil dict keys")

    def items(self):
        raise RuntimeError("evil dict items")

    def __getitem__(self, k):
        raise RuntimeError("evil dict getitem")


class _BadList(list):
    def __iter__(self):
        raise RuntimeError("evil list iter")

    def __getitem__(self, i):
        raise RuntimeError("evil list getitem")

    def __len__(self):
        raise RuntimeError("evil list len")


class _Throws:
    def __init__(self) -> None:
        self._x = 1

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        raise ValueError(f"throws on {name}")


def _huge(n: int = 200_000) -> str:
    return "X" * n


#: Flat corpus of adversarial scalars / containers (safe to enumerate).
HOSTILE: list[Any] = [
    # wrong / edge scalars
    None, 0, -1, 1, -0.0, 3.14, -3.14, True, False,
    float("inf"), float("-inf"), float("nan"),
    10**50, -(10**50), 2**63, -(2**63) - 1, complex(1, 2),
    # strings: empty, blank, unicode, emoji, NUL, control, huge, pathological
    "", " ", "\t", "\n", "\r\n", "\x00", "null\x00byte", "a\x00b",
    "🔥💀émoji ünïcödé", "​zero​width​", "\U0001f4a9" * 100,
    "line\nbreaks\ttabbed", " " * 5000, _huge(50_000),
    "répétition" * 500, "{}{}{}".format("{x}", "{y}", "{z}"),
    # bytes / bytearray / memoryview
    b"", b"\x00\xff\xfe", bytearray(b"abc"), memoryview(b"xyz"),
    # sequences
    [], [None], [1, 2, 3], list(range(500)), tuple(), (1,), {"a": 1}.keys(),
    # mappings
    {}, {"a": 1}, {"nested": {"deep": [1, 2, {"x": None}]}},
    {1: 2, None: 3, (1, 2): 4}, _BadDict(), _BadList(),
    # sets / frozensets
    set(), {1, 2, 3}, frozenset({1, 2}), {1, 2.0, 3},
    # objects / callables / weird
    object(), _Cyclic(), _Evil(), _Throws(), lambda x: x,
    functools.partial(lambda a, b: a, b=1), range(3), slice(1, 2),
    type("X", (), {}), Exception("boom"), ValueError("bad"),
]


def gen_value(depth: int = 0, rng: random.Random | None = None) -> Any:
    """Recursive adversarial value generator (bounded depth)."""
    rng = rng or random.Random(0)
    if depth > 3:
        return rng.choice(HOSTILE)
    pick = rng.randint(0, 6)
    if pick == 0:
        return rng.choice(HOSTILE)
    if pick == 1:
        return [gen_value(depth + 1, rng) for _ in range(rng.randint(0, 4))]
    if pick == 2:
        return {
            f"k{rng.randint(0, 9)}": gen_value(depth + 1, rng)
            for _ in range(rng.randint(0, 3))
        }
    if pick == 3:
        out: set = set()
        for _ in range(rng.randint(0, 3)):
            v = gen_value(depth + 1, rng)
            with contextlib.suppress(Exception):
                out.add(v)  # unhashable / exploding __hash__ -> skip
        return out
    if pick == 4:
        return {
            "items": [gen_value(depth + 1, rng) for _ in range(rng.randint(0, 3))],
            "meta": {"n": rng.randint(-10, 10)},
        }
    if pick == 5:
        return _huge(rng.randint(1, 20_000))
    return rng.choice(HOSTILE)


def gen_str(rng: random.Random | None = None) -> str:
    rng = rng or random.Random(0)
    pool = [h for h in HOSTILE if isinstance(h, str)] + ["", "tool", "school_x"]
    return str(rng.choice(pool))


def gen_json_safe(rng: random.Random | None = None) -> dict:
    """A random JSON-ish dict, mixing valid and hostile fields."""
    rng = rng or random.Random(0)
    return {
        "command": rng.choice(["status", "remember", "recall", "goal", "zzz", ""]),
        "worktree": rng.choice([".", "", None, 123, "C:\\nope", "\x00"]),
        "tool_name": gen_str(rng),
        "text": gen_str(rng),
        "n": rng.choice([0, -1, 999999, 3.14, None, "x"]),
    }


# ---------------------------------------------------------------------------
# Fuzz runner + per-label ledger
# ---------------------------------------------------------------------------

#: label -> number of iterations actually executed (for the "N times each" proof)
FUZZ_LEDGER: dict[str, int] = {}
#: label -> list of failure records
FUZZ_FAILURES: dict[str, list[dict]] = {}


@dataclass
class FuzzReport:
    label: str
    iterations: int = 0
    failures: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures

    def summary(self) -> str:
        head = (
            f"[fuzz] {self.label}: {self.iterations} iterations, "
            f"{len(self.failures)} failures"
        )
        if not self.failures:
            return head
        lines = [head]
        for f in self.failures[:10]:
            lines.append(
                f"  #{f['i']} args={f['args']!r:.120} -> "
                f"{f['err_type']}: {f['err']:.160}"
            )
        return "\n".join(lines)


def _safe_repr(obj: Any, limit: int = 120) -> str:
    """repr() that never raises (hostile objects have exploding __repr__)."""
    try:
        s = repr(obj)
    except Exception:  # noqa: BLE001
        return f"<{type(obj).__name__}>"
    return s if len(s) <= limit else s[:limit] + "…"


def fuzz_fail_open(
    call: Callable[..., Any],
    n: int = 2000,
    make_args: Callable[[int], tuple[tuple, dict]] | None = None,
    label: str = "tool",
    check: Callable[[Any], None] | None = None,
) -> FuzzReport:
    """Run `call` n times with adversarial args; record any raise as a failure.

    `make_args(i)` returns `(args_tuple, kwargs_dict)`. Default uses gen_value.
    `check(result)` is an optional invariant assertion; its AssertionError counts
    as a failure (for correctness, not just crash, testing).
    """
    report = FuzzReport(label=label)
    rng = random.Random(hash(label) & 0xFFFFFFFF)
    for i in range(n):
        args: tuple = ()
        kwargs: dict = {}
        try:
            if make_args is not None:
                args, kwargs = make_args(i)
            else:
                args, kwargs = ((gen_value(rng=rng),), {})
            result = call(*args, **kwargs)
            if check is not None:
                check(result)
            report.iterations += 1
        except Exception as exc:  # noqa: BLE001 — we WANT to catch everything
            report.iterations += 1
            report.failures.append({
                "i": i,
                "args": _safe_repr(args),
                "err_type": type(exc).__name__,
                "err": _safe_repr(str(exc), 160),
                "tb": traceback.format_exc(),
            })
    FUZZ_LEDGER[label] = FUZZ_LEDGER.get(label, 0) + report.iterations
    FUZZ_FAILURES.setdefault(label, []).extend(report.failures)
    return report


def ledger_summary() -> str:
    total = sum(FUZZ_LEDGER.values())
    lines = [f"[fuzz-ledger] {len(FUZZ_LEDGER)} labels, {total} total iterations"]
    for label in sorted(FUZZ_LEDGER):
        fails = len(FUZZ_FAILURES.get(label, []))
        mark = "OK " if fails == 0 else f"{fails}F"
        lines.append(f"  {mark}  {label}: {FUZZ_LEDGER[label]}")
    return "\n".join(lines)
