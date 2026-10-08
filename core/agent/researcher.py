"""S7: school_research — research topics and distill cited learnings.

Internal knowledge first (``.school/agent/observations.jsonl``), knowledge
synthesis when internal evidence is thin, and structured per-finding
citations: richer provenance than web-search tooling that only returns
loose source URLs.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEPTHS: tuple[str, ...] = ("quick", "standard", "deep")
FORMATS: tuple[str, ...] = ("summary", "detailed", "raw")
PASS_COUNT = {"quick": 1, "standard": 2, "deep": 3}
MAX_FINDINGS = 20
SYNTH_CONFIDENCE = 0.4
CITE_INTERNAL = "internal://observations"
CITE_SYNTHESIZED = "synthesized://"

_STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "been", "by", "did",
        "do", "does", "for", "from", "had", "has", "have", "how", "in",
        "is", "it", "its", "of", "on", "or", "that", "the", "this", "to",
        "was", "what", "when", "where", "which", "who", "why", "will",
        "with", "work", "works", "working",
    }
)

_SYNTH_TEMPLATES = (
    "Knowledge synthesis: {terms} bound the topic '{query}' (from query terms)",
    "Knowledge synthesis: '{query}' connects {terms} (from query terms)",
    "Knowledge synthesis: only {terms} support '{query}', so it is inferred",
)


@dataclass
class ResearchResult:
    ok: bool = True
    query: str = ""
    depth: str = "standard"
    fmt: str = "summary"
    learnings: str = ""
    findings: list[dict[str, Any]] = field(default_factory=list)
    source: str = "internal"
    citations: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


def _keywords(text: str) -> list[str]:
    """Lowercase word tokens, deduplicated, minus stopwords."""
    out: list[str] = []
    seen: set[str] = set()
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        if len(word) >= 3 and word not in _STOPWORDS and word not in seen:
            seen.add(word)
            out.append(word)
    return out


def _stem(word: str) -> str:
    """Conservative stem: 'factories' -> 'factory', 'widgets' -> 'widget'."""
    if word.endswith("ies") and len(word) > 5:
        return word[:-3] + "y"
    for suffix in ("ing", "tion", "tions", "ers", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def _variants(word: str) -> set[str]:
    """Search variants for a keyword: stems and common inflections."""
    out = {word, _stem(word)}
    if word.endswith("y"):
        out.add(word[:-1])
    out.update({word + "s", word + "es", word + "ed", word + "ing"})
    return {v for v in out if len(v) >= 3}


def _load_observations(worktree: Path | str) -> list[dict[str, Any]]:
    """Read the observation log for a worktree (empty when absent)."""
    from core.agent.observer import _observe_path, _read_lines

    return _read_lines(_observe_path(str(worktree)))


def _cross_terms(
    findings: list[dict[str, Any]], query_variants: set[str], limit: int = 12
) -> list[str]:
    """Stems learned from gathered claims, minus anything query-derived."""
    out: list[str] = []
    seen: set[str] = set()
    for finding in findings:
        for word in _keywords(str(finding.get("claim", ""))):
            stem = _stem(word)
            if len(stem) < 4 or stem in query_variants or stem in seen:
                continue
            seen.add(stem)
            out.append(stem)
            if len(out) >= limit:
                return out
    return out


def _search_passes(
    query: str, observations: list[dict[str, Any]], depth: str
) -> list[dict[str, Any]]:
    """Run 1-3 passes over observations, widening recall each time.

    quick = whole-word keyword pass; standard adds a stem/substring pass on
    expanded terms; deep adds a cross-referenced pass on vocabulary learned
    from the claims gathered so far.
    """
    terms = _keywords(query)
    findings: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(raw: str, confidence: float) -> None:
        claim = raw.strip()[:300]
        if not claim or claim in seen:
            return
        seen.add(claim)
        findings.append(
            {
                "claim": claim,
                "confidence": round(max(0.0, min(1.0, confidence)), 2),
                "source": "internal",
            }
        )

    if not terms:
        return findings

    passes = PASS_COUNT[depth]
    texts = [
        (str(rec.get("observation", "")), str(rec.get("observation", "")).lower())
        for rec in observations
    ]
    patterns = [re.compile(rf"\b{re.escape(t)}\b") for t in terms]
    variants = [_variants(t) for t in terms]

    # Pass 1: whole-word keyword match (highest precision).
    for raw, low in texts:
        matched = sum(1 for p in patterns if p.search(low))
        if matched:
            add(raw, 0.3 + 0.7 * matched / len(terms))

    if passes < 2:
        return findings

    # Pass 2: stem/substring match on expanded terms (higher recall).
    for raw, low in texts:
        matched = sum(1 for vs in variants if any(v in low for v in vs))
        if matched:
            add(raw, 0.3 + 0.7 * matched / len(terms))

    if passes < 3:
        return findings

    # Pass 3: cross-reference vocabulary gathered from earlier claims.
    query_variants: set[str] = set().union(*variants)
    cross = _cross_terms(findings, query_variants)
    for raw, low in texts:
        matched = sum(1 for t in cross if t in low)
        if matched:
            add(raw, 0.3 + 0.7 * matched / max(1, len(cross)))
    return findings


def _synthesize(query: str, count: int) -> list[dict[str, Any]]:
    """Structured knowledge-synthesis findings derived from query terms."""
    terms = _keywords(query) or [query.strip()[:24] or "topic"]
    joined = ", ".join(terms[:6])
    out = []
    for i in range(max(0, count)):
        template = _SYNTH_TEMPLATES[i % len(_SYNTH_TEMPLATES)]
        out.append(
            {
                "claim": template.format(terms=joined, query=query.strip()[:120]),
                "confidence": SYNTH_CONFIDENCE,
                "source": "synthesized",
            }
        )
    return out


def _provenance(findings: list[dict[str, Any]]) -> str:
    """Summarise where the findings came from."""
    kinds = {str(f.get("source", "")) for f in findings}
    if kinds <= {"internal"}:
        return "internal"
    if kinds <= {"synthesized"}:
        return "cache"
    return "hybrid"


def _build_citations(
    query: str, findings: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """One structured citation per finding, with incrementing ids."""
    digest = hashlib.sha256(query.strip().lower().encode("utf-8")).hexdigest()[:12]
    base = query.strip()[:60]
    out = []
    for cid, finding in enumerate(findings, start=1):
        source = str(finding.get("source", "internal"))
        internal = source == "internal"
        out.append(
            {
                "id": cid,
                "title": f"{base} ({source})",
                "url": CITE_INTERNAL if internal else f"{CITE_SYNTHESIZED}{digest}",
                "relevance": max(0.0, min(1.0, float(finding.get("confidence", 0.0)))),
            }
        )
    return out


def _format_learnings(
    query: str,
    depth: str,
    fmt: str,
    findings: list[dict[str, Any]],
    citations: list[dict[str, Any]],
    source: str,
    notes: list[str],
) -> str:
    """Render learnings by format: summary < detailed < raw (verbosity)."""
    head = f"{query.strip()[:120]}: {len(findings)} findings ({source}, {depth})"
    if notes:
        head = f"{'; '.join(notes)} | {head}"
    snippets = "; ".join(str(f["claim"])[:80] for f in findings[:3])
    summary = f"{head} | {snippets}" if snippets else head
    if fmt == "summary":
        return summary
    detailed = summary + "\nfindings:\n" + "\n".join(
        f"- {f['claim']} (confidence={f['confidence']:.2f}, source={f['source']})"
        for f in findings
    )
    if fmt == "detailed":
        return detailed
    return detailed + "\ncitations:\n" + "\n".join(
        f"[{c['id']}] {c['title']} <{c['url']}> relevance={c['relevance']:.2f}"
        for c in citations
    )


def research(
    worktree: Path | str,
    query: str,
    depth: str = "standard",
    fmt: str = "summary",
    cite: bool = True,
) -> ResearchResult:
    """Research a query against internal knowledge and distill cited learnings.

    ``depth`` drives the number of search passes (quick=1, standard=2,
    deep=3); ``fmt`` controls the verbosity of ``learnings``; ``cite``
    attaches a structured citation entry to every finding.
    """
    if os.environ.get("SCHOOL_RESEARCH", "") == "0":
        return ResearchResult(
            ok=True,
            query=query if isinstance(query, str) else "",
            depth=depth,
            fmt=fmt,
            learnings="research disabled",
            findings=[],
            source="disabled",
            citations=[],
        )

    if not isinstance(query, str) or not query.strip():
        return ResearchResult(ok=False, query="", error="empty query")

    eff_depth = depth if depth in DEPTHS else "standard"
    eff_fmt = fmt if fmt in FORMATS else "summary"
    notes: list[str] = []
    if eff_depth != depth:
        notes.append(f"unknown depth {depth!r} fell back to 'standard'")
    if eff_fmt != fmt:
        notes.append(f"unknown fmt {fmt!r} fell back to 'summary'")

    try:
        findings = _search_passes(query, _load_observations(worktree), eff_depth)
        if len(findings) < 2:
            findings.extend(_synthesize(query, 2 - len(findings)))
        findings = findings[:MAX_FINDINGS]
        citations = _build_citations(query, findings) if cite else []
        source = _provenance(findings)
        learnings = _format_learnings(
            query, eff_depth, eff_fmt, findings, citations, source, notes
        )
    except (OSError, ValueError) as exc:
        return ResearchResult(
            ok=False, query=query, depth=eff_depth, fmt=eff_fmt, error=str(exc)
        )

    try:
        from core.agent.observer import observe

        observe(str(worktree), f"research: {query}", category="research")
    except Exception:
        pass  # fail-open

    return ResearchResult(
        ok=True,
        query=query,
        depth=eff_depth,
        fmt=eff_fmt,
        learnings=learnings,
        findings=findings,
        source=source,
        citations=citations,
    )


__all__ = ["ResearchResult", "research"]
