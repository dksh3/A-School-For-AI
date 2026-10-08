# School Context Engine — Master Design (Context Economy + Universal Agents)

Date: 2026-10-06
Status: approved through design sections 1–6; awaiting written-spec review
Program structure (user decision, verbatim): "do the 3rd, 2nd, and 1st combined" —
ONE master spec (this document) + parallel read-only research track + sequential
sub-project implementation (S1→S6), each sub-project with its own implementation plan
derived from this spec.

## 1. Vision

School becomes the unified **context & token economy platform** for AI agents:

- **Context**: skeletonize tool results, compress conversation history with
  deterministic-first layering, restore anything that was compressed — all fail-open.
- **Economy**: disjoint token accounting, real pricing, dashboards, budget-aware routing.
- **Every School feature** (memory, retrieval, confidence, lifecycle, routing, skillgen)
  gets a build-vs-borrow audit against the best open source — combined, not reinvented.
- **General-purpose agents first-class**: coding, writing, research, planning, support —
  not repo-specific.
- **Presentation standard (user requirement, standing constraint)**: every visible
  surface — footer chips, CLI, MCP text, dashboards — must "genuinely look like Apple
  made it": calm hierarchy, refined typography, no clutter, quiet confidence. Never
  plain output. This applies to every sub-project.

Always branded **School** (never Teacher).

## 2. Decisions locked in design Q&A

| # | Decision |
|---|----------|
| D1 | Scope = B+A: full context & token economy platform **and** per-feature OSS merge for every existing School subsystem. |
| D2 | Build-vs-borrow = hybrid: drop-in OSS libraries where commodity and license-clean; adopted *ideas* (clean-room) where our architecture is the differentiator; verdict recorded per subsystem. |
| D3 | DCP is **folded into School**: School gains first-class conversation compression; third-party `@tarquinen/opencode-dcp` becomes optional/removable; if present, School complements it and offers a quiet switch prompt — never tampers with it. |
| D4 | Surfaces = everything: OpenCode plugin, MCP mirror, embeddable core + CLI, adapter contract for hook-exposing runtimes. |
| D5 | Compression engine = layered hybrid ("all"): free deterministic pre-pass always, budgeted micro-model pass, deterministic emergency truncate; configurable intensity (off/low/high). |
| D6 | Trigger = **auto-on-threshold** (context budget crossing, default 80%), plus explicit tools/CLI. |
| D7 | DCP is AGPL → **ideas only, clean-room implementation**; never copied code. |

## 3. Architecture overview

```
Agent runtime (OpenCode | MCP client | embeddable loop | adapters)
        │  on_tool_result / apply_view / emit_chip  (adapter contract)
        ▼
School Context Platform (core, runtime-agnostic)
  ├─ Skeletonizer      tree-sitter AST → structural skeleton (fail-open)   [EXISTS]
  ├─ Compression       Layer 0 → 1 → 2 ladder, circuit breaker            [NEW]
  ├─ Block Store       verbatim history + summaries, restore/decompress   [NEW]
  ├─ View Builder      prompt-side copy; originals never mutated          [NEW]
  ├─ Token Ledger      disjoint buckets, pricing, JSONL + aggregates      [NEW]
  ├─ Budget Router     spend/pressure → school_route input                [NEW]
  └─ Registry/Confidence/Lifecycle/Routing/SkillGen                       [EXISTS]
```

## 4. Section 1 — Compression engine (APPROVED)

**Keep as School's own** (differentiators): tree-sitter skeletonization with
hybrid parse and fail-open raw fallback; deterministic pre-pass; integration with
registry/lifecycle/ModelCallBudget; existing storage discipline.

**Adopt clean-room from OSS** (ideas, not code):

| Source | Idea adopted |
|---|---|
| contextkit | 3-tier ladder + circuit breaker (ok/warning/error/critical; 3 consecutive model failures → stay on free layers), state surfaced in status |
| omnigent | layering least→most lossy; **original history never mutated — only a prompt-side view** |
| hermes ContextCompressor | iterative summary updates (no unbounded summary-of-summary chains); head/tail protection (~last 20k tokens verbatim); secret redaction `[REDACTED]` before model calls; failure cooldown; "Remaining Work" framing |
| deepagents | offloaded history restorable from file |
| pydantic-ai | never split tool_call/result pairs; trigger by messages/tokens/fraction; guided focus topic |
| DCP (AGPL, ideas only) | nested summaries on overlap (depth cap 2, then flatten); dedup + purge-errors strategies; protected tools; decompress by id; budget-pressure nudges |
| context-pipe | policy object with `trigger_at` (default 0.8) |

**Layer ladder:**

- **Layer 0 — deterministic (free, always):** dedupe repeated errors, strip already
  skeletonized outputs, collapse boilerplate/whitespace, purge stale errors (configurable).
- **Layer 1 — budgeted micro-model:** subprocess judge (existing school_route /
  SubprocessModelJudge pattern) under `ModelCallBudget` (env-tunable per-task cap);
  produces/upates summaries; redacted input; on failure/cooldown → fall through.
- **Layer 2 — deterministic emergency truncate:** rare, logged, circuit-breaker-driven;
  oldest-first with protected tail retained.

Fail-open at every step: any layer failure degrades to the next free layer or to
originals — a session never crashes or blocks on compression.
Kill switches: `SCHOOL_COMPRESS=0` (compression), `SCHOOL_CTX=0` (skeletonization),
`SCHOOL_HOOKS=0` (footer) — consistent with existing patterns.

## 5. Section 2 — Block store & restore (APPROVED)

- **File**: `<school-context-dir>/<session-id>.blocks.json` — sibling of memory dir,
  resolved via existing School config; atomic write (tmp + `os.replace`), file-locked;
  bounded (default 200 blocks / 5 MB per session, oldest-restored-last eviction);
  restart-recoverable.
- **Block schema**: `id` (stable `bN`), `range`, `messages` (verbatim originals —
  source of truth, never mutated), `summary`, `parent_id`/`summary_of` (nesting ≤ depth 2),
  `layer`, `tokens_original`, `tokens_summary`, `created_at`, `restores`.
- **Never-mutate rule**: compression builds a **view** (prompt-side copy where block
  ranges are replaced by summaries). View-build failure → feed originals.
- **Restore**: by id or expand-last; file-backed (works after restart); idempotent;
  counted for observability; never triggers re-compression by itself.
- **Iterative re-compression**: on next threshold crossing, summaries are updated in
  place (tail folded in); nesting only for genuinely overlapping ranges.
- **Safety rails**: redaction before model calls; tool_call/result pair atomicity;
  protected tail; circuit breaker; cooldown. No tokens/secrets ever cached.
- **Persistence contract** (sub-project exit criterion): kill the process mid-cycle,
  restart, restore any block — exact originals.

## 6. Section 3 — Surfaces & DCP coexistence (APPROVED)

**Adapter contract** (all surfaces implement the same three methods):

```
on_tool_result(payload)   # skeletonization entry
apply_view(view)          # what the model sees
emit_chip(status)         # Apple-grade footer/status line
```

1. **OpenCode plugin (primary)** — skeletonization already lives in
   `tool.execute.after`. Conversation compression needs an apply-view mechanism;
   **exact opencode capability = just-in-time research spike before S2 planning**
   (DCP proves something is possible; mechanism to be verified, not assumed).
   Fallback if none exists: tool-driven compress/restore + nudges (degraded but
   functional). Footer chip on every response.
2. **MCP mirror (thin)** — three tools max: `school_context_status` (read-only),
   `school_context_compress` (explicit), `school_context_restore` (idempotent).
   Existing `school_read`/`school_grep` unchanged. Parity rules (TS byte-equal
   descriptions, read-only annotations) apply as with existing tools.
3. **Embeddable core** — importable package; `school context compress|restore|status`
   CLI for non-Python runtimes via subprocess JSON.
4. **Adapters** — contract designed now; Claude Code / Codex / LangGraph built in S4.

**DCP coexistence**: detect `@tarquinen/opencode-dcp` at plugin load.
Absent → School owns compression. Present → School keeps skeletonization/economy/chips;
message-level compression stays with DCP until the user chooses; one quiet, dismissible,
Apple-grade offer: *"School can now handle compression — with restore, budgets, and
status. Keep DCP, or switch?"* Clean break on switch (no state import). Never disable,
patch, or tamper with the third-party plugin.

**Chip voice (Apple-grade)**: one calm monospace line, e.g.
`[school] ctx 62% · −18.4k tok · $0.07` / `[school] compacted 2 blocks · restorable`.
Same voice across footer, CLI, MCP.

## 7. Section 4 — Token economy (APPROVED)

- **Disjoint buckets**: `uncached_input`, `cache_read`, `cache_write`, `output`,
  `reasoning` — cached tokens never double-counted. Per-record quality flag:
  `actual | estimated | unknown`; missing data recorded `unknown`, **never 0**.
- **Pricing**: Decimal math; editable `prices.json` (version-stamped defaults,
  env-overridable); per-bucket rates; unknown price → cost `—`, tokens still counted.
- **Storage**: append-only JSONL per session (atomic appends, bounded retention) +
  rolled-up daily/session aggregates. No SQLite (zero-dep embeddable core).
- **Sources**: plugin reads runtime `usage` when exposed (JIT research: exact opencode
  metadata); else chars/4 estimator flagged `estimated`; embeddable core accepts
  host-supplied usage.
- **Dashboards**: footer chip; `school status` / `school_skill_status` gain a compact
  tokens block (extend, no new tool); CLI `school tokens report --session|--today`
  (buckets, cost, top-5 consumers, compression savings); MCP reuses `school_status`.
- **Budget-integrated routing (TBO idea)**: thresholds (warn/act, env-tunable) feed
  `school_route` as a `budget` input — under pressure, recommendations bias to cheaper
  models/lighter skills. Accounting never blocks the agent (fails open); only routing
  suggestions react.

## 8. Section 5 — General-agent embedding (S4, APPROVED)

- Platform is runtime-agnostic Python (zero hard deps, `core/skillgen` style);
  host wires the three adapter methods (~10 lines for a custom loop).
- Framework adapters (JIT API research in S4): LangGraph middleware, generic Python
  context manager, Claude Code hooks, Codex if usable; OpenAI-style SDK only if
  research justifies it (YAGNI otherwise).
- Phase 1–2 features travel free via existing MCP tools; embedding docs show the wiring.
- Domain-neutral wording config for non-coding contexts.
- Deliverable: adapter package + docs + one worked example per adapter.
  **No new features in S4 — integration only.**

## 9. Section 6 — Per-feature audit & merge (S5, APPROVED)

- Research track audits one subsystem at a time (memory → retrieval →
  confidence/lifecycle → routing → skillgen) against best-in-class OSS.
- **Verdict per component, recorded in this spec's appendix**:
  `KEEP` / `ADOPT` (permissive dep vendored) / `IDEAS-ONLY` (copyleft, clean-room) /
  `MERGE` (their mechanism inside our architecture) / `REPLACE`.
- Hard rules: license check on every adopt (permissive only for vendoring);
  no churn that breaks the existing green test suite; backward compat for all
  `school_*` surfaces; each accepted merge becomes its own sub-plan.
- Research lands as a spec amendment **before** the matching sub-project starts.

## 10. Program: sub-projects & exit criteria

| # | Sub-project | Scope | Exit criteria |
|---|---|---|---|
| S1 | Context Engine Core | Layers 0–2, block store, view builder, restore, circuit breaker, skeletonization integration | persistence/restart/restore tests; fail-open suite; battery green; chips rendered |
| S2 | Surfaces & DCP coexistence | plugin apply-view (post-spike), MCP 3 tools, `school context` CLI, DCP detection/offer, chips with ctx/compaction fields | all surfaces live; parity tests; DCP-present and absent modes tested |
| S3 | Token economy wiring | ledger sources, pricing, token/cost fields on chips, dashboards, budget→routing | `school tokens report`; budget field in route; unknown-not-zero tests |
| S4 | Embedding & adapters | embeddable package polish, framework adapters, docs + examples | one worked example per adapter passes its own tests |
| S5 | Per-feature audit & merge | subsystem-by-subsystem verdicts + accepted merges | appendix complete; each merge planned & green |
| S6 | Progress & live telemetry UX | animated progress bars, interactive TUI surfaces, bar graphs of context/token usage, cumulative stats (tokens saved, contexts saved/restored), context tool always-working guarantee (fail-open + watchdog + parity tests) | bars/graphs render under mocked clock; stats reconcile with block store; context tool passes always-working suite (error, timeout, corrupt-store paths) |

Testing follows existing conventions: mocked deterministic tests (models mocked,
no live network), full battery run each sub-project, ruff clean (plugin_source.py
stays at baseline E501 count), `node --check` for TS.

## 11. Constraints (standing)

- Fail-open everywhere; budgets on every model call; kill switches for every new
  automatic behavior; no secrets in cache/log/provenance/telemetry.
- Apple-grade presentation on every surface (D-brand constraint).
- Backward compat: existing 7 Phase-1 skill tools, 5 Phase-2 GitHub tools, memory,
  routing, footer, MCP parity — all stay green.
- No commits unless the user explicitly asks. Do not touch `.superpowers/`,
  `.opencode/goals/`, or unrelated working-tree changes.
- Phase 3 marketplace and Phase 4 web acquisition remain out of scope entirely.

## 12. Just-in-time research items (scoped, not open design questions)

1. opencode mechanism for applying a compressed view to model context (S2 spike).
2. opencode per-message `usage` metadata shape (S3 source wiring).
3. Claude Code / Codex / LangGraph hook APIs (S4).
4. Per-subsystem OSS shortlists for S5 (research track; memory shortlist already begun).

## 13. Research appendix (seed)

- Memory: Mem0 (57k★, Apache, two-phase extraction) / Zep+Graphiti (bi-temporal graph) /
  Letta (platform, not lib) / LangMem (LangGraph-native); benchmark note: verbatim
  storage beats per-turn extraction on ingest; no system >58% recall.
- Compression landscape: see §4 table (contextkit, omnigent, hermes, deepagents,
  pydantic-ai, DCP, context-pipe).
- Economy: token-ledger (disjoint buckets), tokonomics (Decimal pricing), tokmon
  (dashboards), TBO (budget routing).
- S5 verdicts will be appended here as research completes.
