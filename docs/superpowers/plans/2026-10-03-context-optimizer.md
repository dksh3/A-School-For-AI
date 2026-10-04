# Context Optimizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Skeletonize oversized tool results (MCP reads/greps + all native OpenCode tool outputs) to a contract-tested structural skeleton with a single `[school ctx: in→out tokens]` footer, keeping everything below the 1000-token threshold byte-identical.

**Architecture:** A pure-Python core (`school/skeleton.py`) owns thresholding, footer rules, heuristic line-based code skeletonization, JSON/payload shape-collapsing, grep-match elision, and (via optional tree-sitter extra) AST skeletonization for big-6 languages. Three surfaces consume it: the bridge (`skeleton` command), the MCP server (`school_read`/`school_grep` tools implemented in-process), and the OpenCode plugin (TypeScript hook that calls the bridge with a 2000ms cap and falls back to a TS twin heuristic). Every failure path fails open: raw text, no footer.

**Tech Stack:** Python 3.11+ (venv at `.venv`), tree-sitter 0.26.0 + 8 grammar wheels (optional `ctx` extra), pytest 9.1.1, ruff 0.16.7, TypeScript plugin embedded as a string in `school/plugin_source.py`, Node 24 (native TS type-stripping) for live harness.

**Spec:** docs/superpowers/specs/2026-10-03-context-optimizer-design.md

## Global Constraints

- Threshold: `est = ceil(chars/4)`; `< 1000` tokens → pass raw untouched, NO marker/footer; `≥ 1000` → compress + append exactly ONE footer `[school ctx: <in>→<out> tokens]`.
- Footer excluded from downstream estimates (strip before re-estimating); never expand: if `tokens_out >= tokens_in` → fail open with original text.
- Kill switch `SCHOOL_CTX=0` → passthrough raw (independent of `SCHOOL_HOOKS=0`).
- Fail open everywhere: any exception → original text, no footer. Error messages pass raw. Never modify tool INPUTS. One footer max per result.
- Heuristic path: no I/O, no network, target ~50ms (test bound <1.0s for 100KB).
- Bridge AST attempt capped at `CTX_TIMEOUT_MS=2000` (separate from recall budget); total failure → TS fallback → fail open.
- Naming: everything `school_*`; MCP tools snake_case. Plugin TS imports only `node:child_process|util|path|fs` (no npm deps) and plugin tool surface stays 13 (school_read/school_grep are MCP-only).
- Python style: ruff line-length 100, select E,W,F,I,B,UP,SIM — NO new errors on touched files (plugin_source.py has pre-existing E501s inside the embedded TS template; keep NEW physical lines ≤100 chars).
- Test battery must stay green (baseline ~2516 tests): `& ".venv\Scripts\python.exe" -m pytest -q --no-header -p no:cacheprovider`.
- Working directory: repo root `C:\Users\dex34\OneDrive\Documents\Teach` (Windows, PowerShell; no `rg` — use grep tool). Python: `& ".venv\Scripts\python.exe"`.
- Commits: one per task (or sub-batch), style matches repo: `feat: ...`, `test: ...`, `fix: ...`.

---

### Task 1: Core skeleton module (primitives, optimize dispatch, payload, matches, heuristic)

**Files:**
- Create: `school/skeleton.py`
- Test: `tests/unit/test_school_skeleton.py`

**Interfaces:**
- Consumes: nothing (leaf module; only stdlib).
- Produces (used by ALL later tasks):
  - `CTX_THRESHOLD: int = 1000`, `CTX_TIMEOUT_MS: int = 2000`, `FOOTER_RE: re.Pattern[str]`
  - `estimate_tokens(text: str) -> int`
  - `strip_footer(text: str) -> str`
  - `make_footer(tokens_in: int, tokens_out: int) -> str`
  - `comment_prefix(filename: str) -> str`
  - `LANGUAGES: dict[str, str]`, `CODE_EXTENSIONS: frozenset[str]`
  - `@dataclass OptimizeResult(text: str, tokens_in: int, tokens_out: int, compressed: bool, parser: str)` — parser ∈ {`passthrough`, `heuristic`, `payload`, `matches`} (Task 2 adds `tree-sitter-<lang>`)
  - `optimize(text: str, filename: str = "", strategy: str = "auto") -> OptimizeResult`
  - `skeletonize_payload(text: str, filename: str = "") -> str`
  - `elide_matches(text: str) -> str`
  - `heuristic_skeleton(text: str, filename: str = "") -> str`
  - `skeletonize_ast(text: str, language: str) -> str | None` — Task 2 adds; Task 1 defines a stub returning `None` so `optimize` already calls it.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_school_skeleton.py`:

```python
"""Contract tests for the Context Optimizer core (school.skeleton)."""

import math
import re
import time

from school.skeleton import (
    CTX_THRESHOLD,
    CODE_EXTENSIONS,
    FOOTER_RE,
    LANGUAGES,
    OptimizeResult,
    comment_prefix,
    elide_matches,
    estimate_tokens,
    heuristic_skeleton,
    make_footer,
    optimize,
    skeletonize_ast,
    skeletonize_payload,
    strip_footer,
)

FOOTER_ONE = re.compile(r"\[school ctx: \d+→\d+ tokens\]")


def _payload_lines(n: int) -> str:
    return "\n".join('{"k": "some value %d"}' % i for i in range(n))


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
            lines.append('"unique string alpha %d":' % i)
            lines.append("%d" % (i * 7919))
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
        lines = [r"C:\proj\a.py:%d: hit" % i for i in range(1, 13)]
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
            + "\n".join("  - id: %d" % i for i in range(12))
            + "\n"
        )
        out = heuristic_skeleton(text, filename="cfg.yaml")
        assert "server:" in out
        assert "host: localhost" in out
        assert "noise" not in out
        assert "…" in out

    def test_perf_100kb_under_1s(self):
        lines = ["def fn_%d(a, b):" % i for i in range(400)]
        for i in range(400):
            lines.append("    result_%d = a + b + %d" % (i, i))
            lines.append("    result_%d = result_%d * 2" % (i, i))
            lines.append("    return result_%d" % i)
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/unit/test_school_skeleton.py -q --no-header -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError: No module named 'school.skeleton'`

- [ ] **Step 3: Write minimal implementation**

Create `school/skeleton.py`:

```python
"""Context Optimizer: skeletonize oversized tool results.

Contract: below CTX_THRESHOLD tokens the input is returned byte-identical
with no marker. At or above it, a structural skeleton is produced and one
``[school ctx: in->out tokens]`` footer is appended. Every failure path
fails open: original text, no footer.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass

CTX_THRESHOLD = 1000
CTX_TIMEOUT_MS = 2000
FOOTER_RE = re.compile(r"\[school ctx: \d+→\d+ tokens\]\s*$")

LANGUAGES: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".hxx": "cpp",
}

CODE_EXTENSIONS = frozenset(
    {
        ".py", ".pyi", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx",
        ".go", ".rs", ".java", ".c", ".h", ".cpp", ".cc", ".cxx",
        ".hpp", ".hh", ".hxx", ".sh", ".bash", ".zsh", ".rb", ".php",
        ".cs", ".kt", ".swift", ".sql", ".yaml", ".yml", ".toml",
        ".ini", ".cfg", ".conf", ".lua", ".pl", ".r", ".scala",
        ".ex", ".exs", ".hs", ".clj", ".cljs", ".graphql", ".proto", ".tf",
    }
)

_SLASH_EXTS = frozenset(
    {
        ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx",
        ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".go", ".rs",
        ".java", ".kt", ".cs", ".swift", ".scala", ".php",
    }
)
_DASH_EXTS = frozenset({".sql", ".lua", ".pl"})

_NOISE_WORDS = frozenset(
    {
        "import", "from", "as", "require", "const", "let", "var", "use",
        "using", "include", "package", "export", "default", "async",
        "await", "type",
    }
)

LICENSE_RE = re.compile(
    r"copyright|licensed?\s+under|spdx-|all\s+rights\s+reserved",
    re.IGNORECASE,
)
IMPORT_RE = re.compile(
    r"^\s*(import\b|from\s+\S+\s+import\b|require\s*\(|use\s|using\s"
    r"|include\s|package\s+\w|export\s+.*\sfrom\s"
    r"|#\s*(include|define|if|ifdef|ifndef|pragma)\b)"
)
DECL_RE = re.compile(
    r"^\s*(?:(?:export|default|async|pub|public|private|protected|static"
    r"|final|abstract|override|virtual)\s+)*"
    r"(def|class|function|fn|func|struct|enum|trait|impl|interface|type"
    r"|namespace|module)\s+[A-Za-z_$]"
)
ARROW_CONST_RE = re.compile(
    r"^\s*(export\s+)?(const|let|var)\s+[\w$]+\s*=.*=>"
)
CONTROL_RE = re.compile(
    r"^\s*(if|else|elif|for|while|do|switch|case|default|try|except"
    r"|catch|finally|return|yield|break|continue|match|guard|when"
    r"|raise|throw|assert)\b"
)
CLOSER_RE = re.compile(r"^\s*[}\])]+;?\s*$")
SIG_RE = re.compile(r"^\s*[A-Za-z_][\w.]*\s*:(\s|$)")
SQL_KEEP_RE = re.compile(
    r"^\s*(select|from|where|group\s+by|order\s+by|having|limit|offset"
    r"|join|left|right|inner|outer|full|union|values|insert\s+into"
    r"|update|delete\s+from|create|alter|drop|with|returning|set|into"
    r"|on|begin|end|commit|rollback)\b",
    re.IGNORECASE,
)
YAML_KEY_RE = re.compile(r"^[A-Za-z_][\w.-]*\s*:")
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
QUOTED_RE = re.compile(r"\"[^\"]*\"|'[^']*'")


@dataclass
class OptimizeResult:
    text: str
    tokens_in: int
    tokens_out: int
    compressed: bool
    parser: str


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / 4)


def strip_footer(text: str) -> str:
    return FOOTER_RE.sub("", text).rstrip("\n")


def make_footer(tokens_in: int, tokens_out: int) -> str:
    return f"[school ctx: {tokens_in}→{tokens_out} tokens]"


def suffix(filename: str) -> str:
    name = filename.lower()
    dot = name.rfind(".")
    if dot <= 0:
        return ""
    return name[dot:]


def comment_prefix(filename: str) -> str:
    ext = suffix(filename)
    if ext in _SLASH_EXTS:
        return "//"
    if ext in _DASH_EXTS:
        return "--"
    return "#"


def _passthrough(text: str, tokens_in: int, original: str) -> OptimizeResult:
    return OptimizeResult(
        text=original, tokens_in=tokens_in, tokens_out=tokens_in,
        compressed=False, parser="passthrough",
    )


def skeletonize_ast(text: str, language: str) -> str | None:
    """AST skeleton; returns None when unavailable or in doubt (Task 2)."""
    return None


def _classify_lines(lines: list[str]) -> list[str]:
    kinds: list[str] = []
    mode = ""
    for line in lines:
        stripped = line.strip()
        if mode:
            kinds.append("string_cont")
            for closer in (mode,):
                if closer in stripped:
                    mode = ""
            continue
        if not stripped:
            kinds.append("blank")
            continue
        if stripped.startswith(("#", "//", "/*", "*", "--")):
            kinds.append("comment")
            continue
        code = QUOTED_RE.sub('""', line)
        open_dq = code.count('"""')
        open_sq = code.count("'''")
        tick = code.count("`")
        if open_dq % 2 == 1:
            kinds.append("string_first")
            mode = '"""'
        elif open_sq % 2 == 1:
            kinds.append("string_first")
            mode = "'''"
        elif tick % 2 == 1:
            kinds.append("string_first")
            mode = "`"
        else:
            kinds.append("code")
    return kinds


def _is_import(line: str) -> bool:
    return IMPORT_RE.search(line) is not None


def _keep_class(
    line: str, ext: str, kind: str
) -> str:
    if kind == "comment":
        return "comment"
    stripped = line.strip()
    if not stripped:
        return "blank"
    if _is_import(line):
        return "import"
    if re.match(r"^\s*@\w", line):
        return "decorator"
    if DECL_RE.match(line) or ARROW_CONST_RE.match(line):
        return "decl"
    if CONTROL_RE.match(line):
        return "control"
    if CLOSER_RE.match(line):
        return "closer"
    if ext in {".sql", ".graphql", ".gql"} and SQL_KEEP_RE.match(line):
        return "sql"
    if ext in {".yaml", ".yml"} and YAML_KEY_RE.match(line):
        return "yaml"
    if SIG_RE.match(line):
        return "sig"
    return "body"


def _decl_label(line: str) -> str:
    m = DECL_RE.match(line)
    if m:
        word = m.group(1)
        rest = line[m.end():].lstrip()
        name = re.match(r"[A-Za-z_$][\w$]*", rest)
        base = name.group(0) if name else ""
        if word in {"def", "function", "fn", "func"} and base:
            return f"{base}()"
        if base:
            return base
        return word
    m2 = ARROW_CONST_RE.match(line)
    if m2:
        rest = line.lstrip()
        rest = rest.removeprefix("export ").lstrip()
        nm = re.match(r"(?:const|let|var)\s+([\w$]+)", rest)
        if nm:
            return f"{nm.group(1)}()"
    return "body"


def _import_names(line: str) -> set[str]:
    return {
        w for w in IDENT_RE.findall(line)
        if w not in _NOISE_WORDS and len(w) > 1
    }


def _depth_delta(line: str) -> int:
    cleaned = QUOTED_RE.sub("", line)
    cleaned = re.sub(r"(#|//|--).*$", "", cleaned)
    return cleaned.count("(") + cleaned.count("[") + cleaned.count("{") - (
        cleaned.count(")") + cleaned.count("]") + cleaned.count("}")
    )


def heuristic_skeleton(text: str, filename: str = "") -> str:
    """Line-based structural skeleton for code text (no I/O)."""
    ext = suffix(filename)
    prefix = comment_prefix(filename)
    lines = text.splitlines()
    if not lines:
        return text
    kinds = _classify_lines(lines)

    # License banner + header comments (first comment block only).
    drop: list[bool] = [False] * len(lines)
    first_block = True
    header_comments = 0
    block_sizes: list[tuple[int, int]] = []
    i = 0
    while i < len(lines):
        if kinds[i] != "comment":
            if first_block and any(k == "code" for k in kinds[:i]):
                first_block = False
            i += 1
            continue
        start = i
        while i < len(lines) and kinds[i] == "comment":
            i += 1
        block = lines[start:i]
        if first_block and not any(
            k == "code" for k in kinds[:start]
        ):
            if any(LICENSE_RE.search(c) for c in block):
                for j in range(start, i):
                    drop[j] = True
                block_sizes.append((start, i - start))
            else:
                keep = 0
                for j in range(start, i):
                    if keep < 3:
                        keep += 1
                    else:
                        drop[j] = True
                if i - start - keep >= 2:
                    block_sizes.append((start, i - start - keep))
            header_comments = i
            first_block = False
        else:
            for j in range(start, i):
                drop[j] = True
            if i - start >= 2:
                block_sizes.append((start, i - start))

    # Import-name reference set (from non-import lines).
    refset: set[str] = set()
    for idx, line in enumerate(lines):
        if kinds[idx] == "code" and not _is_import(line):
            refset |= set(IDENT_RE.findall(line))

    # Pass 1: decide keep/drop per line.
    kept_depth = 0
    label = "body"
    keep_flags: list[bool] = [False] * len(lines)
    for idx, line in enumerate(lines):
        kind = kinds[idx]
        if drop[idx]:
            continue
        if kind == "blank":
            keep_flags[idx] = True
            continue
        if kind == "string_first":
            keep_flags[idx] = True
            continue
        if kind == "string_cont":
            continue
        if kind == "comment":
            keep_flags[idx] = header_comments > 0 and idx < header_comments
            continue
        cls = _keep_class(line, ext, "code")
        if kept_depth > 0:
            keep_flags[idx] = True
            kept_depth += _depth_delta(line)
            continue
        if cls in {"import", "decorator", "decl", "control", "closer",
                   "sql", "yaml", "sig"}:
            if cls == "import" and not (_import_names(line) & refset):
                continue  # unreferenced import → dropped
            keep_flags[idx] = True
            kept_depth += _depth_delta(line)
            if cls == "decl":
                label = _decl_label(line)
            continue
        # body line while depth == 0 → dropped

    # Pass 2: emit with run markers.
    out: list[str] = []
    run: list[int] = []
    run_label = label

    def flush(j: int) -> None:
        nonlocal run, run_label
        if run:
            n = len(run)
            if n >= 2:
                out.append(f"{prefix} … {run_label} — {n} lines")
            run = []
        run_label = label

    pending_blank = False
    prev_was_string_first = False
    for idx, line in enumerate(lines):
        if drop[idx]:
            continue
        if not keep_flags[idx]:
            if kinds[idx] == "blank":
                continue
            if run and run_label == "body" and label != "body":
                run_label = label
            run.append(idx)
            if run and kinds[run[-1]] == "string_cont" and len(run) == 1 \
                    and prev_was_string_first:
                run_label = "docstring"
            prev_was_string_first = False
            continue
        flush(idx)
        if kinds[idx] == "blank":
            if pending_blank:
                continue
            pending_blank = True
            out.append("")
        else:
            pending_blank = False
            out.append(line)
            if kinds[idx] == "decl":
                label = _decl_label(line)
            prev_was_string_first = kinds[idx] == "string_first"
    flush(len(lines))
    while out and not out[-1]:
        out.pop()
    return "\n".join(out)


def _shape(line: str) -> str:
    s = line.strip()
    if not s:
        return ""
    if re.fullmatch(r"\"(?:[^\"\\]|\\.)*\",?", s) or re.fullmatch(
        r"'(?:[^'\\]|\\.)*',?", s
    ):
        return "S"
    if re.fullmatch(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?,?", s):
        return "N"
    if re.fullmatch(r"(true|false|null|nil|undefined),?", s, re.IGNORECASE):
        return "K"
    if s[0] in "{[":
        return "B"
    if s[0] in "}]":
        return "C"
    if re.fullmatch(r"[\w$.-]+(?:\s*:\s*.+)?,?", s):
        return "I"
    return "O"


def skeletonize_payload(text: str, filename: str = "") -> str:
    """Shape-collapse for JSON/tool payloads."""
    prefix = comment_prefix(filename)
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    pending_blank = False
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            pending_blank = True
            i += 1
            continue
        shape = _shape(line)
        j = i
        while j < len(lines) and lines[j].strip() and _shape(lines[j]) == shape:
            j += 1
        run_len = j - i
        if run_len >= 6:
            if pending_blank:
                out.append("")
                pending_blank = False
            out.append(lines[i])
            out.append(lines[i + 1])
            out.append(
                f"{prefix} … repeated block — {run_len - 2} lines"
            )
        else:
            for k in range(i, j):
                if pending_blank:
                    out.append("")
                    pending_blank = False
                out.append(lines[k])
        i = j
    return "\n".join(out)


def elide_matches(text: str) -> str:
    """Keep first 10 matches per file; elide the rest with a marker."""
    lines = text.splitlines()
    out: list[str] = []
    cur_path: str | None = None
    cur_total = 0
    cur_kept = 0

    def flush() -> None:
        nonlocal cur_path, cur_total, cur_kept
        if cur_path is not None and cur_total > cur_kept:
            out.append(f"# … {cur_total - cur_kept} more matches in {cur_path}")
        cur_path = None
        cur_total = 0
        cur_kept = 0

    for line in lines:
        m = re.match(r"^(.+?):(\d+):", line)
        path = m.group(1) if m else ""
        if path != cur_path:
            flush()
            cur_path = path
        cur_total += 1
        if cur_kept < 10:
            out.append(line)
            cur_kept += 1
    flush()
    return "\n".join(out)


def optimize(
    text: str, filename: str = "", strategy: str = "auto"
) -> OptimizeResult:
    """Apply the Context Optimizer contract to *text*."""
    original = text
    body = strip_footer(text)
    tokens_in = estimate_tokens(body)
    if os.environ.get("SCHOOL_CTX") == "0" or tokens_in < CTX_THRESHOLD:
        return _passthrough(body, tokens_in, original)
    try:
        if strategy == "matches":
            out = elide_matches(body)
            parser = "matches"
        else:
            ext = suffix(filename)
            out = None
            parser = ""
            if ext in LANGUAGES and strategy in {"auto", "code"}:
                language = LANGUAGES[ext]
                out = skeletonize_ast(body, language)
                if out is not None:
                    parser = f"tree-sitter-{language}"
            if out is None:
                if ext in CODE_EXTENSIONS or strategy == "code":
                    out = heuristic_skeleton(body, filename)
                    parser = "heuristic"
                else:
                    out = skeletonize_payload(body, filename)
                    parser = "payload"
        tokens_out = estimate_tokens(out)
        if tokens_out >= tokens_in:
            return _passthrough(body, tokens_in, original)
        return OptimizeResult(
            text=f"{out}\n\n{make_footer(tokens_in, tokens_out)}",
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            compressed=True,
            parser=parser,
        )
    except Exception:
        return _passthrough(body, tokens_in, original)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/unit/test_school_skeleton.py -q --no-header -p no:cacheprovider`
Expected: all PASS. If contract tests fail (marker wording, keep/drop rules), fix `heuristic_skeleton`/`skeletonize_payload` until they pass — the assertions are the spec.

- [ ] **Step 5: Ruff + commit**

Run: `& ".venv\Scripts\python.exe" -m ruff check school/skeleton.py tests/unit/test_school_skeleton.py`
Expected: no errors.

```bash
git add school/skeleton.py tests/unit/test_school_skeleton.py
git commit -m "feat: context optimizer core skeleton module"
```

---

### Task 2: tree-sitter AST skeleton + `ctx` extra + big-6 contract tests

**Files:**
- Modify: `school/skeleton.py` (replace `skeletonize_ast` stub, add AST tables + walker)
- Modify: `pyproject.toml` (add `ctx` extra, extend `all`)
- Test: `tests/unit/test_school_skeleton.py` (append AST classes)

**Interfaces:**
- Consumes: Task 1's `OptimizeResult`, `optimize` already calls `skeletonize_ast(body, language)` before the heuristic — no signature change.
- Produces: `skeletonize_ast(text: str, language: str) -> str | None` (None = unavailable/doubt → `optimize` falls back to heuristic); pyproject extra `school[ctx]`.

- [ ] **Step 1: Add the pyproject `ctx` extra**

In `pyproject.toml`, inside `[project.optional-dependencies]`, add:

```toml
ctx = [
    "tree-sitter==0.26.0",
    "tree-sitter-python==0.25.0",
    "tree-sitter-javascript==0.25.0",
    "tree-sitter-typescript==0.23.2",
    "tree-sitter-go==0.25.0",
    "tree-sitter-rust==0.24.2",
    "tree-sitter-java==0.23.5",
    "tree-sitter-c==0.24.2",
    "tree-sitter-cpp==0.23.4",
]
```

And change `all = ["school[dev,web,semantic,mcp]"]` → `all = ["school[dev,web,semantic,mcp,ctx]"]`.

- [ ] **Step 2: Install the wheels into the venv**

Run: `& ".venv\Scripts\python.exe" -m pip install "tree-sitter==0.26.0" "tree-sitter-python==0.25.0" "tree-sitter-javascript==0.25.0" "tree-sitter-typescript==0.23.2" "tree-sitter-go==0.25.0" "tree-sitter-rust==0.24.2" "tree-sitter-java==0.23.5" "tree-sitter-c==0.24.2" "tree-sitter-cpp==0.23.4"`
Expected: installs 9 wheels (dry-run previously verified all resolve as win amd64 abi3).

- [ ] **Step 3: Write the failing AST contract tests**

Append to `tests/unit/test_school_skeleton.py`:

```python
import pytest

tree_sitter = pytest.importorskip("tree_sitter", reason="ctx extra not installed")

PY_AST_SAMPLE = PY_SAMPLE_FOR_AST = TestHeuristicContract.PY_SAMPLE

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
        assert "… transform() — 3 lines" in out
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
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/unit/test_school_skeleton.py -q --no-header -p no:cacheprovider -k "Ast or ast"`
Expected: FAIL (`skeletonize_ast returned None` — stub still returns None, or importorskip passes but asserts fail).

- [ ] **Step 5: Implement `skeletonize_ast`**

In `school/skeleton.py`, add imports at top (`import importlib`, `from tree_sitter import Language, Parser` must NOT be top-level — keep tree-sitter optional) and replace the stub with:

```python
_AST_PACKAGES = {
    "python": "tree_sitter_python",
    "javascript": "tree_sitter_javascript",
    "typescript": "tree_sitter_typescript",
    "go": "tree_sitter_go",
    "rust": "tree_sitter_rust",
    "java": "tree_sitter_java",
    "c": "tree_sitter_c",
    "cpp": "tree_sitter_cpp",
}
_LANGUAGE_CACHE: dict[str, object] = {}

_COMMENT_TYPES = {
    "python": {"comment"},
    "javascript": {"comment"},
    "typescript": {"comment"},
    "go": {"comment"},
    "rust": {"line_comment", "block_comment"},
    "java": {"line_comment", "block_comment"},
    "c": {"comment"},
    "cpp": {"comment"},
}
_IMPORT_TYPES = {
    "python": {"import_statement", "import_from_statement", "package_clause"},
    "javascript": {"import_statement"},
    "typescript": {"import_statement"},
    "go": {"import_declaration", "package_clause"},
    "rust": {"use_declaration"},
    "java": {"import_declaration", "package_declaration"},
    "c": {"preproc_include", "preproc_def"},
    "cpp": {"preproc_include", "preproc_def"},
}
_DECL_TYPES = {
    "python": {"function_definition", "class_definition", "decorated_definition"},
    "javascript": {
        "function_declaration", "generator_function_declaration",
        "class_declaration", "method_definition", "lexical_declaration",
        "interface_declaration", "type_alias_declaration", "enum_declaration",
        "export_statement",
    },
    "typescript": {
        "function_declaration", "generator_function_declaration",
        "class_declaration", "method_definition", "lexical_declaration",
        "interface_declaration", "type_alias_declaration", "enum_declaration",
        "export_statement",
    },
    "go": {"function_declaration", "method_declaration", "type_declaration"},
    "rust": {
        "function_item", "struct_item", "enum_item", "trait_item",
        "impl_item", "mod_item", "const_item", "static_item",
    },
    "java": {
        "class_declaration", "interface_declaration", "enum_declaration",
        "method_declaration", "constructor_declaration", "record_declaration",
    },
    "c": {"function_definition", "struct_specifier", "union_specifier", "type_definition"},
    "cpp": {
        "function_definition", "struct_specifier", "class_specifier",
        "union_specifier", "type_definition",
    },
}
_CTRL_TYPES = {
    "python": {
        "if_statement", "for_statement", "while_statement", "try_statement",
        "return_statement", "raise_statement", "match_statement",
        "with_statement", "elif_clause", "else_clause", "except_clause",
        "finally_clause", "assert_statement", "break_statement",
        "continue_statement",
    },
    "javascript": {
        "if_statement", "for_statement", "for_in_statement", "while_statement",
        "do_statement", "switch_statement", "try_statement", "return_statement",
        "throw_statement", "switch_case", "switch_default", "break_statement",
        "continue_statement",
    },
    "typescript": {
        "if_statement", "for_statement", "for_in_statement", "while_statement",
        "do_statement", "switch_statement", "try_statement", "return_statement",
        "throw_statement", "switch_case", "switch_default", "break_statement",
        "continue_statement",
    },
    "go": {
        "if_statement", "for_statement", "return_statement",
        "switch_statement", "select_statement", "case_clause",
    },
    "rust": {
        "if_expression", "for_expression", "while_expression",
        "loop_expression", "match_expression", "return_expression",
        "arm", "break_expression", "continue_expression",
    },
    "java": {
        "if_statement", "for_statement", "while_statement", "do_statement",
        "switch_statement", "try_statement", "return_statement",
        "throw_statement", "switch_block_statement_group", "switch_label",
        "break_statement", "continue_statement",
    },
    "c": {
        "if_statement", "for_statement", "while_statement", "do_statement",
        "switch_statement", "return_statement", "case_statement",
        "break_statement", "continue_statement",
    },
    "cpp": {
        "if_statement", "for_statement", "for_range_loop", "while_statement",
        "do_statement", "switch_statement", "return_statement",
        "case_statement", "break_statement", "continue_statement",
    },
}
_BODY_TYPES = {
    "python": {"block"},
    "javascript": {"statement_block", "class_body"},
    "typescript": {"statement_block", "class_body", "object_type", "interface_body"},
    "go": {"block", "declaration_list", "field_declaration_list"},
    "rust": {"block", "declaration_list", "field_declaration_list",
             "enum_variant_list", "ordered_field_declaration_list"},
    "java": {"class_body", "block", "enum_body", "interface_body", "record_body"},
    "c": {"compound_statement", "field_declaration_list"},
    "cpp": {"compound_statement", "field_declaration_list"},
}
_KEEP_WHOLE_TYPES = {
    "python": set(),
    "javascript": {"field_definition"},
    "typescript": {"field_definition", "public_field_definition", "method_signature"},
    "go": {"field_declaration"},
    "rust": {"field_declaration", "enum_variant"},
    "java": {"field_declaration", "constant_declaration", "enum_constant"},
    "c": {"field_declaration"},
    "cpp": {"field_declaration"},
}
_LABEL_TYPES = {
    "switch_case", "switch_default", "case_statement", "switch_label",
    "switch_block_statement_group", "arm",
}
_IDENT_TYPES = {
    "identifier", "type_identifier", "field_identifier",
    "property_identifier", "name",
}
_SKIP_DEEP = {
    "decorator", "identifier", "type_identifier", "property_identifier",
    "field_identifier", "comment", "line_comment", "block_comment",
    "primitive_type", "type", "parameters", "formal_parameters",
    "type_parameters", "arguments", "argument_list", "parameter_list",
    "modifiers",
}


def _load_language(name: str) -> object | None:
    if name in _LANGUAGE_CACHE:
        return _LANGUAGE_CACHE[name]
    pkg = _AST_PACKAGES.get(name)
    if pkg is None:
        return None
    try:
        from tree_sitter import Language

        mod = importlib.import_module(pkg)
        lang = Language(mod.language())
    except Exception:
        lang = None
    _LANGUAGE_CACHE[name] = lang
    return lang


def _first_ident(node: object) -> str | None:
    for child in node.children:
        if child.type in _IDENT_TYPES:
            return child.text.decode("utf-8", "replace")
    for child in node.children:
        found = _first_ident(child)
        if found:
            return found
    return None


def _decl_name(node: object) -> str:
    if node.type == "decorated_definition":
        for child in node.children:
            if child.type != "decorator":
                return _decl_name(child)
        return "body"
    named = node.child_by_field_name("name")
    if named is not None:
        ident = _first_ident(named)
        if ident:
            if re.search(r"function|method|constructor", node.type):
                return f"{ident}()"
            return ident
    ident = _first_ident(node)
    if ident and re.search(r"function|method|constructor", node.type):
        return f"{ident}()"
    if ident:
        return ident
    return "body"


def _find_body(node: object, depth: int = 0) -> object | None:
    if depth > 5:
        return None
    for child in node.children:
        if child.type in _BODY_TYPES[_CUR_LANG[0]]:
            return child
    for child in node.children:
        if child.type in _SKIP_DEEP:
            continue
        found = _find_body(child, depth + 1)
        if found is not None:
            return found
    return None


_CUR_LANG: list[str] = ["python"]


def skeletonize_ast(text: str, language: str) -> str | None:
    """AST skeleton via tree-sitter; None = unavailable or parse doubt."""
    try:
        lang = _load_language(language)
        if lang is None:
            return None
        from tree_sitter import Parser

        src = text.encode("utf-8")
        parser = Parser(lang)
        tree = parser.parse(src)
        root = tree.root_node
        if root.has_error:
            return None
        _CUR_LANG[0] = language
        parts: list[str] = []
        ctx = {"src": src, "parts": parts, "lang": language}
        _walk_children(ctx, list(root.children), None)
        return _finalize(parts)
    except Exception:
        return None


def _emit(ctx: dict, start: int, end: int, indent_first: int = -1) -> None:
    chunk = ctx["src"][start:end].decode("utf-8", "replace")
    lines = chunk.splitlines()
    if not lines:
        return
    while lines and not lines[-1].strip():
        lines.pop()
    if indent_first > 0 and lines:
        lines[0] = " " * indent_first + lines[0].lstrip()
    ctx["parts"].extend(lines)


def _emit_marker(ctx: dict, label: str, n: int) -> None:
    prefix = "#" if ctx["lang"] == "python" else "//"
    ctx["parts"].append(f"{prefix} … {label} — {n} lines")


def _finalize(parts: list[str]) -> str:
    out: list[str] = []
    pending_blank = False
    for line in parts:
        if not line.strip():
            pending_blank = True
            continue
        if pending_blank and out:
            out.append("")
        pending_blank = False
        out.append(line)
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out)


def _is_string_like(node: object) -> bool:
    if "string" in node.type:
        return True
    return bool(node.children) and "string" in node.children[0].type


def _walk_children(ctx: dict, children: list, label: str | None) -> str | None:
    lang = ctx["lang"]
    imports = _IMPORT_TYPES[lang]
    decls = _DECL_TYPES[lang]
    ctrls = _CTRL_TYPES[lang]
    bodies = _BODY_TYPES[lang]
    keep_whole = _KEEP_WHOLE_TYPES[lang]
    comments = _COMMENT_TYPES[lang]
    run: list = []
    seen_code = False

    def flush() -> None:
        if not run:
            return
        span = ctx["src"][run[0].start_byte:run[-1].end_byte].count(b"\n") + 1
        if span >= 2:
            _emit_marker(ctx, label or "body", span)
        run.clear()

    for child in children:
        if child.type in comments:
            flush()
            continue
        if not seen_code and _is_string_like(child):
            start_line_end = child.start_byte + (
                ctx["src"][child.start_byte:].find(b"\n") or 1
            )
            _emit(ctx, child.start_byte, min(start_line_end, child.end_byte))
            tail = ctx["src"][child.start_byte:child.end_byte].count(b"\n")
            if tail >= 2:
                _emit_marker(ctx, "docstring", tail)
            seen_code = True
            continue
        if child.type in imports or child.type in keep_whole:
            flush()
            _emit(ctx, child.start_byte, child.end_byte)
            seen_code = True
            continue
        if child.type in decls or child.type in ctrls or child.type in bodies:
            flush()
            label = _walk(ctx, child, label)
            seen_code = True
            continue
        if child.type == "ERROR":
            flush()
            return label
        first_line_end = ctx["src"][child.start_byte:].find(b"\n")
        first = (
            ctx["src"][child.start_byte:child.start_byte + first_line_end + 1]
            .decode("utf-8", "replace")
        )
        if re.match(r"^[A-Za-z_][\w.]*\s*:", first):
            flush()
            _emit(ctx, child.start_byte, child.end_byte)
            seen_code = True
            continue
        run.append(child)
        seen_code = True
    flush()
    return label


def _walk(ctx: dict, node: object, label: str | None) -> str | None:
    lang = ctx["lang"]
    imports = _IMPORT_TYPES[lang]
    decls = _DECL_TYPES[lang]
    ctrls = _CTRL_TYPES[lang]
    bodies = _BODY_TYPES[lang]
    keep_whole = _KEEP_WHOLE_TYPES[lang]
    comments = _COMMENT_TYPES[lang]
    if node.type in comments:
        return label
    if node.type in imports or node.type in keep_whole:
        _emit(ctx, node.start_byte, node.end_byte)
        return label
    if node.type in decls:
        new_label = _decl_name(node)
        body = _find_body(node)
        if body is None:
            _emit(ctx, node.start_byte, node.end_byte)
            return new_label
        header_end = body.start_byte
        if header_end > node.start_byte and ctx["src"][header_end - 1:header_end] == b"{":
            header_end += 1
        _emit(ctx, node.start_byte, header_end, indent_first=node.start_point.column)
        _walk_children(ctx, list(body.children), new_label)
        if body.end_byte > body.start_byte and ctx["src"][body.end_byte - 1:body.end_byte] == b"}":
            close_start = ctx["src"].rfind(b"\n", body.start_byte, body.end_byte - 1)
            if close_start == -1:
                close_start = body.end_byte - 1
            _emit(ctx, close_start + 1, body.end_byte)
        return new_label
    if node.type in ctrls:
        block = None
        for child in node.children:
            if child.type in bodies:
                block = child
                break
        if block is None:
            if node.type in _LABEL_TYPES:
                first_line_end = ctx["src"][node.start_byte:].find(b"\n")
                end = (
                    node.start_byte + first_line_end + 1
                    if first_line_end != -1
                    else node.end_byte
                )
                _emit(ctx, node.start_byte, end)
                kids = [
                    c for c in node.children
                    if c.start_byte >= end
                    and c.type not in comments
                ]
                _walk_children(ctx, kids, label)
            else:
                _emit(ctx, node.start_byte, node.end_byte)
            return label
        header_end = block.start_byte
        if header_end > node.start_byte and ctx["src"][header_end - 1:header_end] in (b"{", b":"):
            header_end += 1
        _emit(ctx, node.start_byte, header_end, indent_first=node.start_point.column)
        if node.type in _LABEL_TYPES:
            first_line_end = ctx["src"][block.start_byte:].find(b"\n")
            rel_end = (
                block.start_byte + first_line_end + 1
                if first_line_end != -1
                else block.end_byte
            )
            _emit(ctx, block.start_byte, rel_end)
            kids = [
                c for c in block.children
                if c.start_byte >= rel_end and c.type not in comments
            ]
            _walk_children(ctx, kids, label)
        else:
            _walk_children(ctx, list(block.children), label)
            if block.end_byte > block.start_byte and ctx["src"][block.end_byte - 1:block.end_byte] == b"}":
                close_start = ctx["src"].rfind(b"\n", block.start_byte, block.end_byte - 1)
                if close_start == -1:
                    close_start = block.end_byte - 1
                _emit(ctx, close_start + 1, block.end_byte)
            remainder = (block.end_byte, node.end_byte)
            if remainder[1] > remainder[0]:
                _emit(ctx, remainder[0], remainder[1])
        return label
    if node.type in bodies:
        _walk_children(ctx, list(node.children), label)
        return label
    if node.type == "ERROR":
        return label
    _emit(ctx, node.start_byte, node.end_byte)
    return label
```

Notes for the implementer:
- If a contract test fails because a grammar uses a different node name (e.g. rust comments, go field declarations), inspect with a quick script (`Parser(lang).parse(src).root_node.sexp()`) and add the missing node type to the relevant set — the assertions are the spec, the tables are adjustable.
- `_CUR_LANG` is a one-element list used because `_find_body` needs the current language; it is set in `skeletonize_ast` before walking.

- [ ] **Step 6: Run tests to verify they pass**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/unit/test_school_skeleton.py -q --no-header -p no:cacheprovider`
Expected: all PASS (AST + Task 1).

- [ ] **Step 7: Ruff + commit**

Run: `& ".venv\Scripts\python.exe" -m ruff check school/skeleton.py tests/unit/test_school_skeleton.py pyproject.toml`
Expected: no new errors.

```bash
git add school/skeleton.py pyproject.toml tests/unit/test_school_skeleton.py
git commit -m "feat: tree-sitter ast skeleton with ctx extra"
```

---

### Task 3: Bridge `skeleton` command

**Files:**
- Modify: `school/bridge.py` (module docstring Commands list; import; `_handle_skeleton`; `_COMMANDS` registration)
- Test: `tests/unit/test_school_plugin_bridge.py` (append class)

**Interfaces:**
- Consumes: `school.skeleton.optimize(text, filename=..., strategy=...) -> OptimizeResult` (Task 1).
- Produces: bridge command `"skeleton"` → JSON `{ok:true, content, tokens_in, tokens_out, compressed, parser}`; validation errors `{ok:false, error:{type:"validation", message}}`. The plugin (Task 5) invokes this via `invokeBridge(python, bridgePath, {command:"skeleton", text, filename}, 2000)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_school_plugin_bridge.py`:

```python
class TestSkeletonCommand:
    def test_registered_in_commands(self):
        import school.bridge as bridge_mod

        assert "skeleton" in bridge_mod._COMMANDS
        assert bridge_mod._COMMANDS["skeleton"] is bridge_mod._handle_skeleton

    def test_payload_compressed_with_footer(self):
        import school.bridge as bridge_mod

        text = "\n".join('{"k": "some value %d"}' % i for i in range(400))
        out = bridge_mod._handle_skeleton(
            {"text": text, "filename": "data.json"}
        )
        assert out["ok"] is True
        assert out["compressed"] is True
        assert out["tokens_in"] >= 1000
        assert out["tokens_out"] < out["tokens_in"]
        assert "[school ctx:" in out["content"]
        assert out["parser"] == "payload"

    def test_small_text_passthrough(self):
        import school.bridge as bridge_mod

        out = bridge_mod._handle_skeleton({"text": "tiny", "filename": "a.txt"})
        assert out["ok"] is True
        assert out["compressed"] is False
        assert out["content"] == "tiny"
        assert "school ctx" not in out["content"]

    def test_missing_text_validation(self):
        import school.bridge as bridge_mod

        out = bridge_mod._handle_skeleton({})
        assert out["ok"] is False
        assert out["error"]["type"] == "validation"

    def test_invalid_strategy_validation(self):
        import school.bridge as bridge_mod

        out = bridge_mod._handle_skeleton(
            {"text": "x" * 4000, "strategy": "nope"}
        )
        assert out["ok"] is False
        assert out["error"]["type"] == "validation"

    def test_kill_switch(self, monkeypatch):
        import school.bridge as bridge_mod

        monkeypatch.setenv("SCHOOL_CTX", "0")
        text = "\n".join('{"k": "some value %d"}' % i for i in range(400))
        out = bridge_mod._handle_skeleton({"text": text, "filename": "d.json"})
        assert out["ok"] is True
        assert out["compressed"] is False
        assert out["content"] == text

    def test_stdio_roundtrip(self):
        import json as json_mod
        from io import StringIO
        from unittest.mock import patch

        import school.bridge as bridge_mod

        text = "\n".join('{"k": "some value %d"}' % i for i in range(400))
        payload = json_mod.dumps(
            {"command": "skeleton", "text": text, "filename": "d.json"}
        )
        stdin = StringIO(payload)
        stdout = StringIO()
        with (
            patch("sys.stdin", stdin),
            patch("sys.stdout", stdout),
        ):
            bridge_mod.main()
        output = json_mod.loads(stdout.getvalue())
        assert output["ok"] is True
        assert output["compressed"] is True
        assert "[school ctx:" in output["content"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/unit/test_school_plugin_bridge.py -q --no-header -p no:cacheprovider -k Skeleton`
Expected: FAIL (`AttributeError: ... has no attribute '_handle_skeleton'` or ImportError on `_COMMANDS["skeleton"]`).

- [ ] **Step 3: Implement in `school/bridge.py`**

1. Add to the top-level imports (respect existing import block, alphabetical among `school.*`): `from school.skeleton import optimize`.
2. Extend the module docstring Commands list with a line: `  skeleton — Context Optimizer (skeletonize oversized text)`.
3. Add the handler next to the other `_handle_*` functions:

```python
def _handle_skeleton(req: dict) -> dict:
    text = req.get("text", "")
    if not isinstance(text, str) or not text:
        return {
            "ok": False,
            "error": {"type": "validation", "message": "text is required"},
        }
    filename = str(req.get("filename", "") or "")
    strategy = str(req.get("strategy", "auto") or "auto")
    if strategy not in {"auto", "code", "payload", "matches"}:
        return {
            "ok": False,
            "error": {"type": "validation", "message": f"unknown strategy: {strategy}"},
        }
    result = optimize(text, filename=filename, strategy=strategy)
    return {
        "ok": True,
        "content": result.text,
        "tokens_in": result.tokens_in,
        "tokens_out": result.tokens_out,
        "compressed": result.compressed,
        "parser": result.parser,
    }
```

4. Register in `_COMMANDS`: `"skeleton": _handle_skeleton,`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/unit/test_school_plugin_bridge.py -q --no-header -p no:cacheprovider`
Expected: all PASS (including pre-existing bridge tests).

- [ ] **Step 5: Ruff + commit**

Run: `& ".venv\Scripts\python.exe" -m ruff check school/bridge.py tests/unit/test_school_plugin_bridge.py`
Expected: no new errors.

```bash
git add school/bridge.py tests/unit/test_school_plugin_bridge.py
git commit -m "feat: bridge skeleton command"
```

---

### Task 4: MCP `school_read` + `school_grep` tools

**Files:**
- Modify: `school/mcp/server.py` (imports; `_result`/`_error_result` helpers; `_SKIPPED_DIRS`, `_MAX_GREP_FILE`; `_call_read`, `_call_grep`; two `_TOOLS` entries after `school_route_stats`; `_call_tool` dispatch)
- Test: `tests/unit/test_mcp_server.py` (tool order, annotations, description parity, new classes)
- Test: `tests/integration/test_mcp_stdio.py` (tool order + new class)

**Interfaces:**
- Consumes: `school.skeleton.optimize` (Task 1/2).
- Produces (MCP-only — NOT added to plugin tool lists): tools `school_read` (schema: path req, offset ≥1, limit ≥1) and `school_grep` (schema: pattern req, path, ignore_case, limit 1–1000 default 200); both `read_only_hint`/`idempotent_hint` true; payloads `{ok, path, content, skeletonized, tokens_in, tokens_out, parser}` (read) and `{ok, path, matches, truncated, content, skeletonized, tokens_in, tokens_out, parser}` (grep); errors `{ok:false, error:{type: validation|not_found|io, message}}` with `is_error=True`.

- [ ] **Step 1: Write the failing unit tests**

In `tests/unit/test_mcp_server.py`:

1. In `EXPECTED_TOOL_ORDER`, append `"school_read", "school_grep"` after `"school_route_stats"`.
2. In `test_read_only_annotations` exact set, add `"school_read"` and `"school_grep"`.
3. In `test_mcp_descriptions_match_plugin_ts`, add at loop top:

```python
        MCP_ONLY_TOOLS = frozenset({"school_read", "school_grep"})
        for name, spec in mcp_server._TOOLS.items():
            if name in MCP_ONLY_TOOLS:
                continue
```

and after the loop add:

```python
    def test_mcp_only_tools_have_no_plugin_block(self):
        import re as re_mod

        plugin_tools = set(
            re_mod.findall(r"^\s+(school_\w+): tool\(", TS_PLUGIN_SOURCE, re_mod.M)
        )
        assert set(mcp_server._TOOLS) - plugin_tools == {
            "school_read",
            "school_grep",
        }
        assert plugin_tools - set(mcp_server._TOOLS) == set()
```

(adjust the surrounding loop/indentation of the existing test to keep its asserts working).

4. Append:

```python
class TestReadToolMCP:
    def test_small_file_raw(self, tmp_path):
        f = tmp_path / "small.txt"
        f.write_text("hello world\nsecond line\n", encoding="utf-8")
        result = mcp_server._call_tool(str(tmp_path), "school_read", {"path": "small.txt"})
        data = json.loads(result.content[0].text)
        assert result.is_error is False
        assert data["ok"] is True
        assert data["skeletonized"] is False
        assert data["content"] == "hello world\nsecond line"
        assert "school ctx" not in data["content"]

    def test_oversized_python_skeletonized(self, tmp_path):
        lines = ["def compute(a: int) -> int:"]
        for i in range(600):
            lines.append("    x = x + %d" % i)
        f = tmp_path / "big.py"
        f.write_text("\n".join(lines), encoding="utf-8")
        result = mcp_server._call_tool(str(tmp_path), "school_read", {"path": "big.py"})
        data = json.loads(result.content[0].text)
        assert data["ok"] is True
        assert data["skeletonized"] is True
        assert data["tokens_in"] >= 1000
        assert data["tokens_out"] < data["tokens_in"]
        assert "def compute(" in data["content"]
        assert re.search(r"\[school ctx: \d+→\d+ tokens\]\s*$", data["content"])

    def test_offset_limit_raw_window(self, tmp_path):
        f = tmp_path / "lines.txt"
        f.write_text("\n".join("line %d" % i for i in range(1, 21)), encoding="utf-8")
        result = mcp_server._call_tool(
            str(tmp_path), "school_read", {"path": "lines.txt", "offset": 1, "limit": 3}
        )
        data = json.loads(result.content[0].text)
        assert data["skeletonized"] is False
        assert data["content"] == "line 1\nline 2\nline 3"

    def test_missing_path_validation(self, tmp_path):
        result = mcp_server._call_tool(str(tmp_path), "school_read", {})
        data = json.loads(result.content[0].text)
        assert result.is_error is True
        assert data["error"]["type"] == "validation"

    def test_not_found(self, tmp_path):
        result = mcp_server._call_tool(
            str(tmp_path), "school_read", {"path": "nope.txt"}
        )
        data = json.loads(result.content[0].text)
        assert result.is_error is True
        assert data["error"]["type"] == "not_found"

    def test_directory_validation(self, tmp_path):
        (tmp_path / "adir").mkdir()
        result = mcp_server._call_tool(
            str(tmp_path), "school_read", {"path": "adir"}
        )
        data = json.loads(result.content[0].text)
        assert result.is_error is True
        assert data["error"]["type"] == "validation"

    def test_binary_io_error(self, tmp_path):
        f = tmp_path / "blob.bin"
        f.write_bytes(b"\x00\x01\x02abc")
        result = mcp_server._call_tool(str(tmp_path), "school_read", {"path": "blob.bin"})
        data = json.loads(result.content[0].text)
        assert result.is_error is True
        assert data["error"]["type"] == "io"


class TestGrepToolMCP:
    def test_finds_matches(self, tmp_path):
        (tmp_path / "a.py").write_text(
            "def alpha():\n    pass\n\ndef beta():\n    pass\n", encoding="utf-8"
        )
        (tmp_path / "b.py").write_text(
            "def gamma():\n    pass\n", encoding="utf-8"
        )
        result = mcp_server._call_tool(
            str(tmp_path), "school_grep", {"pattern": "^def "}
        )
        data = json.loads(result.content[0].text)
        assert data["ok"] is True
        assert data["matches"] == 3
        assert data["truncated"] is False
        assert "a.py:1:def alpha():" in data["content"]
        assert data["skeletonized"] is False

    def test_limit_truncates(self, tmp_path):
        (tmp_path / "a.py").write_text(
            "\n".join("def f%d():" % i for i in range(20)), encoding="utf-8"
        )
        result = mcp_server._call_tool(
            str(tmp_path), "school_grep", {"pattern": "^def ", "limit": 1}
        )
        data = json.loads(result.content[0].text)
        assert data["matches"] == 1
        assert data["truncated"] is True

    def test_invalid_regex_validation(self, tmp_path):
        result = mcp_server._call_tool(
            str(tmp_path), "school_grep", {"pattern": "["}
        )
        data = json.loads(result.content[0].text)
        assert result.is_error is True
        assert data["error"]["type"] == "validation"

    def test_unknown_path_not_found(self, tmp_path):
        result = mcp_server._call_tool(
            str(tmp_path), "school_grep",
            {"pattern": "x", "path": "missing_dir"},
        )
        data = json.loads(result.content[0].text)
        assert result.is_error is True
        assert data["error"]["type"] == "not_found"

    def test_oversized_matches_elided(self, tmp_path):
        (tmp_path / "c.txt").write_text(
            "\n".join(
                "match_token %d padding padding" % i for i in range(150)
            ),
            encoding="utf-8",
        )
        result = mcp_server._call_tool(
            str(tmp_path), "school_grep",
            {"pattern": "match_token", "limit": 500},
        )
        data = json.loads(result.content[0].text)
        assert data["matches"] == 150
        assert data["skeletonized"] is True
        assert "[school ctx:" in data["content"]
        assert "more matches in" in data["content"]
        kept = [ln for ln in data["content"].splitlines() if ln.startswith("c.txt:")]
        assert len(kept) == 10
```

- [ ] **Step 2: Run unit tests to verify they fail**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/unit/test_mcp_server.py -q --no-header -p no:cacheprovider`
Expected: FAIL — order assertion (`school_read` missing), unknown tool `ValueError`/MCPError in new classes.

- [ ] **Step 3: Implement in `school/mcp/server.py`**

1. Imports: add `re` to the stdlib import block (order: json, os, re, sys, ...) and `from school.skeleton import optimize` after `from school import __version__, bridge`.
2. After `_route_result` (or near `_call_route`), add helpers:

```python
_SKIPPED_DIRS = frozenset({
    ".git", "node_modules", ".venv", "venv", "__pycache__", ".school",
    ".evo", "dist", "build", ".mypy_cache", ".ruff_cache", ".pytest_tmp",
    ".pytest_cache", ".opencode", ".superpowers",
})
_MAX_GREP_FILE = 1_000_000


def _result(data: dict) -> types.CallToolResult:
    payload = json.dumps(data, default=str, ensure_ascii=False)
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=payload)],
        structured_content=json.loads(payload),
        is_error=not bool(data.get("ok", False)),
    )


def _error_result(err_type: str, message: str) -> types.CallToolResult:
    return _result({"ok": False, "error": {"type": err_type, "message": message}})
```

3. Add the two tool entries in `_TOOLS` immediately after the `school_route_stats` entry (before the closing `}`):

```python
    "school_read": {
        "description": (
            "Read a text file with the Context Optimizer: small files come back raw, "
            "oversized results are skeletonized (signatures, imports, control flow kept; "
            "bodies elided) with a single [school ctx: in->out tokens] footer. "
            "Use for file contents; pass offset/limit to re-read a region raw after an elision."
        ),
        "annotations": {"read_only_hint": True, "idempotent_hint": True},
        "schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File to read (absolute, or relative to the worktree).",
                },
                "offset": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "1-based first line to return (defaults to 1).",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Maximum number of lines to return from offset.",
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    "school_grep": {
        "description": (
            "Search files under a path for a regular expression and return "
            "path:line:content matches (Context Optimizer footer when oversized). "
            "Use to locate code/text across a project without reading whole files."
        ),
        "annotations": {"read_only_hint": True, "idempotent_hint": True},
        "schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regular expression to search for.",
                },
                "path": {
                    "type": "string",
                    "description": "File or directory to search (defaults to the worktree).",
                },
                "ignore_case": {
                    "type": "boolean",
                    "description": "Case-insensitive search.",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 1000,
                    "description": "Maximum matches to return (default 200).",
                },
            },
            "required": ["pattern"],
            "additionalProperties": False,
        },
    },
```

4. Add the two dispatchers (near `_call_route`, before `_call_tool`):

```python
def _int_arg(value: object, default: int, lo: int, hi: int) -> int:
    try:
        n = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _call_read(worktree: str, arguments: dict) -> types.CallToolResult:
    raw = str(arguments.get("path", "") or "").strip()
    if not raw:
        return _error_result("validation", "path is required")
    path = Path(raw)
    if not path.is_absolute():
        path = Path(worktree) / path
    if not path.exists():
        return _error_result("not_found", f"no such file: {raw}")
    if path.is_dir():
        return _error_result("validation", f"is a directory: {raw}")
    try:
        data = path.read_bytes()
    except OSError as exc:
        return _error_result("io", str(exc))
    if b"\x00" in data[:8192]:
        return _error_result("io", "binary file")
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    offset = _int_arg(arguments.get("offset"), 1, 1, 1 << 30)
    limit = None
    if arguments.get("limit") is not None:
        limit = _int_arg(arguments.get("limit"), len(lines), 1, 1 << 30)
    window = lines[offset - 1:]
    if limit is not None:
        window = window[:limit]
    content = "\n".join(window)
    result = optimize(content, filename=str(path))
    return _result({
        "ok": True,
        "path": str(path),
        "content": result.text,
        "skeletonized": result.compressed,
        "tokens_in": result.tokens_in,
        "tokens_out": result.tokens_out,
        "parser": result.parser,
    })


def _call_grep(worktree: str, arguments: dict) -> types.CallToolResult:
    pattern = str(arguments.get("pattern", "") or "")
    if not pattern:
        return _error_result("validation", "pattern is required")
    flags = re.IGNORECASE if arguments.get("ignore_case") else 0
    try:
        rx = re.compile(pattern, flags)
    except re.error as exc:
        return _error_result("validation", f"invalid regex: {exc}")
    raw = str(arguments.get("path", "") or "").strip() or worktree
    target = Path(raw)
    if not target.is_absolute():
        target = Path(worktree) / target
    if not target.exists():
        return _error_result("not_found", f"no such path: {raw}")
    limit = _int_arg(arguments.get("limit"), 200, 1, 1000)
    if target.is_file():
        files = [target]
        base = target.parent
    else:
        files = sorted(
            p for p in target.rglob("*")
            if p.is_file() and not any(part in _SKIPPED_DIRS for part in p.parts)
        )
        base = target
    matches: list[str] = []
    truncated = False
    for file in files:
        try:
            if file.stat().st_size > _MAX_GREP_FILE:
                continue
            data = file.read_bytes()[:8192]
            if b"\x00" in data:
                continue
        except OSError:
            continue
        try:
            body = file.read_bytes().decode("utf-8", errors="replace")
        except OSError:
            continue
        rel = file.relative_to(base)
        for lineno, line in enumerate(body.splitlines(), start=1):
            if rx.search(line):
                matches.append(f"{rel}:{lineno}:{line.rstrip()}")
                if len(matches) >= limit:
                    truncated = True
                    break
        if truncated:
            break
    content = "\n".join(matches)
    result = optimize(content, strategy="matches")
    return _result({
        "ok": True,
        "path": str(target),
        "matches": len(matches),
        "truncated": truncated,
        "content": result.text,
        "skeletonized": result.compressed,
        "tokens_in": result.tokens_in,
        "tokens_out": result.tokens_out,
        "parser": result.parser,
    })
```

5. In `_call_tool`, after the `school_route_stats` special-case and before the generic `_build_request` path, add:

```python
    if name == "school_read":
        return _call_read(worktree, arguments)
    if name == "school_grep":
        return _call_grep(worktree, arguments)
```

- [ ] **Step 4: Run unit tests to verify they pass**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/unit/test_mcp_server.py -q --no-header -p no:cacheprovider`
Expected: all PASS (order, annotations, parity with MCP_ONLY skip, new classes, pre-existing tests).

- [ ] **Step 5: Write failing integration tests**

In `tests/integration/test_mcp_stdio.py`: append `"school_read", "school_grep"` to `EXPECTED_TOOLS`, then append:

```python
class TestContextOptimizerTools:
    async def test_small_read_raw(self, tmp_path):
        (tmp_path / "small.txt").write_text("hello world\n", encoding="utf-8")
        async with _server(tmp_path) as (session, _):
            result = await session.call_tool("school_read", {"path": "small.txt"})
            assert not result.is_error
            data = json.loads(result.content[0].text)
            assert data["ok"] is True
            assert data["skeletonized"] is False
            assert data["content"] == "hello world"

    async def test_oversized_read_skeletonized(self, tmp_path):
        lines = ["def compute(a: int) -> int:"]
        for i in range(600):
            lines.append("    x = x + %d" % i)
        (tmp_path / "big.py").write_text("\n".join(lines), encoding="utf-8")
        async with _server(tmp_path) as (session, _):
            result = await session.call_tool("school_read", {"path": "big.py"})
            assert not result.is_error
            data = json.loads(result.content[0].text)
            assert data["skeletonized"] is True
            assert "[school ctx:" in data["content"]

    async def test_unknown_path_is_error(self, tmp_path):
        async with _server(tmp_path) as (session, _):
            result = await session.call_tool("school_read", {"path": "missing.txt"})
            assert result.is_error
            data = json.loads(result.content[0].text)
            assert data["error"]["type"] == "not_found"

    async def test_grep_finds_def(self, tmp_path):
        (tmp_path / "a.py").write_text(
            "def alpha():\n    pass\n", encoding="utf-8"
        )
        async with _server(tmp_path) as (session, _):
            result = await session.call_tool("school_grep", {"pattern": "^def "})
            assert not result.is_error
            data = json.loads(result.content[0].text)
            assert data["matches"] == 1
            assert "a.py:1:def alpha():" in data["content"]
```

- [ ] **Step 6: Run integration tests to verify they pass**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/integration/test_mcp_stdio.py -q --no-header -p no:cacheprovider`
Expected: all PASS (order test now includes the two tools; new class passes).

- [ ] **Step 7: Ruff + commit**

Run: `& ".venv\Scripts\python.exe" -m ruff check school/mcp/server.py tests/unit/test_mcp_server.py tests/integration/test_mcp_stdio.py`
Expected: no new errors.

```bash
git add school/mcp/server.py tests/unit/test_mcp_server.py tests/integration/test_mcp_stdio.py
git commit -m "feat: mcp school_read and school_grep tools"
```

---

### Task 5: Plugin TS Context Optimizer (constants, helpers, `ctxOptimize`, hook wiring)

**Files:**
- Modify: `school/plugin_source.py` (inside `_TS_PLUGIN_TEMPLATE`: constants + helpers block after the knobs/route helpers, before `const School: Plugin`; wiring inserted in the `tool.execute.after` hook)
- Test: `tests/unit/test_school_plugin_hooks.py` (append `class TestContextOptimizer`)

**Interfaces:**
- Consumes: bridge command `skeleton` (Task 3) via existing `invokeBridge(python, bridgePath, request, timeoutMs)`; `python`/`bridgePath` consts already in scope inside the `School` closure; `hooksEnabled()`; footer format from Task 1.
- Produces: TS functions `ctxEnabled()`, `ctxEstimate(s)`, `ctxStripFooter(t)`, `ctxFooter(i,o)`, `ctxCommentPrefix(filename)`, `ctxHeuristic(text, filename)`, `ctxPayload(text)`, `async ctxOptimize(text, filename): Promise<string | null>`; constants `CTX_THRESHOLD=1000`, `CTX_TIMEOUT_MS=2000`, `CTX_FOOTER_RE`, `CTX_CODE_RE`. Plugin tool surface stays 13; no new imports.

Notes:
- The helpers block goes at TOP LEVEL of the template (after the route helpers, before `const School: Plugin = async (ctx) => {`) because `python`/`bridgePath` are closure locals — therefore `ctxOptimize` must take them as parameters: signature `async function ctxOptimize(python: string, bridgePath: string, text: string, filename: string): Promise<string | null>`. The wiring inside the hook calls `await ctxOptimize(python, bridgePath, raw, filename)`.
- Keep every new physical line ≤100 chars (ruff E501 on the Python file).

- [ ] **Step 1: Write the failing source-contract tests**

Append to `tests/unit/test_school_plugin_hooks.py` (reuse its `_hook_block` helper; add a module-level `_fn_block` if not present):

```python
def _fn_block(name: str) -> str:
    m = re.search(
        rf"(?:async )?function {name}\([\s\S]*?\n\}}",
        TS_PLUGIN_SOURCE,
    )
    assert m, f"function {name} not found in plugin source"
    return m.group(0)


class TestContextOptimizer:
    def test_constants(self):
        assert "const CTX_THRESHOLD = 1000" in TS_PLUGIN_SOURCE
        assert "const CTX_TIMEOUT_MS = 2000" in TS_PLUGIN_SOURCE

    def test_kill_switch(self):
        assert 'process.env.SCHOOL_CTX !== "0"' in TS_PLUGIN_SOURCE

    def test_footer_regex_literal(self):
        assert r"\[school ctx: \d+→\d+ tokens\]" in TS_PLUGIN_SOURCE

    def test_ctx_optimize_uses_bridge_with_timeout(self):
        block = _fn_block("ctxOptimize")
        assert 'command: "skeleton"' in block
        assert "CTX_TIMEOUT_MS" in block
        assert "ctxEnabled" in block
        assert "catch" in block

    def test_after_hook_wires_optimization(self):
        block = _hook_block("tool.execute.after")
        assert "ctxOptimize(" in block
        assert 'startsWith("Error")' in block
        assert "CTX_THRESHOLD" in block
        assert block.index("ctxOptimize(") < block.index(
            "rec && rec.hits > 0"
        ), "compression must run before the recall block append"

    def test_helper_functions_present(self):
        for name in ("ctxEnabled", "ctxEstimate", "ctxHeuristic", "ctxPayload"):
            _fn_block(name)

    def test_no_new_imports(self):
        allowed = (
            "node:child_process", "node:util", "node:path", "node:fs",
            "@opencode-ai/plugin",
        )
        for m in re.findall(r'from\s+"([^"]+)"', TS_PLUGIN_SOURCE):
            assert m in allowed, f"unexpected import {m}"

    def test_tool_surface_still_13(self):
        assert (
            len(re.findall(r"^\s+(school_\w+): tool\(", TS_PLUGIN_SOURCE, re.M))
            == 13
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/unit/test_school_plugin_hooks.py -q --no-header -p no:cacheprovider -k ContextOptimizer`
Expected: FAIL (`const CTX_THRESHOLD = 1000` not found / function ctxOptimize not found).

- [ ] **Step 3: Implement in `school/plugin_source.py`**

**3a. Helpers block** — insert immediately before `const School: Plugin = async (ctx) => {` (line ~390):

```typescript
  const CTX_THRESHOLD = 1000;
  const CTX_TIMEOUT_MS = 2000;
  const CTX_FOOTER_RE = /\[school ctx: \d+→\d+ tokens\]\s*$/;
  const CTX_CODE_RE = /\.(py|pyi|js|jsx|mjs|cjs|ts|tsx|go|rs|java|c|h|cpp|cc|cxx|hpp|hh|hxx|sh|bash|rb|php|cs|kt|swift|sql|ya?ml|toml|ini|cfg|conf|lua|pl|r|scala|ex|exs|hs|clj|cljs|graphql|proto|tf)$/i;
  const CTX_NOISE = new Set([
    "import", "from", "as", "require", "const", "let", "var", "use",
    "using", "include", "package", "export", "default", "async", "await", "type",
  ]);

  function ctxEnabled(): boolean {
    return process.env.SCHOOL_CTX !== "0";
  }
  function ctxEstimate(s: string): number {
    return Math.ceil(s.length / 4);
  }
  function ctxStripFooter(t: string): string {
    return t.replace(CTX_FOOTER_RE, "").replace(/\s+$/, "");
  }
  function ctxFooter(i: number, o: number): string {
    return `[school ctx: ${i}→${o} tokens]`;
  }
  function ctxSuffix(filename: string): string {
    const name = filename.toLowerCase();
    const dot = name.lastIndexOf(".");
    return dot > 0 ? name.slice(dot) : "";
  }
  function ctxCommentPrefix(filename: string): string {
    const ext = ctxSuffix(filename);
    if (/\.(c|h|cpp|cc|cxx|hpp|hh|hxx|js|jsx|mjs|cjs|ts|tsx|go|rs|java|kt|cs|swift|scala|php)$/.test(ext)) return "//";
    if (/\.(sql|lua|pl)$/.test(ext)) return "--";
    return "#";
  }
  const CTX_LICENSE_RE = /copyright|licensed?\s+under|spdx-|all\s+rights\s+reserved/i;
  const CTX_IMPORT_RE = /^\s*(import\b|from\s+\S+\s+import\b|require\s*\(|use\s|using\s|include\s|package\s+\w|export\s+.*\sfrom\s|#\s*(include|define|if|ifdef|ifndef|pragma)\b)/;
  const CTX_DECL_RE = /^\s*(?:(?:export|default|async|pub|public|private|protected|static|final|abstract|override|virtual)\s+)*(def|class|function|fn|func|struct|enum|trait|impl|interface|type|namespace|module)\s+[A-Za-z_$]/;
  const CTX_ARROW_RE = /^\s*(export\s+)?(const|let|var)\s+[\w$]+\s*=.*=>/;
  const CTX_CONTROL_RE = /^\s*(if|else|elif|for|while|do|switch|case|default|try|except|catch|finally|return|yield|break|continue|match|guard|when|raise|throw|assert)\b/;
  const CTX_CLOSER_RE = /^\s*[}\])]+;?\s*$/;
  const CTX_SIG_RE = /^\s*[A-Za-z_][\w.]*\s*:(\s|$)/;
  const CTX_SQL_KEEP_RE = /^\s*(select|from|where|group\s+by|order\s+by|having|limit|offset|join|left|right|inner|outer|full|union|values|insert\s+into|update|delete\s+from|create|alter|drop|with|returning|set|into|on|begin|end|commit|rollback)\b/i;
  const CTX_YAML_KEY_RE = /^[A-Za-z_][\w.-]*\s*:/;

  function ctxClassify(lines: string[]): string[] {
    const kinds: string[] = [];
    let mode = "";
    for (const line of lines) {
      const stripped = line.trim();
      if (mode) {
        kinds.push("string_cont");
        if (stripped.includes(mode)) mode = "";
        continue;
      }
      if (!stripped) { kinds.push("blank"); continue; }
      if (stripped.startsWith("#") || stripped.startsWith("//") ||
          stripped.startsWith("/*") || stripped.startsWith("*") ||
          stripped.startsWith("--")) { kinds.push("comment"); continue; }
      const dq = (line.match(/"""/g) || []).length;
      const sq = (line.match(/'''/g) || []).length;
      const tick = (line.match(/`/g) || []).length;
      if (dq % 2 === 1) { kinds.push("string_first"); mode = '"""'; }
      else if (sq % 2 === 1) { kinds.push("string_first"); mode = "'''"; }
      else if (tick % 2 === 1) { kinds.push("string_first"); mode = "`"; }
      else kinds.push("code");
    }
    return kinds;
  }
  function ctxDepthDelta(line: string): number {
    const cleaned = line
      .replace(/"[^"]*"|'[^']*'/g, "")
      .replace(/(#|\/\/|--).*$/, "");
    let d = 0;
    for (const ch of cleaned) {
      if (ch === "(" || ch === "[" || ch === "{") d += 1;
      else if (ch === ")" || ch === "]" || ch === "}") d -= 1;
    }
    return d;
  }
  function ctxDeclLabel(line: string): string {
    const m = CTX_DECL_RE.exec(line);
    if (m) {
      const rest = line.slice(m.index + m[0].length).replace(/^\s+/, "");
      const nm = /^[A-Za-z_$][\w$]*/.exec(rest);
      const base = nm ? nm[0] : "";
      if (["def", "function", "fn", "func"].includes(m[1]) && base) return base + "()";
      return base || m[1];
    }
    const rest = line.trim().replace(/^export\s+/, "");
    const m2 = /^(?:const|let|var)\s+([\w$]+)/.exec(rest);
    if (m2 && CTX_ARROW_RE.test(line)) return m2[1] + "()";
    return "body";
  }
  function ctxKeep(line: string, ext: string, kind: string): string {
    if (kind === "comment") return "comment";
    const s = line.trim();
    if (!s) return "blank";
    if (CTX_IMPORT_RE.test(line)) return "import";
    if (/^\s*@\w/.test(line)) return "decorator";
    if (CTX_DECL_RE.test(line) || CTX_ARROW_RE.test(line)) return "decl";
    if (CTX_CONTROL_RE.test(line)) return "control";
    if (CTX_CLOSER_RE.test(line)) return "closer";
    if ((ext === ".sql" || ext === ".graphql" || ext === ".gql") && CTX_SQL_KEEP_RE.test(line)) return "sql";
    if ((ext === ".yaml" || ext === ".yml") && CTX_YAML_KEY_RE.test(line)) return "yaml";
    if (CTX_SIG_RE.test(line)) return "sig";
    return "body";
  }
  function ctxImportNames(line: string): Set<string> {
    const out = new Set<string>();
    for (const w of line.match(/[A-Za-z_][A-Za-z0-9_]*/g) || []) {
      if (!CTX_NOISE.has(w) && w.length > 1) out.add(w);
    }
    return out;
  }
  function ctxHeuristic(text: string, filename: string): string {
    const ext = ctxSuffix(filename);
    const prefix = ctxCommentPrefix(filename);
    const lines = text.split("\n");
    if (lines.length === 0) return text;
    const kinds = ctxClassify(lines);
    const drop = new Array(lines.length).fill(false);
    let firstBlock = true;
    let headerEnd = 0;
    let i = 0;
    while (i < lines.length) {
      if (kinds[i] !== "comment") { i += 1; continue; }
      const start = i;
      while (i < lines.length && kinds[i] === "comment") i += 1;
      const block = lines.slice(start, i);
      const beforeAllCode = kinds.slice(0, start).every((k) => k !== "code");
      if (firstBlock && beforeAllCode) {
        if (block.some((c) => CTX_LICENSE_RE.test(c))) {
          for (let j = start; j < i; j += 1) drop[j] = true;
        } else {
          let kept = 0;
          for (let j = start; j < i; j += 1) {
            if (kept < 3) kept += 1; else drop[j] = true;
          }
        }
        headerEnd = i;
        firstBlock = false;
      } else {
        for (let j = start; j < i; j += 1) drop[j] = true;
      }
    }
    const refset = new Set<string>();
    lines.forEach((line, idx) => {
      if (kinds[idx] === "code" && !CTX_IMPORT_RE.test(line)) {
        for (const w of line.match(/[A-Za-z_][A-Za-z0-9_]*/g) || []) refset.add(w);
      }
    });
    let keptDepth = 0;
    let label = "body";
    const keep = new Array(lines.length).fill(false);
    lines.forEach((line, idx) => {
      const kind = kinds[idx];
      if (drop[idx]) return;
      if (kind === "blank") { keep[idx] = true; return; }
      if (kind === "string_first") { keep[idx] = true; return; }
      if (kind === "string_cont") return;
      if (kind === "comment") { keep[idx] = headerEnd > 0 && idx < headerEnd; return; }
      const cls = ctxKeep(line, ext, "code");
      if (keptDepth > 0) {
        keep[idx] = true;
        keptDepth += ctxDepthDelta(line);
        return;
      }
      if (["import", "decorator", "decl", "control", "closer", "sql", "yaml", "sig"].includes(cls)) {
        if (cls === "import") {
          let hit = false;
          for (const n of ctxImportNames(line)) if (refset.has(n)) { hit = true; break; }
          if (!hit) return;
        }
        keep[idx] = true;
        keptDepth += ctxDepthDelta(line);
        if (cls === "decl") label = ctxDeclLabel(line);
      }
    });
    const out: string[] = [];
    let run: number[] = [];
    let runLabel = label;
    let pendingBlank = false;
    let prevStringFirst = false;
    const flush = () => {
      if (run.length > 0) {
        if (run.length >= 2) out.push(`${prefix} … ${runLabel} — ${run.length} lines`);
        run = [];
      }
      runLabel = label;
    };
    lines.forEach((line, idx) => {
      if (drop[idx]) return;
      if (!keep[idx]) {
        if (kinds[idx] === "blank") return;
        run.push(idx);
        if (run.length === 1 && prevStringFirst && kinds[idx] === "string_cont") {
          runLabel = "docstring";
        }
        prevStringFirst = false;
        return;
      }
      flush();
      if (kinds[idx] === "blank") {
        if (pendingBlank) return;
        pendingBlank = true;
        out.push("");
      } else {
        pendingBlank = false;
        out.push(line);
        if (kinds[idx] === "decl") label = ctxDeclLabel(line);
        prevStringFirst = kinds[idx] === "string_first";
      }
    });
    flush();
    while (out.length > 0 && out[out.length - 1] === "") out.pop();
    return out.join("\n");
  }
  function ctxShape(line: string): string {
    const s = line.trim();
    if (!s) return "";
    if (/^"(?:[^"\\]|\\.)*",?$/.test(s) || /^'(?:[^'\\]|\\.)*',?$/.test(s)) return "S";
    if (/^-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?,?$/.test(s)) return "N";
    if (/^(true|false|null|nil|undefined),?$/i.test(s)) return "K";
    if (s[0] === "{" || s[0] === "[") return "B";
    if (s[0] === "}" || s[0] === "]") return "C";
    if (/^[\w$.-]+(?:\s*:\s*.+)?,?$/.test(s)) return "I";
    return "O";
  }
  function ctxPayload(text: string): string {
    const prefix = "#";
    const lines = text.split("\n");
    const out: string[] = [];
    let i = 0;
    let pendingBlank = false;
    while (i < lines.length) {
      if (!lines[i].trim()) { pendingBlank = true; i += 1; continue; }
      const shape = ctxShape(lines[i]);
      let j = i;
      while (j < lines.length && lines[j].trim() && ctxShape(lines[j]) === shape) j += 1;
      const runLen = j - i;
      if (runLen >= 6) {
        if (pendingBlank) { out.push(""); pendingBlank = false; }
        out.push(lines[i]);
        out.push(lines[i + 1]);
        out.push(`${prefix} … repeated block — ${runLen - 2} lines`);
      } else {
        for (let k = i; k < j; k += 1) {
          if (pendingBlank) { out.push(""); pendingBlank = false; }
          out.push(lines[k]);
        }
      }
      i = j;
    }
    return out.join("\n");
  }
  async function ctxOptimize(
    python: string,
    bridgePath: string,
    text: string,
    filename: string
  ): Promise<string | null> {
    try {
      if (!ctxEnabled()) return null;
      const body = ctxStripFooter(text);
      const tokensIn = ctxEstimate(body);
      if (tokensIn < CTX_THRESHOLD) return null;
      if (python && bridgePath) {
        try {
          const resp = await invokeBridge(
            python,
            bridgePath,
            { command: "skeleton", text: body, filename },
            CTX_TIMEOUT_MS
          );
          const r = resp as { ok?: boolean; compressed?: boolean; content?: string };
          if (r.ok) {
            return r.compressed === true && typeof r.content === "string"
              ? r.content
              : null;
          }
        } catch {
          /* fall through to TS heuristic */
        }
      }
      const out = CTX_CODE_RE.test(filename)
        ? ctxHeuristic(body, filename)
        : ctxPayload(body);
      const tokensOut = ctxEstimate(out);
      if (tokensOut >= tokensIn) return null;
      return `${out}\n\n${ctxFooter(tokensIn, tokensOut)}`;
    } catch {
      return null;
    }
  }
```

Notes:
- Bridge content already includes its footer (Python appends it) — never double-footer. `ok && !compressed` → `null` (fail open). `ok:false` (older bridge without the command) → fall through to TS heuristic.
- If `python`/`bridgePath` are empty strings (bridge not discovered), skip straight to the TS heuristic.

**3b. Hook wiring** — in the `tool.execute.after` hook block, insert as the FIRST statement after `if (!hooksEnabled()) return;` and BEFORE `const rec = executionRecalls.get(input.callID) ?? null;`:

```typescript
      if (typeof output.output === "string") {
        const raw = output.output;
        const isErr =
          raw.startsWith("Error") || (output as { isError?: boolean }).isError === true;
        if (!isErr) {
          const anyOut = output as { args?: { filePath?: string; path?: string } };
          const filename = String(anyOut.args?.filePath ?? anyOut.args?.path ?? "");
          const optimized = await ctxOptimize(python, bridgePath, raw, filename);
          if (optimized !== null) output.output = optimized;
        }
      }
```

Keep the surrounding hook `try { ... } catch { /* never break execution */ }` unchanged; never mutate `input.`; the recall `[school context]` block still appends after this (footer sits before it, ≤1 footer per result).

- [ ] **Step 4: Run tests to verify they pass**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/unit/test_school_plugin_hooks.py -q --no-header -p no:cacheprovider`
Expected: all PASS (new class + all pre-existing hook/tool-surface tests).

- [ ] **Step 5: TS syntax check**

```powershell
& ".venv\Scripts\python.exe" -c "from pathlib import Path; from school.plugin_source import TS_PLUGIN_SOURCE; Path(r'C:\Users\dex34\AppData\Local\Temp\opencode\school-check.ts').write_text(TS_PLUGIN_SOURCE, encoding='utf-8')"
node --check C:\Users\dex34\AppData\Local\Temp\opencode\school-check.ts
```
Expected: exit 0. If node rejects TypeScript syntax with `--check`, use `node --experimental-strip-types --check <path>` (Node 24: `node --check` on `.ts` works natively).

- [ ] **Step 6: Ruff + commit**

Run: `& ".venv\Scripts\python.exe" -m ruff check school/plugin_source.py tests/unit/test_school_plugin_hooks.py`
Expected: no NEW errors (pre-existing E501s inside the template are baseline; new physical lines ≤100 chars).

```bash
git add school/plugin_source.py tests/unit/test_school_plugin_hooks.py
git commit -m "feat: plugin context optimizer hook"
```

---

### Task 6: Live node harness (end-to-end plugin hook test)

**Files:**
- Create: `tests/integration/test_plugin_live.py`

**Interfaces:**
- Consumes: `TS_PLUGIN_SOURCE` (Task 5), Node 24 native TS type-stripping, `School` default export with `tool.execute.after` hook.
- Produces: three green integration tests proving live compression, TS fallback, and the `SCHOOL_CTX=0` kill switch through the real Node runtime.

- [ ] **Step 1: Write the harness test file**

```python
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

STUB_TOOL_JS = "export const tool = (t) => t;\n"
STUB_INDEX_JS = "export {};\n"
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
        lines.append("    x = x + %d" % i)
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
    return d


def _run(plugin_dir: Path, worktree: Path, big: Path, env: dict) -> dict:
    proc = subprocess.run(
        ["node", str(plugin_dir / "harness.mjs"), str(worktree), str(big)],
        cwd=str(plugin_dir),
        capture_output=True,
        text=True,
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
        big.write_text(_big_py(), encoding="utf-8")
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
        big.write_text(_big_py(), encoding="utf-8")
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
        big.write_text(_big_py(), encoding="utf-8")
        env = dict(os.environ)
        env["SCHOOL_CTX"] = "0"
        out = _run(plugin_dir, worktree, big, env)
        original = big.read_text(encoding="utf-8")
        assert out["output"] == original
        assert "school ctx" not in out["output"]
```

- [ ] **Step 2: Run tests**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/integration/test_plugin_live.py -q --no-header -p no:cacheprovider`
Expected: PASS. Debug notes:
- If `School()` throws during discovery: PATH/SCHOOL_HOME games must stay try/caught — they are in the template; check stderr from the assert message.
- If node fails to import `.ts`: ensure Node ≥22.6/24 (env has v24.20.0) and `package.json {"type":"module"}` exists in plugin_dir.
- If title lacks `school`: the after-hook marker logic should still run after compression — verify hook ordering.
- Test 1 outcome must hold even with `SCHOOL_HOME` pointed nowhere (TS heuristic path); test 2 is outcome-based (bridge OR heuristic both acceptable — footer + shrink + signature).

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_plugin_live.py
git commit -m "test: live node plugin context optimizer"
```

---

### Task 7: Final battery + install parity + doctor

**Files:**
- None created; verification gates only.

- [ ] **Step 1: Full test suite**

Run: `& ".venv\Scripts\python.exe" -m pytest -q --no-header -p no:cacheprovider`
Expected: all green; total ≥ baseline (~2516 + new tests).

- [ ] **Step 2: Ruff on every touched file**

Run: `& ".venv\Scripts\python.exe" -m ruff check school/skeleton.py school/bridge.py school/mcp/server.py school/plugin_source.py tests/unit/test_school_skeleton.py tests/unit/test_school_plugin_bridge.py tests/unit/test_mcp_server.py tests/unit/test_school_plugin_hooks.py tests/integration/test_mcp_stdio.py tests/integration/test_plugin_live.py pyproject.toml`
Expected: no errors (or only pre-existing plugin_source.py E501s already in baseline).

- [ ] **Step 3: TS syntax check**

```powershell
& ".venv\Scripts\python.exe" -c "from pathlib import Path; from school.plugin_source import TS_PLUGIN_SOURCE; Path(r'C:\Users\dex34\AppData\Local\Temp\opencode\school-check.ts').write_text(TS_PLUGIN_SOURCE, encoding='utf-8')"
node --check C:\Users\dex34\AppData\Local\Temp\opencode\school-check.ts
```
Expected: exit 0.

- [ ] **Step 4: Install parity**

```powershell
& ".venv\Scripts\python.exe" -m school install --force
& ".venv\Scripts\python.exe" -c "from pathlib import Path; from school.plugin_source import TS_PLUGIN_SOURCE; inst = Path.home() / '.config/opencode/plugins/school.ts'; print('MATCH' if inst.read_text(encoding='utf-8') == TS_PLUGIN_SOURCE else 'MISMATCH')"
```
Expected: `MATCH`.

- [ ] **Step 5: Doctor**

Run: `& ".venv\Scripts\python.exe" -m school doctor`
Expected: all PASS.

- [ ] **Step 6: Commit any fixes (if steps 1–5 forced changes)**

```bash
git add -A
git commit -m "fix: context optimizer battery fixes"
```
If nothing changed, skip this commit.

---

## Self-Review

**1. Spec coverage**
- Threshold boundary 999/1001, raw below, one footer above → T1 (`TestBelowThreshold`, `TestTokenEstimate`).
- Footer format + dedupe + downstream strip → T1 (`TestFooter`, idempotence).
- Never-expand → T1 `TestNeverExpand`.
- Fail open (garbage, exceptions, bridge failure) → T1 `TestFailOpen`, T5 `ctxOptimize` catch, T2 `skeletonize_ast → None`.
- `SCHOOL_CTX=0` → T1 `TestKillSwitch`, T3 `test_kill_switch`, T6 `test_kill_switch_raw`.
- Big-6 AST contract tests → T2 `TestAstBigSix`.
- 2 heuristic-only samples (.sql, .yaml) → T1 `TestHeuristicContract`.
- Heuristic perf bound → T1 `test_perf_100kb_under_1s`.
- Bridge skeleton command → T3.
- MCP school_read/school_grep + offset/limit, validation/not_found/io, matches elision → T4.
- MCP stdio integration (raw small, skeletonized, unknown-path error) → T4 Step 5–6.
- Plugin source-contract (constants, footer, wiring order, kill switch, no new imports, 13 tools) → T5.
- Live oversized read through real Node → T6.
- Kill switch independent of SCHOOL_HOOKS → T5 uses `SCHOOL_CTX` only; existing `hooksEnabled` untouched.

**2. Placeholder scan** — no TBD/TODO/"similar to task N"; all code steps carry full code; description strings exact.

**3. Type consistency** — `optimize(text, filename="", strategy="auto") -> OptimizeResult` used identically in T3/T4; `ctxOptimize(python, bridgePath, text, filename)` matches T5 wiring call; bridge payload keys (`content/tokens_in/tokens_out/compressed/parser`) match T5 `r.content/r.compressed` reads and T3 handler; `_result`/`_error_result` used by both dispatchers; `skeletonize_ast(text, language) -> str | None` matches T1 stub and T2 implementation.

## Execution Notes

- Work on `main` (established session convention; repo is a git repo, branch `main`).
- Per-task commit; run the full battery (Task 7) at the end and after any cross-cutting fix.
- After Task 7 completes: report stopped adaptive-routing phases (T4 brief-written-never-dispatched, T5/T6 not started) and ask permission to resume them per the user's directive — unless the user has already granted it (check latest instructions), in which case resume T4–T6 next.

