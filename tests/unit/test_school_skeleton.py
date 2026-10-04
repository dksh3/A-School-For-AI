"""Contract tests for the Context Optimizer core (school.skeleton)."""

import re
import time

from school.skeleton import (
    CODE_EXTENSIONS,
    CTX_THRESHOLD,
    FOOTER_RE,
    LANGUAGES,
    OptimizeResult,
    comment_prefix,
    elide_matches,
    estimate_tokens,
    heuristic_skeleton,
    make_footer,
    optimize,
    skeletonize_payload,
    strip_footer,
)

FOOTER_ONE = re.compile(r"\[school ctx: \d+→\d+ tokens\]")


def _payload_lines(n: int) -> str:
    return "\n".join(f'{{"k": "some value {i}"}}' for i in range(n))


class TestTokenEstimate:
    def test_ceil_rule(self):
        assert estimate_tokens("") == 0
        assert estimate_tokens("abcd") == 1
        assert estimate_tokens("abcde") == 2

    def test_threshold_constant(self):
        assert CTX_THRESHOLD == 1000


class TestFooter:
    def test_make_footer_format(self):
        assert make_footer(1000, 250) == "[school ctx: 1000→250 tokens]"

    def test_strip_footer(self):
        body = "def f():\n    pass"
        assert strip_footer(body + "\n\n" + make_footer(4, 4)) == body

    def test_strip_footer_idempotent(self):
        body = "x = 1"
        once = strip_footer(body)
        assert strip_footer(once) == once

    def test_footer_regex_shape(self):
        assert FOOTER_RE.fullmatch(make_footer(4321, 99)) is not None
        assert FOOTER_RE.search("[school ctx: 1→1 tokens]") is not None


class TestBelowThreshold:
    def test_999_tokens_raw_untouched(self):
        text = "x" * 3996  # ceil(3996/4) == 999
        assert estimate_tokens(text) == 999
        res = optimize(text, filename="notes.txt")
        assert res.compressed is False
        assert res.parser == "passthrough"
        assert res.text == text
        assert "school ctx" not in res.text

    def test_1000_tokens_attempts_compression(self):
        text = _payload_lines(400)  # well over 1000 tokens
        res = optimize(text, filename="data.json")
        assert res.tokens_in >= CTX_THRESHOLD

    def test_idempotent_single_footer(self):
        text = _payload_lines(400)
        first = optimize(text, filename="data.json")
        assert first.compressed is True
        assert len(FOOTER_ONE.findall(first.text)) == 1
        second = optimize(first.text, filename="data.json")
        assert len(FOOTER_ONE.findall(second.text)) <= 1


class TestKillSwitch:
    def test_school_ctx_zero_passthrough(self, monkeypatch):
        monkeypatch.setenv("SCHOOL_CTX", "0")
        text = _payload_lines(400)
        res = optimize(text, filename="data.json")
        assert res.compressed is False
        assert res.parser == "passthrough"
        assert res.text == text
        assert "school ctx" not in res.text


class TestNeverExpand:
    def test_output_never_larger_than_input(self):
        lines = []
        for i in range(200):
            lines.append(f'"unique string alpha {i}":')
            lines.append(f"{i * 7919}")
        text = "\n".join(lines)
        res = optimize(text, filename="kv.json")
        assert res.tokens_out <= res.tokens_in
        if not res.compressed:
            assert res.text == text


class TestPayloadSkeleton:
    def test_repeated_block_collapsed(self):
        text = "\n".join("{\"item\": \"value\"}" for _ in range(30))
        out = skeletonize_payload(text, filename="data.json")
        kept = [ln for ln in out.splitlines() if ln]
        assert len(kept) == 3
        assert kept[0] == '{"item": "value"}'
        assert "repeated block — 28 lines" in out

    def test_blank_runs_collapse(self):
        text = "a\n\n\n\nb"
        out = skeletonize_payload(text, filename="data.json")
        assert out == "a\n\nb"


class TestMatchesElision:
    def test_grouped_keep_10(self):
        lines = [f"a.py:{i}: match {i}" for i in range(1, 16)]
        lines += [f"b.py:{i}: match {i}" for i in range(1, 6)]
        out = elide_matches("\n".join(lines))
        assert out.count("a.py:") == 10
        assert "… 5 more matches in a.py" in out
        assert "b.py:1: match 1" in out
        assert "more matches in b.py" not in out  # < 10 → no marker

    def test_windows_path_groups(self):
        lines = [rf"C:\proj\a.py:{i}: hit" for i in range(1, 13)]
        out = elide_matches("\n".join(lines))
        assert out.count(r"C:\proj\a.py:") == 10
        assert "… 2 more matches in C:\\proj\\a.py" in out

    def test_matches_strategy_small_raw(self):
        text = "one line of grep output"
        res = optimize(text, strategy="matches")
        assert res.compressed is False
        assert res.text == text

    def test_matches_strategy_large_footer(self):
        lines = [f"f.py:{i}: match_token {i} " + "p" * 20 for i in range(1, 151)]
        res = optimize("\n".join(lines), strategy="matches")
        assert res.compressed is True
        assert res.parser == "matches"
        assert "school ctx" in res.text


class TestFailOpen:
    def test_garbage_python_returns_result(self):
        text = ("def broken(:\n    ???\n" * 200)[:4500]
        res = optimize(text, filename="x.py")
        assert isinstance(res, OptimizeResult)
        assert len(FOOTER_ONE.findall(res.text)) <= 1

    def test_empty_string_passthrough(self):
        res = optimize("", filename="empty.txt")
        assert res.compressed is False
        assert res.text == ""


class TestHeuristicContract:
    PY_SAMPLE = '''\
import os
from dataclasses import dataclass

@dataclass
class User:
    id: int
    name: str

def fetch_user(user_id: int) -> User:
    """Fetch a user row by id."""
    row = db.query(user_id)
    if row is None:
        raise LookupError("missing")
    for key in row:
        audit(key)
    return User(id=row["id"], name=row["name"])

def transform(rows):
    total = 0
    for row in rows:
        total += 1
    return total
'''

    def test_signature_control_flow_kept(self):
        out = heuristic_skeleton(self.PY_SAMPLE, filename="sample.py")
        assert "import os" in out
        assert "def fetch_user(user_id: int) -> User:" in out
        assert '"""Fetch a user row by id."""' in out
        assert "id: int" in out
        assert "if row is None:" in out
        assert "raise LookupError" in out
        assert "for key in row:" in out
        assert "return User(" in out

    def test_body_statements_dropped_with_marker(self):
        out = heuristic_skeleton(self.PY_SAMPLE, filename="sample.py")
        assert "row = db.query" not in out
        assert "… transform() — 3 lines" in out

    def test_license_banner_dropped(self):
        text = (
            "# Copyright (c) 2026 Example Corp\n"
            "# Licensed under the MIT License\n"
            "# SPDX-License-Identifier: MIT\n"
            "# All rights reserved.\n"
            "import os\n"
            "print(os.getcwd())\n"
        )
        out = heuristic_skeleton(text, filename="lic.py")
        assert "Copyright" not in out
        assert "license banner" in out
        assert "import os" in out

    def test_single_line_license_dropped_silently(self):
        text = (
            "# Copyright (c) 2026 X\n"
            "import os\n"
            "print(os.getcwd())\n"
        )
        out = heuristic_skeleton(text, filename="lic1.py")
        assert "Copyright" not in out
        assert "license banner" not in out
        assert "import os" in out

    def test_unreferenced_import_dropped(self):
        text = (
            "import os\n"
            "import totally_unused_module\n"
            "print(os.getcwd())\n"
        )
        out = heuristic_skeleton(text, filename="refs.py")
        assert "totally_unused_module" not in out

    def test_sql_sample(self):
        text = (
            "SELECT u.id, u.name\n"
            "FROM users u\n"
            "JOIN orders o ON o.user_id = u.id\n"
            "-- noise comment\n"
            "-- more noise\n"
            "WHERE u.active = 1\n"
            "ORDER BY u.created_at;\n"
        )
        out = heuristic_skeleton(text, filename="q.sql")
        assert "SELECT u.id, u.name" in out
        assert "FROM users u" in out
        assert "WHERE u.active = 1" in out
        assert "-- …" in out  # elision marker with dash prefix
        assert "noise" not in out

    def test_yaml_sample(self):
        text = (
            "---\n"
            "server:\n"
            "  host: localhost\n"
            "  port: 8080\n"
            "  # noise one\n"
            "  # noise two\n"
            "  # noise three\n"
            "items:\n"
            + "\n".join(f"  - id: {i}" for i in range(12))
            + "\n"
        )
        out = heuristic_skeleton(text, filename="cfg.yaml")
        assert "server:" in out
        assert "host: localhost" in out
        assert "noise" not in out
        assert "…" in out

    def test_perf_100kb_under_1s(self):
        lines = [f"def fn_{i}(a, b):" for i in range(800)]
        for i in range(800):
            lines.append(f"    result_{i} = a + b + {i}")
            lines.append(f"    result_{i} = result_{i} * 2")
            lines.append(f"    return result_{i}")
        text = "\n".join(lines)
        assert len(text) > 50_000
        started = time.perf_counter()
        heuristic_skeleton(text, filename="big.py")
        # spec target ~50ms; loose bound for CI variance
        assert time.perf_counter() - started < 1.0


class TestFilenameRouting:
    def test_code_extension_routes_heuristic(self):
        text = _payload_lines(400)
        res = optimize(text, filename="blob.py")
        assert res.parser in {"heuristic", "tree-sitter-python"}

    def test_unknown_extension_routes_payload(self):
        text = _payload_lines(400)
        res = optimize(text, filename="blob.unknownext")
        assert res.parser == "payload"

    def test_comment_prefixes(self):
        assert comment_prefix("a.py") == "#"
        assert comment_prefix("a.ts") == "//"
        assert comment_prefix("a.sql") == "--"

    def test_language_maps(self):
        assert LANGUAGES[".py"] == "python"
        assert LANGUAGES[".tsx"] == "typescript"
        assert ".go" in CODE_EXTENSIONS
        assert ".sql" in CODE_EXTENSIONS
