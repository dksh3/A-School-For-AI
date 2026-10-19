---
name: chart
description: Use when a goal is bigger than one sitting and needs an executable plan — "what's the plan?", "how long will this take?", or a blueprint ready to execute. Bite-sized steps, each with a check, dependencies, lanes, critical path. Any domain — not only coding. Not for exploration (brainstorm first) or execution itself (forge).
---

# Chart — The Implementation Plan

A goal without a plan is a wish with a deadline. `chart` is the planning
skill of the Forge suite: it turns intent (a `blueprint`, an interview from
`clarion`, or a raw goal) into a **map of bite-sized, verifiable steps** with
explicit order, ownership, and a definition of done for every step.

**Universal by contract.** Plans are not a coding artifact. A novel has a
plan (chapters, drafts, beta reads). A business launch has a plan (offer,
channel, first ten customers). A move to a new city has a plan. The
discipline is identical: shrink the steps until each one is verifiable in a
single sitting, then order them by what unblocks what. Works for every agent
type and every domain — coding is just one of eleven.

## When to use me

- You have a `blueprint` (or any goal statement) and it is time to execute.
- The work is bigger than one sitting and you keep re-deciding what to do
  next.
- Someone asks "how long will this take / what's the plan?" and you want to
  answer with a chart, not a vibe.
- Parallel workers are available and you need lanes for `relay`.

Not for: open-ended exploration (`brainstorm` first), execution itself (`forge`),
or final judgment (`gate`).

## Workflow

### 1. Fix the destination first

A chart needs a "you are here" and a "you are there". From the `blueprint`
(or by asking — ONE round, then decide):

- **Goal**: the end state, stated as an observable condition ("beta readers
  finish chapter 9 and ask for more", "first 10 paying customers", "the
  migration runs with zero data loss").
- **Non-goals**: what you are explicitly not doing. Plans rot fastest at
  their edges.
- **Constraints**: time, money, skills, deadlines, user requirements, hard
  rules, prohibited actions, required outputs, assumptions, and the
  always/never directives from any `edict`. Constraints travel the whole
  chain — `chart` → `forge` → `gate` — so give each one a line here; the
  plan's template has a slot for them and `gate` checks them at the end.

### 2. Cut the work into bite-sized steps

Split until every step passes the **one-sitting test** — a competent worker
(possibly future you) can finish and verify it in roughly 25 minutes to 2
hours. Rules for each step:

- **Verb-first title**: "Draft chapter 3 opening", "Interview 5 churning
  customers", "Write the migration script". "Improve onboarding" is a fog.
- **Own check**: every step names the `forge` check that proves it done — a
  test, a threshold, a sign-off, a reconciliation. A step without a check is
  not a step; it is a hope. Split it again or delete it.
- **Deliverable**: what exists after the step that did not exist before.
- **Estimate**: minutes, honestly. Wrong estimates are data for next time.

If a step cannot be verified, it is too big or it is actually research —
route it to `brainstorm`/`triage` and chart its output instead.

### 3. Order: dependencies, phases, lanes

Shape the steps with `weave` formations:

- **Phases** when order is real (you cannot edit before you draft).
- **Lanes** when work is parallel (`relay` will run them; give each lane a
  clear boundary so merges are trivial).
- **Critical path** when there is a deadline: mark the chain where any delay
  is the whole-project delay, and put your best attention there.
- **Dependencies** as explicit `step B needs step A` links, never "probably
  fine in parallel". In the plan this is `needs: S1`; it is the same link
  `school_weave` renders from `Command.depends_on: ["S1"]` — one vocabulary
  end to end, so hand the steps to `school_weave` for phases, lanes, and the
  critical path instead of re-deriving formations by hand.

### 4. Name the checkpoints

Insert **gate checkpoints** every 3–7 steps: moments where `gate` runs and
the plan can change course (cut scope, add a lane, kill a phase). A plan with
no checkpoints is a commitment to drift.

### 5. Review the chart before executing

- Can a stranger execute step 1 without asking you anything?
- Does every path from here to the goal pass through at least one check per
  step?
- Is the critical path shorter than the deadline with honest estimates?
- What is the smallest version that still counts as done? (Name it. It is
  your fallback.)

## Output format

Ship the chart as `reports/chart-<goal>.md` (create `reports/` on first
write; follow an existing repo report location if one exists).

```markdown
# Chart: <goal>
Destination: <observable end state>    Non-goals: <...>
Constraints: <hard rules, prohibited actions, required outputs, assumptions, always/never from any edict>
## Phase 1 — <name>  (exit check: <...>)
- [ ] S1 <verb-first title> (~45m) → delivers <...>; check: <...>
- [ ] S2 <title> (~30m) → delivers <...>; check: <...>; needs: S1   (= Command.depends_on)
## Lanes (parallel, run via relay)
- Lane A (owns S3–S4): <boundary>
- Lane B (owns S5–S6): <boundary>
## Critical path: S1 → S4 → S7 → gate
## Checkpoints: after S4 (gate), after S7 (gate + scope decision)
## Smallest-done fallback: <...>
```

## Worked example (writing domain)

Goal: "publish the nonfiction proposal". Non-goals: the full manuscript.
Steps: S1 research comp titles (check: 5 comps with numbers, 1h) → S2
one-page overview (check: an agent can restate the hook from it, 45m) → S3
chapter summaries (check: each summary is one paragraph and reveals an
argument, 2h) → S4 sample chapter draft (check: `forge` reader test — 3
readers want to know what happens next) → gate → S5 polish + submit.
Critical path: S3 → S4. Smallest-done: S1–S3 + existing sample.

## Gates for a good chart

- Every step has a check and a deliverable. (Run this as a literal scan.)
- No step exceeds one sitting; the chart contains no "and then the hard
  part" step.
- Dependencies are explicit and acyclic.
- The critical path fits the deadline with honest estimates; if it does
  not, cut scope in the open — never by silently shrinking checks.

## Never

- Never plan past your resolution: detail only the next phase; sketch the
  rest and re-chart at the checkpoint. Plans are living documents.
- Never write a step whose done-state is a feeling. If you cannot check it,
  you cannot finish it.
- Never batch two verifiable outcomes into one step to make the chart look
  shorter. The check will find out.
- Never treat estimates as promises; treat them as the cheapest experiment
  you can run against reality.

## Suite map — artifacts → School tools

`clarion` (interview) → `school_clarion` · `blueprint` (spec) → `school_blueprint` · `edict` (commands) → `school_edict`
`weave` (formation) → `school_weave` · `compass` (acceptance) → `school_compass` · `brainstorm` (ideas) → `school_brainstorm`
CLI: `school <artifact>` — e.g. `school edict`, `school brainstorm` (legacy alias: `school prism`).
Bridge wire names: `clarion`, `blueprint`, `edict`, `weave`, `compass`, `prism` (`prism` = brainstorm, legacy wire name kept for compatibility).
