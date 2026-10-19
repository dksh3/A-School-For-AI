"""Adaptive diagnostic investigation: findings, hypotheses, evidence, next actions.

A case file records an investigation scope, a repository-grounded component map,
explicit hypotheses, structured findings, captured evidence, clarification
questions, and an auditable action log. State is JSON-serializable so an
investigation can resume after interruption or a blocker.

Honesty rules (enforced, not aspirational):
- A finding without evidence cannot be closed FIXED or VERIFIED.
- Confidence is a recorded judgment that requires a justification; it is never
  presented as a statistical measure.
- Prioritization is additive ordinal banding (like ``risk.ordinal_priority``) --
  an ordering, NOT a probability or an expected loss.
- A question with no recorded answer marks its affected conclusions BLOCKED /
  UNRESOLVED; the loop continues on independent paths.
- ``to_markdown`` never claims exhaustive discovery.

Probes run real commands (subprocess) and record the outcome as evidence; a
failed or timed-out probe is evidence, never an exception.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

_MAX_PROBE_OUTPUT = 2000


class Severity(StrEnum):
    """Triage vocabulary shared with the suite skills."""

    MUST_FIX = "must-fix"
    SHOULD_FIX = "should-fix"
    NOTE = "note"


class Classification(StrEnum):
    CONFIRMED_DEFECT = "CONFIRMED DEFECT"
    LIKELY_DEFECT = "LIKELY DEFECT"
    DESIGN_GAP = "DESIGN GAP"
    COVERAGE_GAP = "COVERAGE GAP"
    ENVIRONMENTAL_FAILURE = "ENVIRONMENTAL FAILURE"
    UNKNOWN = "UNKNOWN"


class FindingStatus(StrEnum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    BLOCKED = "BLOCKED"
    FIXED = "FIXED"
    VERIFIED = "VERIFIED"
    NOT_REPRODUCED = "NOT REPRODUCED"


class EvidenceKind(StrEnum):
    COMMAND = "command"
    TEST = "test"
    FILE = "file"
    TRACE = "trace"
    LOG = "log"
    OBSERVATION = "observation"


class Band(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _safe_str(value: Any, default: str = "") -> str:
    try:
        if value is None:
            return default
        return str(value)
    except Exception:  # noqa: BLE001
        return default


def _safe_list(value: Any) -> list[str]:
    try:
        if isinstance(value, list):
            return [str(v) for v in value]
        return []
    except Exception:  # noqa: BLE001
        return []


def _safe_float(value: Any, default: float = 0.5) -> float:
    try:
        result = float(value)
    except Exception:  # noqa: BLE001
        return default
    if result != result:  # NaN
        return default
    return max(0.0, min(1.0, result))


def _safe_enum(enum_cls: type[StrEnum], value: Any, default: StrEnum) -> StrEnum:
    try:
        return enum_cls(str(value))
    except Exception:  # noqa: BLE001
        return default


_SEVERITY_BAND: dict[str, int] = {
    Severity.MUST_FIX: 3,
    Severity.SHOULD_FIX: 2,
    Severity.NOTE: 1,
}
_LIKELIHOOD_BAND: dict[str, int] = {
    Band.HIGH: 2,
    Band.MEDIUM: 1,
    Band.LOW: 0,
    Band.UNKNOWN: 1,
}
_IMPACT_BAND: dict[str, int] = {
    Band.HIGH: 2,
    Band.MEDIUM: 1,
    Band.LOW: 0,
    Band.UNKNOWN: 1,
}
_UNCERTAINTY_BAND: dict[str, int] = {
    Band.HIGH: 1,
    Band.MEDIUM: 0,
    Band.LOW: 0,
    Band.UNKNOWN: 1,
}


@dataclass
class Evidence:
    id: str
    kind: EvidenceKind = EvidenceKind.OBSERVATION
    ref: str = ""
    detail: str = ""
    captured: str = ""

    def __post_init__(self) -> None:
        self.kind = _safe_enum(EvidenceKind, self.kind, EvidenceKind.OBSERVATION)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "ref": self.ref,
            "detail": self.detail,
            "captured": self.captured,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Evidence:
        d = data if isinstance(data, dict) else {}
        return cls(
            id=_safe_str(d.get("id")),
            kind=_safe_enum(EvidenceKind, d.get("kind"), EvidenceKind.OBSERVATION),  # type: ignore[arg-type]
            ref=_safe_str(d.get("ref")),
            detail=_safe_str(d.get("detail")),
            captured=_safe_str(d.get("captured")),
        )


@dataclass
class Hypothesis:
    id: str
    statement: str
    confidence: float = 0.5
    justification: str = ""
    supporting: list[str] = field(default_factory=list)
    refuting: list[str] = field(default_factory=list)
    status: str = "open"  # open | supported | refuted | superseded

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "statement": self.statement,
            "confidence": self.confidence,
            "justification": self.justification,
            "supporting": list(self.supporting),
            "refuting": list(self.refuting),
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Hypothesis:
        d = data if isinstance(data, dict) else {}
        return cls(
            id=_safe_str(d.get("id")),
            statement=_safe_str(d.get("statement")),
            confidence=_safe_float(d.get("confidence")),
            justification=_safe_str(d.get("justification")),
            supporting=_safe_list(d.get("supporting")),
            refuting=_safe_list(d.get("refuting")),
            status=_safe_str(d.get("status"), "open"),
        )


@dataclass
class Finding:
    id: str
    title: str
    severity: Severity = Severity.NOTE
    component: str = ""
    entry_point: str = ""
    expected: str = ""
    observed: str = ""
    reproduction: str = ""
    reproduction_unavailable: str = ""
    evidence: list[str] = field(default_factory=list)
    classification: Classification = Classification.UNKNOWN
    likelihood: Band = Band.UNKNOWN
    impact: Band = Band.UNKNOWN
    uncertainty: Band = Band.MEDIUM
    confidence: float = 0.5
    confidence_justification: str = ""
    root_cause: str = ""
    root_cause_supported: bool = False
    related: list[str] = field(default_factory=list)
    status: FindingStatus = FindingStatus.OPEN
    next_action: str = ""

    def __post_init__(self) -> None:
        self.severity = _safe_enum(Severity, self.severity, Severity.NOTE)
        self.classification = _safe_enum(
            Classification, self.classification, Classification.UNKNOWN
        )
        self.likelihood = _safe_enum(Band, self.likelihood, Band.UNKNOWN)
        self.impact = _safe_enum(Band, self.impact, Band.UNKNOWN)
        self.uncertainty = _safe_enum(Band, self.uncertainty, Band.MEDIUM)
        self.status = _safe_enum(FindingStatus, self.status, FindingStatus.OPEN)

    def priority(self) -> int:
        """Additive ordinal band (ordering only -- never a probability)."""
        return (
            _SEVERITY_BAND.get(self.severity, 1)
            + _LIKELIHOOD_BAND.get(self.likelihood, 1)
            + _IMPACT_BAND.get(self.impact, 1)
            + _UNCERTAINTY_BAND.get(self.uncertainty, 0)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "severity": self.severity.value,
            "component": self.component,
            "entry_point": self.entry_point,
            "expected": self.expected,
            "observed": self.observed,
            "reproduction": self.reproduction,
            "reproduction_unavailable": self.reproduction_unavailable,
            "evidence": list(self.evidence),
            "classification": self.classification.value,
            "likelihood": self.likelihood.value,
            "impact": self.impact.value,
            "uncertainty": self.uncertainty.value,
            "confidence": self.confidence,
            "confidence_justification": self.confidence_justification,
            "root_cause": self.root_cause,
            "root_cause_supported": self.root_cause_supported,
            "related": list(self.related),
            "status": self.status.value,
            "next_action": self.next_action,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Finding:
        d = data if isinstance(data, dict) else {}
        return cls(
            id=_safe_str(d.get("id")),
            title=_safe_str(d.get("title")),
            severity=_safe_enum(Severity, d.get("severity"), Severity.NOTE),  # type: ignore[arg-type]
            component=_safe_str(d.get("component")),
            entry_point=_safe_str(d.get("entry_point")),
            expected=_safe_str(d.get("expected")),
            observed=_safe_str(d.get("observed")),
            reproduction=_safe_str(d.get("reproduction")),
            reproduction_unavailable=_safe_str(d.get("reproduction_unavailable")),
            evidence=_safe_list(d.get("evidence")),
            classification=_safe_enum(
                Classification, d.get("classification"), Classification.UNKNOWN
            ),  # type: ignore[arg-type]
            likelihood=_safe_enum(Band, d.get("likelihood"), Band.UNKNOWN),  # type: ignore[arg-type]
            impact=_safe_enum(Band, d.get("impact"), Band.UNKNOWN),  # type: ignore[arg-type]
            uncertainty=_safe_enum(Band, d.get("uncertainty"), Band.MEDIUM),  # type: ignore[arg-type]
            confidence=_safe_float(d.get("confidence")),
            confidence_justification=_safe_str(d.get("confidence_justification")),
            root_cause=_safe_str(d.get("root_cause")),
            root_cause_supported=bool(d.get("root_cause_supported")),
            related=_safe_list(d.get("related")),
            status=_safe_enum(FindingStatus, d.get("status"), FindingStatus.OPEN),  # type: ignore[arg-type]
            next_action=_safe_str(d.get("next_action")),
        )


_ACTION_BY_STATUS: dict[str, str] = {
    FindingStatus.INVESTIGATING: "probe",
    FindingStatus.BLOCKED: "ask",
    FindingStatus.FIXED: "verify",
    FindingStatus.NOT_REPRODUCED: "reprobe",
}

_ACTION_BY_CLASS: dict[str, str] = {
    Classification.CONFIRMED_DEFECT: "fix",
    Classification.LIKELY_DEFECT: "probe",
    Classification.UNKNOWN: "probe",
    Classification.COVERAGE_GAP: "inspect",
    Classification.DESIGN_GAP: "inspect",
    Classification.ENVIRONMENTAL_FAILURE: "reprobe",
}


@dataclass
class Investigation:
    id: str
    title: str
    scope: str = ""
    acceptance_criteria: list[str] = field(default_factory=list)
    component_map: dict[str, str] = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    questions: list[dict[str, str]] = field(default_factory=list)
    actions: list[dict[str, str]] = field(default_factory=list)
    created: str = ""
    updated: str = ""

    # ---------- construction helpers ----------

    @classmethod
    def start(cls, investigation_id: str, title: str, scope: str = "") -> Investigation:
        now = _now()
        case = cls(id=investigation_id, title=title, scope=scope, created=now, updated=now)
        case.record_action("start", title, "investigation opened")
        return case

    def _next_id(self, prefix: str, items: list[Any]) -> str:
        used = {_safe_str(getattr(item, "id", "")) for item in items}
        index = 1
        while f"{prefix}-{index:03d}" in used:
            index += 1
        return f"{prefix}-{index:03d}"

    def add_evidence(self, kind: str, ref: str, detail: str = "") -> Evidence:
        evidence = Evidence(
            id=self._next_id("E", self.evidence),
            kind=_safe_enum(EvidenceKind, kind, EvidenceKind.OBSERVATION),  # type: ignore[arg-type]
            ref=_safe_str(ref),
            detail=_safe_str(detail),
            captured=_now(),
        )
        self.evidence.append(evidence)
        self.updated = _now()
        return evidence

    def add_hypothesis(
        self, statement: str, confidence: float = 0.5, justification: str = ""
    ) -> Hypothesis:
        hypothesis = Hypothesis(
            id=self._next_id("H", self.hypotheses),
            statement=_safe_str(statement),
            confidence=_safe_float(confidence),
            justification=_safe_str(justification),
        )
        self.hypotheses.append(hypothesis)
        self.updated = _now()
        return hypothesis

    def add_finding(self, title: str, **fields: Any) -> Finding:
        finding = Finding(id=self._next_id("F", self.findings), title=_safe_str(title), **fields)
        self.findings.append(finding)
        self.updated = _now()
        self.record_action("finding", finding.id, finding.title)
        return finding

    # ---------- hypothesis + evidence wiring ----------

    def link_evidence(self, hypothesis_id: str, evidence_id: str, *, support: bool) -> None:
        hypothesis = self._hypothesis(hypothesis_id)
        self._evidence(evidence_id)
        target = hypothesis.supporting if support else hypothesis.refuting
        if evidence_id not in target:
            target.append(evidence_id)
        self.updated = _now()

    def set_confidence(self, hypothesis_id: str, value: float, justification: str) -> None:
        if not _safe_str(justification).strip():
            raise ValueError("confidence requires a justification")
        hypothesis = self._hypothesis(hypothesis_id)
        hypothesis.confidence = _safe_float(value)
        hypothesis.justification = _safe_str(justification)
        self.updated = _now()

    def _hypothesis(self, hypothesis_id: str) -> Hypothesis:
        for hypothesis in self.hypotheses:
            if hypothesis.id == hypothesis_id:
                return hypothesis
        raise KeyError(f"unknown hypothesis: {hypothesis_id}")

    def _finding(self, finding_id: str) -> Finding:
        for finding in self.findings:
            if finding.id == finding_id:
                return finding
        raise KeyError(f"unknown finding: {finding_id}")

    def _evidence(self, evidence_id: str) -> Evidence:
        for item in self.evidence:
            if item.id == evidence_id:
                return item
        raise KeyError(f"unknown evidence: {evidence_id}")

    def attach_evidence(self, finding_id: str, evidence_id: str) -> None:
        finding = self._finding(finding_id)
        self._evidence(evidence_id)
        if evidence_id not in finding.evidence:
            finding.evidence.append(evidence_id)
        self.updated = _now()

    def set_status(self, finding_id: str, status: str) -> Finding:
        finding = self._finding(finding_id)
        try:
            new_status = FindingStatus(status)  # canonical value, e.g. "NOT REPRODUCED"
        except ValueError:
            key = str(status).strip().upper().replace("-", "_").replace(" ", "_")
            try:
                new_status = FindingStatus[key]  # member name form, e.g. "NOT_REPRODUCED"
            except KeyError:
                raise ValueError(f"unknown finding status: {status!r}") from None
        if new_status in (FindingStatus.FIXED, FindingStatus.VERIFIED) and not finding.evidence:
            raise ValueError(
                "closing a finding requires evidence (missing evidence is not success)"
            )
        finding.status = new_status  # type: ignore[assignment]
        self.updated = _now()
        self.record_action("status", finding_id, str(new_status))
        return finding

    # ---------- questions (targeted clarification) ----------

    def record_question(self, question: str, why: str) -> str:
        normalized = " ".join(_safe_str(question).split()).casefold()
        for item in self.questions:
            if " ".join(_safe_str(item.get("question")).split()).casefold() == normalized:
                raise ValueError(
                    f"question already recorded: {item.get('id')} "
                    "(answered questions are never re-asked)"
                )
        question_id = f"Q-{len(self.questions) + 1:03d}"
        self.questions.append(
            {
                "id": question_id,
                "question": _safe_str(question),
                "why": _safe_str(why),
                "answer": "",
                "effect": "",
            }
        )
        self.updated = _now()
        self.record_action("ask", question_id, _safe_str(question))
        return question_id

    def answer_question(self, question_id: str, answer: str, effect: str) -> None:
        for item in self.questions:
            if item.get("id") == question_id:
                item["answer"] = _safe_str(answer)
                item["effect"] = _safe_str(effect)
                self.updated = _now()
                return
        raise KeyError(f"unknown question: {question_id}")

    def open_questions(self) -> list[dict[str, str]]:
        return [q for q in self.questions if not q.get("answer")]

    # ---------- action log ----------

    def record_action(self, action: str, target: str, result: str) -> None:
        self.actions.append(
            {"at": _now(), "action": _safe_str(action), "target": _safe_str(target),
             "result": _safe_str(result)}
        )
        self.updated = _now()

    # ---------- probes ----------

    def probe(
        self,
        command: str,
        *,
        kind: str = "command",
        ref: str = "",
        timeout_s: float = 60.0,
        cwd: str | None = None,
    ) -> Evidence:
        """Run a real command and record the outcome as evidence.

        A non-zero exit or timeout is captured as evidence detail; this method
        does not raise for probe failures.
        """
        detail = ""
        try:
            completed = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                cwd=cwd,
            )
            out = (completed.stdout or "") + (completed.stderr or "")
            if len(out) > _MAX_PROBE_OUTPUT:
                out = out[:_MAX_PROBE_OUTPUT] + "…[truncated]"
            detail = f"exit={completed.returncode}\n{out}".strip()
        except subprocess.TimeoutExpired:
            detail = f"TIMEOUT after {timeout_s}s — no result claimed"
        except Exception as exc:  # noqa: BLE001
            detail = f"probe error: {exc!r} — no result claimed"
        evidence = self.add_evidence(kind, ref or command, detail)
        self.record_action("probe", ref or command, detail.splitlines()[0] if detail else "done")
        return evidence

    # ---------- adaptive next action ----------

    def next_action(self) -> dict[str, str] | None:
        """Highest-priority open item and the action its state calls for."""
        candidates = [f for f in self.findings if f.status != FindingStatus.VERIFIED]
        candidates.sort(key=lambda f: (-f.priority(), f.id))
        if not candidates:
            if self.open_questions():
                first = self.open_questions()[0]
                return {
                    "target": first.get("id", ""),
                    "action_kind": "ask",
                    "reason": "open question with no recorded answer",
                }
            return None
        top = candidates[0]
        if top.status == FindingStatus.OPEN:
            action = _ACTION_BY_CLASS.get(top.classification, "probe")
        else:
            action = _ACTION_BY_STATUS.get(top.status, "probe")
        if top.status == FindingStatus.OPEN and self.open_questions():
            action = "ask"
        top.next_action = action
        return {"target": top.id, "action_kind": action, "reason": top.title}

    def assessment(self) -> dict[str, Any]:
        return {
            "findings": len(self.findings),
            "by_status": {
                str(s): sum(1 for f in self.findings if f.status == s) for s in FindingStatus
            },
            "by_classification": {
                str(c): sum(1 for f in self.findings if f.classification == c)
                for c in Classification
            },
            "open_questions": len(self.open_questions()),
            "hypotheses": len(self.hypotheses),
            "evidence": len(self.evidence),
            "next": self.next_action(),
        }

    # ---------- persistence (resumable) ----------

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "scope": self.scope,
            "acceptance_criteria": list(self.acceptance_criteria),
            "component_map": dict(self.component_map),
            "evidence": [e.to_dict() for e in self.evidence],
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "findings": [f.to_dict() for f in self.findings],
            "questions": [dict(q) for q in self.questions],
            "actions": [dict(a) for a in self.actions],
            "created": self.created,
            "updated": self.updated,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Investigation:
        d = data if isinstance(data, dict) else {}
        case = cls(
            id=_safe_str(d.get("id")),
            title=_safe_str(d.get("title")),
            scope=_safe_str(d.get("scope")),
            acceptance_criteria=_safe_list(d.get("acceptance_criteria")),
            component_map={
                _safe_str(k): _safe_str(v)
                for k, v in (d.get("component_map") or {}).items()
            }
            if isinstance(d.get("component_map"), dict)
            else {},
            created=_safe_str(d.get("created")),
            updated=_safe_str(d.get("updated")),
        )
        raw = d.get("evidence")
        if isinstance(raw, list):
            case.evidence = [Evidence.from_dict(x) for x in raw]
        raw = d.get("hypotheses")
        if isinstance(raw, list):
            case.hypotheses = [Hypothesis.from_dict(x) for x in raw]
        raw = d.get("findings")
        if isinstance(raw, list):
            case.findings = [Finding.from_dict(x) for x in raw]
        raw = d.get("questions")
        if isinstance(raw, list):
            case.questions = [dict(q) if isinstance(q, dict) else {} for q in raw]
        raw = d.get("actions")
        if isinstance(raw, list):
            case.actions = [dict(a) if isinstance(a, dict) else {} for a in raw]
        return case

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        os.replace(tmp, target)

    @classmethod
    def load(cls, path: str | Path) -> Investigation:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    # ---------- honest report ----------

    def to_markdown(self) -> str:
        lines: list[str] = []
        lines.append(f"# Investigation: {self.title}")
        lines.append("")
        lines.append(f"- id: `{self.id}` · opened: {self.created} · updated: {self.updated}")
        if self.scope:
            lines.append(f"- scope: {self.scope}")
        lines.append("")
        if self.acceptance_criteria:
            lines.append("## Acceptance criteria")
            for item in self.acceptance_criteria:
                lines.append(f"- [ ] {item}")
            lines.append("")
        if self.component_map:
            lines.append("## Component map")
            for name, role in self.component_map.items():
                lines.append(f"- `{name}` — {role}")
            lines.append("")
        lines.append("## Findings (highest priority first)")
        ordered = sorted(self.findings, key=lambda f: (-f.priority(), f.id))
        if not ordered:
            lines.append("_No findings recorded._")
        for f in ordered:
            lines.append("")
            lines.append(f"### {f.id} [{f.severity.value}] {f.title}")
            lines.append(f"- classification: {f.classification.value} · status: {f.status.value}"
                         f" · priority band: {f.priority()}")
            lines.append(f"- component: {f.component} · entry point: {f.entry_point}")
            if f.expected:
                lines.append(f"- expected: {f.expected}")
            if f.observed:
                lines.append(f"- observed: {f.observed}")
            if f.reproduction:
                lines.append(f"- reproduction: {f.reproduction}")
            elif f.reproduction_unavailable:
                lines.append(f"- reproduction unavailable: {f.reproduction_unavailable}")
            else:
                lines.append("- reproduction: NOT RECORDED")
            if f.evidence:
                refs = ", ".join(f.evidence)
                lines.append(f"- evidence: {refs}")
            else:
                lines.append("- evidence: NONE RECORDED (this finding cannot be closed)")
            lines.append(f"- confidence: {f.confidence:.2f}"
                         + (f" — {f.confidence_justification}" if f.confidence_justification
                            else " — NO JUSTIFICATION RECORDED"))
            if f.root_cause_supported and f.root_cause:
                lines.append(f"- root cause: {f.root_cause}")
            else:
                lines.append("- root cause: not established")
            if f.related:
                lines.append(f"- related: {', '.join(f.related)}")
            if f.next_action:
                lines.append(f"- next action: {f.next_action}")
        lines.append("")
        lines.append("## Hypotheses")
        if not self.hypotheses:
            lines.append("_No hypotheses recorded._")
        for h in self.hypotheses:
            support = ", ".join(h.supporting) or "—"
            refute = ", ".join(h.refuting) or "—"
            lines.append(f"- `{h.id}` [{h.status}] {h.statement}")
            lines.append(f"  - confidence: {h.confidence:.2f}"
                         + (f" — {h.justification}" if h.justification else " — NO JUSTIFICATION"))
            lines.append(f"  - supporting: {support} · refuting: {refute}")
        lines.append("")
        lines.append("## Clarification questions")
        if not self.questions:
            lines.append("_No questions asked._")
        for q in self.questions:
            if q.get("answer"):
                lines.append(f"- `{q.get('id')}` {q.get('question')}")
                lines.append(f"  - answer: {q.get('answer')}")
                lines.append(f"  - effect: {q.get('effect')}")
            else:
                lines.append(f"- `{q.get('id')}` {q.get('question')} — **UNRESOLVED** "
                             f"(affected conclusions are marked BLOCKED)")
                lines.append(f"  - why it matters: {q.get('why')}")
        lines.append("")
        lines.append("## Action log")
        for a in self.actions:
            lines.append(
                f"- {a.get('at')} · {a.get('action')} · {a.get('target')} — {a.get('result')}"
            )
        lines.append("")
        lines.append("## Limitations")
        lines.append("- This report does not claim exhaustive discovery of every possible defect.")
        lines.append("- Confidence values are recorded judgments with justifications, "
                     "not statistical measures.")
        lines.append("- Priority bands are additive ordinal ordering, not probabilities "
                     "or expected losses.")
        lines.append("- Missing evidence is never treated as success.")
        return "\n".join(lines) + "\n"
