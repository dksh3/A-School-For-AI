"""Contract tests for the Context Optimizer core (school.skeleton)."""

import re
import time

import pytest

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


PY_AST_SAMPLE = PY_SAMPLE_FOR_AST = TestHeuristicContract.PY_SAMPLE

tree_sitter = pytest.importorskip("tree_sitter", reason="ctx extra not installed")

GO_SAMPLE = """\
package main

import (
\t"fmt"
\t"os"
)

type Server struct {
\taddr string
\tport int
}

func NewServer(addr string) *Server {
\tport := 8080
\tif addr == "" {
\t\tpanic("missing addr")
\t}
\tlogStart(addr)
\treturn &Server{addr: addr, port: port}
}

func (s *Server) Addr() string {
\treturn s.addr
}
"""

RUST_SAMPLE = """\
use std::net::TcpListener;

pub struct Config {
\tpub port: u16,
}

impl Config {
\tpub fn new(port: u16) -> Self {
\t\tlet cfg = Config { port };
\t\tif cfg.port == 0 {
\t\t\tpanic!("bad port");
\t\t}
\t\tcfg
\t}
}
"""

JAVA_SAMPLE = """\
package com.example.app;

import java.util.List;

public class Loader {
\tprivate final int retries;

\tpublic Loader(int retries) {
\t\tthis.retries = retries;
\t}

\tpublic int first(List<Integer> items) {
\t\tint head = items.get(0);
\t\tif (head < 0) {
\t\t\tthrow new IllegalStateException("neg");
\t\t}
\t\ttrace(head);
\t\tskip(head);
\t\treturn head;
\t}
}
"""

C_SAMPLE = """\
#include <stdio.h>
#include <stdlib.h>

struct Point {
\tint x;
\tint y;
};

int add(int a, int b) {
\tint total = a + b;
\tif (total > 100) {
\t\treturn 100;
\t}
\treturn total;
}
"""

JS_SAMPLE = """\
import { readFileSync } from "node:fs";

export class Loader {
\tconstructor(opts) {
\t\tthis.opts = opts;
\t}

\tasync load(path) {
\t\tconst raw = readFileSync(path, "utf8");
\t\tif (!raw) {
\t\t\tthrow new Error("empty");
\t\t}
\t\tconst parsed = JSON.parse(raw);
\t\treturn parsed;
\t}
}

export const build = (cfg) => {
\tconst out = {};
\tfor (const key of cfg) {
\t\tout[key] = 1;
\t}
\treturn out;
};
"""

TS_SAMPLE = JS_SAMPLE + """
export interface LoaderOptions {
\tretry: number;
\tbase: string;
}
"""


def _run_ast(sample: str, language: str, package: str) -> str:
    pytest.importorskip(package, reason=f"{package} not installed")
    from school.skeleton import skeletonize_ast

    out = skeletonize_ast(sample, language)
    assert out is not None, f"skeletonize_ast returned None for {language}"
    return out


class TestAstBigSix:
    def test_python(self):
        out = _run_ast(PY_AST_SAMPLE, "python", "tree_sitter_python")
        assert "import os" in out
        assert "def fetch_user(user_id: int) -> User:" in out
        assert '"""Fetch a user row by id."""' in out
        assert "id: int" in out
        assert "if row is None:" in out
        assert "raise LookupError" in out
        assert "row = db.query" not in out
        assert "\u2026 transform() \u2014 3 lines" in out
        assert "def transform(rows):" in out

    def test_go(self):
        out = _run_ast(GO_SAMPLE, "go", "tree_sitter_go")
        assert "package main" in out
        assert '"fmt"' in out
        assert "type Server struct {" in out
        assert "addr string" in out
        assert "func NewServer(addr string) *Server {" in out
        if "if addr ==" in out:
            assert 'panic("missing addr")' in out
        assert "logStart(addr)" not in out

    def test_rust(self):
        out = _run_ast(RUST_SAMPLE, "rust", "tree_sitter_rust")
        assert "use std::net::TcpListener;" in out
        assert "pub struct Config {" in out
        assert "pub port: u16," in out
        assert "impl Config {" in out
        assert "pub fn new(port: u16) -> Self {" in out
        assert "let cfg = Config { port };" not in out

    def test_java(self):
        out = _run_ast(JAVA_SAMPLE, "java", "tree_sitter_java")
        assert "package com.example.app;" in out
        assert "import java.util.List;" in out
        assert "public class Loader {" in out
        assert "private final int retries;" in out
        assert "public Loader(int retries) {" in out
        assert "public int first(List<Integer> items) {" in out
        assert "int head = items.get(0);" not in out
        assert "trace(head)" not in out

    def test_c_and_cpp(self):
        for language, package in (("c", "tree_sitter_c"),
                                  ("cpp", "tree_sitter_cpp")):
            out = _run_ast(C_SAMPLE, language, package)
            assert "#include <stdio.h>" in out
            assert "struct Point {" in out
            assert "int x;" in out
            assert "int add(int a, int b) {" in out
            assert "int total = a + b;" not in out
            if "if total > 100:" in out or "if (total > 100)" in out:
                assert "return 100;" in out

    def test_javascript(self):
        out = _run_ast(JS_SAMPLE, "javascript", "tree_sitter_javascript")
        assert 'import { readFileSync } from "node:fs";' in out
        assert "export class Loader {" in out
        assert "constructor(opts) {" in out
        assert "async load(path) {" in out
        assert "const raw = readFileSync" not in out

    def test_typescript(self):
        out = _run_ast(TS_SAMPLE, "typescript", "tree_sitter_typescript")
        assert "export class Loader {" in out
        assert "interface LoaderOptions" in out
        assert "retry: number;" in out

    def test_garbage_returns_none(self):
        pytest.importorskip("tree_sitter_python")
        from school.skeleton import skeletonize_ast

        out = skeletonize_ast("def broken(:\n    ???" * 50, "python")
        assert out is None

    def test_ast_wired_into_optimize(self, monkeypatch):
        pytest.importorskip("tree_sitter_python")
        text = PY_AST_SAMPLE + "\n" + "\n".join(
            f"    filler_{i} = {i}" for i in range(400)
        )
        if estimate_tokens(strip_footer(text)) < CTX_THRESHOLD:
            text += "\n" + ("#" * 4)
        monkeypatch.delenv("SCHOOL_CTX", raising=False)
        res = optimize(text, filename="sample.py")
        assert res.compressed is True
        assert res.parser in {"tree-sitter-python", "heuristic"}
