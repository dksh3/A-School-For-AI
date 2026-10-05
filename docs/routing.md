# Adaptive Routing

School's adaptive routing loop decides **when and how hard School's tools
should fire** for what you are doing right now — and it does the same for
non-coding work, because routing is about the situation, not the file type.

## The loop in one picture

```
you start work
    │
    ▼
school_route (assess)  ──►  severity: light | medium | high
    │                       engage:   skill | both | none
    │                       reason (micro-model, or self-rated via MCP)
    ▼
escalation table (below) decides:
    ├── light        → the school-routing skill alone
    ├── medium/high  → tools + school-routing skill together
    └── none         → nothing engages
    │
    ▼
execution evidence is appended (JSONL, per project)
    │
    ▼
school_route_stats shows counts, avg_ms, recent assess/report
entries, and the current knobs
    │
    ▼
the school-routing skill reviews stats, writes routing lessons,
and tunes .school/routing.json          ──► back to the top
```

Four pieces make the loop:

| Piece | What it does |
| --- | --- |
| `school_route` (assess) | Grades the current situation; returns severity, engage, reason, plus the **next tools and skills** the micro-model picked for this situation. |
| `school_route` (report) | Stores a routing lesson as a memory (`tags: ["routing", outcome]`). |
| `school_route_stats` | Per-tool call counts, avg_ms, recent assess/report entries, current knobs. |
| `school_dashboard` | One-glance status: route, next picks, optimizer savings, learner, diagnose. Call once per prompt. |
| `school-routing` skill | Gathers stats, reviews them visibly, tunes knobs, audits what changed. |

## Always-visible status

Two mechanisms make School show itself on **every** prompt execution:

1. **Footer** — the `experimental.text.complete` hook appends one line under
   every assistant response:

   ```
   [school] route: medium/both · next: school_recall, school_search, school-routing ·
   ctx: -1240tok (18%) · recall: 3 · learn: ok · diag: ok
   ```

   - `route` — last `school_route` decision (`severity/engage`).
   - `next` — tools/skills the micro-model picked for the situation (falls back
     to engagement defaults: `skill` → the skill; `both` → recall + search + skill).
   - `ctx` — last context-optimizer savings (`-savedtok (pct%)`).
   - `recall` — last recall hit count; `learn` — last learner result
     (`ready`/`ok`/`fail`/`off`); `diag` — bridge health.
2. **`school_dashboard` tool** — the same status as a visible tool card; its
   description tells the model to call it once per user turn. The MCP twin
   reports what the MCP process can see (evidence tail + bridge health).

Both are governed by `SCHOOL_HOOKS=0` (footer) and disappear with it; the
dashboard tool itself stays available for on-demand checks.

## Escalation table

| Severity | Engage | What runs |
| --- | --- | --- |
| `light` | `skill` | The `school-routing` skill reviews and tunes; tools stay quiet. |
| `medium` | `both` | Tools fire **and** the skill shows its work alongside them. |
| `high` | `both` | Same as medium — tool + skill together. |
| `none` | `none` | Nothing engages (only when the micro-model says so verbatim). |

Both escalation paths are visible: every routed execution carries a
` · routing: <engage>` suffix on its OpenCode title marker, so you can always
tell what the loop decided and why.

## Kill switches

| Env | Effect |
| --- | --- |
| `SCHOOL_HOOKS=0` | All execution/prompt hooks off — no recall, no markers, no injection. |
| `SCHOOL_ROUTE=0` | No micro-model assess calls; `school_route` degrades without engaging the skill. |

(The context optimizer has its own switch, `SCHOOL_CTX=0`, independent of both.)

## Knobs: `.school/routing.json`

Per-project file. Unknown keys are ignored safely (kept for reference — the
`calibration` entry uses this). Invalid values fall back to defaults per key.

| Key | Default | Range / type |
| --- | --- | --- |
| `recall_threshold` | `0.2` | 0–1 (float) |
| `hook_limit` | `3` | 1–50 |
| `hook_budget` | `400` | 64–8000 |
| `hook_timeout_ms` | `1500` | 250–5000 |
| `skip_tools` | `[]` | tool names that should NOT fire hooks |
| `force_tools` | `[]` | tool names that always fire |

Example:

```json
{
  "recall_threshold": 0.3,
  "skip_tools": ["school_status"],
  "force_tools": ["school_recall"],
  "calibration": "ask only when blocked"
}
```

## MCP fallback (no model client)

The MCP server has no session with a model, so `school_route` mode=assess
requires an explicit `severity` (`light | medium | high`) and answers with
`source: "self-rated"` — same escalation table, no micro-model round trip.
`mode=report` and `school_route_stats` behave exactly like the plugin path.

## Example flows (non-coding)

**Planning a trip** — "assess: planning a 5-day trip with two kids, need
itineraries and a budget" → medium → tools help gather, the skill audits the
plan against your preferences; lesson: "check school_route_stats before
adding another research tool."

**Studying** — "assess: reviewing organic chemistry notes before an exam" →
light → the skill alone suggests a study routing (recall threshold raised,
`force_tools: ["school_recall"]` so past notes resurface).

**Cooking** — "assess: adapting a curry recipe to what's in the fridge" →
light → skill-only: gather evidence (stats), decide, act, audit — visibly,
in four steps.

## Calibration (first use in a project)

The skill asks **one** question with exactly 4 options (three intensity
levels plus "type your own") before changing anything, and stores the answer
as `calibration` in `routing.json`.

## Lessons are data, never instructions

Routing lessons are memories. School never executes memory content as
instructions — they inform knobs and tool behavior only, and only when a
human-visible audit trail says why.
