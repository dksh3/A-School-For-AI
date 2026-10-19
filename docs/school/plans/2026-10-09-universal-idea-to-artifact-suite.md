# Universal Idea→Artifact Suite — Design & Build Plan

**Date:** 2026-10-09
**Status:** PLAN (pending name/scope confirmation before build)
**Scope:** Every kind of AI agent — coding, writing, research, planning, business,
education, creative, ops, life. NOT coding-only.
**Standing constraint:** Apple-grade presentation. Fail-open everywhere. Kill switches.
Visual output via the existing 101-renderer system.

---

## 1. Vision

Turn a fuzzy user intent into a complete, actionable set of artifacts by asking
**accurate adaptive questions** and letting the user answer with **pick-one-or-custom**
choices. The engine then synthesizes everything the user named — a design spec,
commands, directives, formations, and more — each with its **own distinct name**
(not everything under one "specer" banner).

This is superpowers' brainstorming + writing-plans + SDD workflow, rebuilt **10x
better** and made **universal**, with the industry's best techniques folded in and
sharpened.

### What "10x better" means concretely
| superpowers does | Our 10x |
|---|---|
| Free-form "ask clarifying questions one at a time" | **Structured adaptive interview** with scored dimensions, branching follow-ups, pick-or-custom answers |
| 3 fixed paths (spike/bounded/architectural) | **Continuous scope meter** + auto-decomposition into sub-projects |
| Prose design doc | **5 distinct generated artifacts** (spec + commands + directives + formations + acceptance), each named |
| Brainstorming = "propose 2-3 approaches" | **Multi-technique divergent engine** (first-principles, SCAMPER, role-storm, analogical, inversion) + convergent scoring + clustering |
| Text-only output | **Visual output** via School's 101 renderers (radar, mind-map, kanban, decision-matrix, timeline…) |
| Coding-centric ("write failing test", "git commit") | **Universal domain templates** (coding, writing, research, business, education, creative, ops, life) |
| Manual spec self-review | **Automated lint** (placeholders, contradictions, ambiguity, scope) with scores |

---

## 2. Research findings (what we're improving on)

### 2.1 superpowers (local source read)
- **brainstorming/SKILL.md** — HARD-GATE approval, 3 paths (spike/bounded/architectural),
  one-question-at-a-time, 2-3 approaches, sectioned design, spec self-review, visual
  companion (browser), red-flags table. Strengths: discipline, approval gate, YAGNI.
  Weaknesses: free-form questioning (not systematic), text-only, coding-centric, one output.
- **writing-plans/SKILL.md** — bite-sized 2-5 min tasks, TDD, exact file paths, task
  right-sizing, plan header for agentic workers. Good skeleton to inherit.
- **14 skills total** — brainstorming, writing-plans, TDD, systematic-debugging,
  verification-before-completion, dispatching-parallel-agents, code-review, git-worktrees,
  writing-skills, etc. We will 10x and rename the valuable ones.

### 2.2 Internet best practice (fetched 2026)
- **SDD:** spec is the primary artifact; must be readable by agents + people; the right
  amount of detail; keep spec↔impl in sync; acceptance criteria with concrete I/O.
- **Spec anatomy (Augment/SSOJet):** mandatory sections = goal, non-goals, acceptance
  criteria (Given/When/Then), constraints, open questions, success metrics.
- **Brainstorming:** divergent→convergent; GPS framework (3-level: goal→approach→detail);
  first-principles; SCAMPER; role-storming; impact-vs-effort scoring; clustering.
- **Requirements interview:** discovery questions (purpose, users, constraints, success,
  risks, edge cases); acceptance criteria as the definition of "done".

---

## 3. The Suite — distinct names (NOT all "specer")

The interview engine produces **five named artifacts**, and the ideation + skill
abilities each carry their own name. Recommended codename theme: **craft of turning
intent into reality**. (Alternative names in §8 — user picks before build.)

### 3.1 The core engine + its 5 named outputs

| # | Name | Role | Output |
|---|---|---|---|
| **A** | **`clarion`** | The **Discovery Interview** engine (the "specer" core). Asks accurate, adaptive, scored questions; user answers pick-one-or-custom; branches follow-ups. | A structured **Requirement Set** (intent, audience, scope, constraints, success, resources, risks, sequence, edge-cases) |
| **B** | **`blueprint`** | The **Design Spec** builder. | goals · non-goals · architecture · components · data-flow · acceptance-criteria (Given/When/Then) · risks · decomposition · glossary · success-metrics |
| **C** | **`edict`** | **Commands & Directives** generator. | **Commands** = ordered executable actions/instructions. **Directives** = governing "always/never" rules that must hold throughout |
| **D** | **`weave`** | **Formations** builder. | The structure & sequencing: phases, roadmap, dependency graph, parallel lanes, milestones, critical-path |
| **E** | **`compass`** | **Acceptance & alignment**. | Testable acceptance checklist, success metrics, definition-of-done, verification steps |

> Flow: `clarion` (ask) → user answers → synthesizes `blueprint` + `edict` + `weave`
> + `compass` in one pass (or one-at-a-time). Each artifact is separately named,
> versioned, and rendered with visuals.

### 3.2 The brainstorming engine (10x superpowers' brainstorming)

| Name | Role |
|---|---|
| **`prism`** | **Ideation engine** — splits intent into a spectrum of possibilities. Divergent (first-principles, SCAMPER, role-storm, analogical, inversion, random-association) → convergent (impact/effort scoring, feasibility, novelty) → clustered synthesis → feeds `clarion`. |

### 3.3 The skill pack (10x the industry's best, renamed)

Each is a named skill, universal (not coding-only), with visual output:

| New name | 10x of | Universal twist |
|---|---|---|
| **`forge`** | test-driven-development | Test/verify-first for ANY deliverable (essays, plans, campaigns) |
| **`triage`** | systematic-debugging | Root-cause method for any failure (a bug, a lost customer, a bad grade) |
| **`chart`** | writing-plans | Roadmap/bite-sized-step writer for any project |
| **`gate`** | verification-before-completion | Definition-of-done checker with a visual checklist |
| **`relay`** | dispatching-parallel-agents | Fan-out work decomposition + merge, any agent |
| **`scrutinize`** | code-review (requesting/receiving) | Review & self-critique for any artifact |
| **`compass`** | (new) | Acceptance/alignment (from §3.1) |

---

## 4. Universal domain model (every agent, not just coding)

`clarion`/`blueprint`/etc. are **domain-aware**. A `domain` field selects the template
that shapes questions + artifact language. Built-in domains:

`coding` · `writing` · `research` · `business` · `planning` · `education` ·
`creative` · `ops` · `data` · `life` · `general`

- **coding** acceptance: "unit tests pass", "Given/When/Then"
- **writing** acceptance: "tone matches brief", "word count", "audience satisfied"
- **research** acceptance: "sources cited", "question answered", "confidence stated"
- **business** acceptance: "stakeholder sign-off", "metric moved", "budget respected"
- **education** acceptance: "learner can demonstrate X", "rubric met"
- **creative** acceptance: "brief honored", "originality", "emotional impact"
- … each domain ships a question-bank + artifact template + acceptance style.

Unknown/other → `general` domain (generic intent/goals/constraints/success).

---

## 5. The interview engine (`clarion`) in detail

### 5.1 Adaptive question model
Each **question** = `{ id, dimension, prompt, type, options[], allow_custom, followups }`
- `type`: `choice` (pick-one, one option = "custom…"), `multi`, `scale`, `text`, `confirm`
- **pick-one-or-custom**: every choice question includes a `"(your own)…"` free-text escape.
- **Adaptive branching**: an answer selects follow-up questions (e.g. choosing
  `audience=enterprise` surfaces compliance questions).
- **Scored dimensions**: each dimension has a confidence score; the engine keeps asking
  in the weakest dimension until confidence ≥ threshold (or user says enough).

### 5.2 Dimensions (universal)
`intent` · `audience` · `scope` · `constraints` · `success` · `resources` · `risks` ·
`sequence` · `style` · `edge_cases` · `glossary` · `open_questions`

### 5.3 Interaction modes
- **Interview mode** — one question per turn, pick-or-custom (the default).
- **Batch mode** — dump a form of all questions; user fills; engine parses.
- **Auto mode** — engine infers answers from a description + repo/context, marks low-confidence items as open questions (for a fast path).
- **Import mode** — start from an existing doc/PRD/repo and interview only the gaps.

---

## 6. Output artifacts (what the user asked: "spec, commands, directives, formations, and everything")

1. **`blueprint`** — the design spec (§3.1 B). Markdown + visual (architecture tree, dashboard).
2. **`edict.commands`** — ordered, executable action list (each step: do-X, inputs, done-when).
3. **`edict.directives`** — governing rules ("always …", "never …", "when X, do Y").
4. **`weave.formations`** — phases, roadmap, dependency graph, parallel lanes, critical path (visual timeline / Gantt / kanban).
5. **`compass.acceptance`** — Given/When/Then + checklist + success metrics.
6. **Everything-else bundle** — glossary, open questions, risks register, decomposition
   into sub-projects, traceability matrix (requirement → command → acceptance).

All artifacts are stored as structured JSON (`.school/forge/<slug>/…`) + rendered as
Markdown + School visuals. Versioned; re-interviewable; exportable.

---

## 7. Technical architecture & wiring

```
core/forge/                      # new Python package (engine, universal)
  clarion.py      # interview engine (questions, branching, scoring)
  blueprint.py    # spec builder
  edict.py        # commands + directives
  weave.py        # formations / roadmap / sequencing
  compass.py      # acceptance / metrics
  prism.py        # brainstorming (divergent/convergent)
  domains/        # question-banks + templates per domain
  models.py       # dataclasses: Requirement, Question, Spec, Command, Directive, Formation
  render.py       # artifact → Markdown + School visuals (reuse visual_dispatch)
```

Wired across all three surfaces like every other School tool:
- **Bridge** commands: `clarion`, `blueprint`, `edict`, `weave`, `compass`, `prism`
- **TS plugin** tools: `school_clarion`, `school_blueprint`, `school_edict`,
  `school_weave`, `school_compass`, `school_brainstorm` (+ dominance + guard + visuals)
- **MCP** tools: same 6
- **CLI**: `school clarion|blueprint|edict|weave|compass|brainstorm`
- **Skills**: `clarion`, `prism`, `forge`, `triage`, `chart`, `gate`, `relay`, `scrutinize`

Guard: every competitor (superpowers brainstorming, writing-plans, spec tools) maps to
the matching School tool via the existing 11-layer guard + duel-proof banner.

---

## 8. Naming — pick before build (names are important)

**Recommended set** (craft-of-creation theme, all distinct, none is "specer"):

`clarion` (interview) · `blueprint` (spec) · `edict` (commands/directives) ·
`weave` (formations) · `compass` (acceptance) · `prism` (brainstorm) ·
`forge`/`triage`/`chart`/`gate`/`relay`/`scrutinize` (skill pack)

**Alternative themes (if you prefer a different flavor):**

- **Navigation theme:** `compass`/`chart`/`beacon`/`horizon`/`anchor`/`compass-rose`
- **Architecture theme:** `blueprint`/`scaffold`/`keystone`/`arch`/`lintel`/`mortar`
- **Command theme:** `clarion`/`edict`/`mandate`/`decree`/`writ`/`canon`
- **One-word-neutral:** `ask`/`spec`/`plan`/`build`/`check`/`ideate`

Tool prefixes stay `school_*` for consistency with the existing surface; the **skill**
and **artifact** names carry the distinct flavor.

---

## 9. Build plan (phases)

**Phase 0 — confirm names & scope** (this step). Lock the naming theme + domain list.

**Phase 1 — core models + `clarion` interview engine**
- `models.py`, `clarion.py`, domain question-banks (all 11 domains)
- Interview modes (interview/batch/auto/import), branching, scoring
- Tests: question flow, pick-or-custom, branching, scoring, fail-open, kill switch

**Phase 2 — artifact builders**
- `blueprint.py`, `edict.py`, `weave.py`, `compass.py` (+ `render.py` to Markdown + visuals)
- Tests: each builder emits correct structure + visuals + acceptance criteria

**Phase 3 — `prism` brainstorming**
- divergent techniques, convergent scoring, clustering, visual output
- Tests: multi-technique generation, scoring, cluster, feed-to-clarion

**Phase 4 — skill pack + universal templates**
- `forge`/`triage`/`chart`/`gate`/`relay`/`scrutinize` skills (SKILL.md each, 10x content)
- domain templates + acceptance styles

**Phase 5 — surface wiring + guard + visuals**
- bridge/TS/MCP/CLI for all 6 tools; dominance + 11-layer guard; visual footers
- `node --check`, ruff, tool-surface tests

**Phase 6 — competitive duels + hardening**
- duels vs superpowers (brainstorming/writing-plans/SDD) + spec tools — School must win
- adversarial fuzz (reuse `tests/stress/fuzz_harness.py`) on every tool/feature ≥2000×
- full battery green

Each phase: TDD, Apple-grade visuals, fail-open, kill switch (`SCHOOL_FORGE=0`, etc.).

---

## 10. Success criteria
- 6 new tools across bridge/TS/MCP/CLI + 6+ named skills
- 11 domains supported (universal)
- 5 distinct named artifacts produced from one interview
- Beats superpowers in a head-to-head duel (breadth, structure, visuals, universality)
- Full test battery green; ruff clean; `node --check` valid
- Every tool ≥2000 adversarial iterations without crashing
