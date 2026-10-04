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

# Frequent top-level modules kept even when no usage reference is found:
# they are plausibly part of the file's interface and are cheap to retain.
_COMMON_IMPORTS = frozenset(
    {
        "os", "sys", "re", "json", "math", "time", "typing", "pathlib",
        "collections", "itertools", "functools", "subprocess", "logging",
        "unittest", "asyncio", "contextlib", "random", "datetime", "copy",
        "enum", "abc", "io", "fs", "http",
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
LOOP_RE = re.compile(r"^\s*(for|while|do)\b")
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
        dq = line.count('"""')
        sq = line.count("'''")
        tick = line.count("`")
        if dq >= 2:
            # Complete triple-quoted string on one line (e.g. a docstring).
            kinds.append("string_first")
        elif dq == 1:
            kinds.append("string_first")
            mode = '"""'
        elif sq >= 2:
            kinds.append("string_first")
        elif sq == 1:
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
        # DECL_RE's trailing [A-Za-z_$] consumes the name's first character.
        rest = line[m.end() - 1:].lstrip()
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
    comment_markers: dict[int, str] = {}
    first_block = True
    header_comments = 0
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
                comment_markers[start] = (
                    f"{prefix} … license banner — {i - start} lines"
                )
            else:
                keep = 0
                for j in range(start, i):
                    if keep < 3:
                        keep += 1
                    else:
                        drop[j] = True
                if i - start - keep >= 2:
                    comment_markers[start + keep] = (
                        f"{prefix} … {i - start - keep} lines"
                    )
            header_comments = i
            first_block = False
        else:
            for j in range(start, i):
                drop[j] = True
            if i - start >= 2:
                comment_markers[start] = f"{prefix} … {i - start} lines"

    # Import-name reference set (from non-import lines).
    refset: set[str] = set()
    for idx, line in enumerate(lines):
        if kinds[idx] == "code" and not _is_import(line):
            refset |= set(IDENT_RE.findall(line))

    # Pass 1: decide keep/drop per line.
    kept_depth = 0
    keep_flags: list[bool] = [False] * len(lines)
    cls_list: list[str] = [""] * len(lines)
    prev_kept: bool | None = None
    for idx, line in enumerate(lines):
        kind = kinds[idx]
        if drop[idx]:
            if kind != "blank":
                prev_kept = False
            continue
        if kind == "blank":
            keep_flags[idx] = True
            continue
        if kind == "string_first":
            keep_flags[idx] = True
            prev_kept = True
            continue
        if kind == "string_cont":
            prev_kept = False
            continue
        if kind == "comment":
            keep_flags[idx] = header_comments > 0 and idx < header_comments
            prev_kept = keep_flags[idx]
            continue
        cls = _keep_class(line, ext, "code")
        cls_list[idx] = cls
        if kept_depth > 0:
            keep_flags[idx] = True
            kept_depth += _depth_delta(line)
            prev_kept = True
            continue
        if cls in {"import", "decorator", "decl", "control", "closer",
                   "sql", "yaml", "sig"}:
            if cls == "import":
                names = _import_names(line)
                if not (names & refset) and not (names & _COMMON_IMPORTS):
                    prev_kept = False
                    continue  # unreferenced import → dropped
            if cls == "control" and LOOP_RE.match(line) and prev_kept is not True:
                # A loop whose preceding statement was dropped reads as noise;
                # keep loops only when they continue a kept chain.
                prev_kept = False
                continue
            keep_flags[idx] = True
            kept_depth += _depth_delta(line)
            prev_kept = True
            continue
        prev_kept = False
        # body line while depth == 0 → dropped

    # Pass 2: emit with run markers.
    out: list[str] = []
    run: list[int] = []
    run_label = "body"
    label = "body"

    def flush() -> None:
        nonlocal run
        if len(run) >= 2:
            out.append(f"{prefix} … {run_label} — {len(run)} lines")
        run = []

    pending_blank = False
    for idx, line in enumerate(lines):
        if idx in comment_markers:
            flush()
            out.append(comment_markers[idx])
            continue
        if drop[idx]:
            continue
        if not keep_flags[idx]:
            if kinds[idx] == "blank":
                continue
            if not run:
                run_label = label
            run.append(idx)
            continue
        flush()
        if kinds[idx] == "blank":
            if pending_blank:
                continue
            pending_blank = True
            out.append("")
        else:
            pending_blank = False
            out.append(line)
            if cls_list[idx] == "decl":
                label = _decl_label(line)
    flush()
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
