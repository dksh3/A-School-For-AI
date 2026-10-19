---
name: gate
description: Use when work claims to be finished and needs a pass/fail verdict — before shipping, publishing, deploying, sending; especially when someone says "it's basically done". Evidence table, GO / GO-WITH-CONDITIONS / NO-GO. Any domain — not only coding. Not for finding unknown problems (scrutinize).
---

# Gate — Acceptance Gating

Work is not done when it feels done; it is done when it **passes**. `gate`
is the verification skill of the Forge suite: it runs the acceptance
contract — a `compass` (scenarios + checklist + success metrics) — against
the finished deliverable and issues a verdict a stranger could audit.

**Universal by contract.** Acceptance is not a software ceremony. Books have
gates (would a beta reader finish it?). Launches have gates (did the first
ten target customers see the offer?). Research has gates (does the evidence
support the claim at the stated confidence?). Moves, diets, curricula,
migrations — anything with a definition of done gets a gate. Works for every
agent type; the checklist is the referee, so bias gets fewer places to hide.

## When to use me

- A `chart` plan reaches a checkpoint (every 3–7 steps).
- A `forge` command or a whole deliverable claims to be finished.
- Before shipping, publishing, deploying, sending, or announcing anything.
- When someone says "it's basically done" — especially then.

## What you gate against

The `compass` artifact holds the contract. If one exists, use it. If not,
build a minimal one before judging (never gate against vibes):

1. **Scenarios** — Given/When/Then conditions that must hold. Written from
   the *user's* side: "Given a tired founder on a phone, when they land, then
   they understand the offer in 10 seconds".
2. **Checklist** — the must-haves (quality bar, style rules, always/never
   directives from the `edict`, legal/ethical floors).
3. **Success metrics** — the numbers that said this would work, with their
   thresholds ("3 of 5 readers want more", "1 reply per 5 cold emails").

## Workflow

### 1. Assemble the compass

Gather every check that the work claimed to satisfy: the `forge` checks per
command (their command logs), the `chart` plan's Constraints line, the
`blueprint`'s success metrics and constraints, the `edict`'s directives, the
acceptance scenarios, and the **review report from `scrutinize`** when one
exists (resolve it from `reports/scrutinize-<deliverable>.md`; if the
workflow required a review and none exists, that gap is itself UNVERIFIED).
Map each review finding to an evidence row by severity: **must-fix** →
hard-floor row (open must-fix ⇒ NO-GO), **should-fix** → condition row
(GO-WITH-CONDITIONS with owner and check), **note** → recorded, never
decisive. Order: hard floors first, then scenarios, then metrics.

### 2. Execute every item — with evidence

For each item, produce a row: **item | type | reading | verdict | evidence |
limitation** — the `reading` cell is hard/soft plus the interpretation you
committed to in step 3. Evidence is a command output, a quote, a number, a screenshot,
or a named witness — never "looks right". Run the checks yourself where you
can; where judgment is required (taste, clarity, ethics), use at least two
independent reads or readers (`scrutinize` for self-review; fresh eyes where
the stakes are high). Mark each row with the Evidence status vocabulary
below; `UNVERIFIED` and unaccepted `SIMULATED` count as **FAIL** for the
verdict. For non-code work the row is the claim itself — state the
limitation (sample size, proxy method, assumption) in the row rather than
manufacturing a witness. Silence is not a pass.

### 3. Verdict (apply mechanically)

Classify every row from the goal and its constraints *before* you look at
the evidence: a claim the goal promises — audience acceptance, human
sign-off, "the lead is persuaded" — is a **hard floor** unless the user
explicitly said otherwise up front (the same standard as accepting a
SIMULATED proxy). A debatable row takes the stricter reading, and the
report names the reading it took in the `reading` column. Never reclassify
a row in either direction after seeing the evidence — that is moving the
goalposts. A proxy accepted after the result was known is the same move.

- Any hard-floor FAIL (safety, legal, core promise, an `edict` "never") →
  **NO-GO**. Stop; route failures to `triage` or back to `forge`.
- All hard floors pass, some soft items fail or are unverified →
  **GO-WITH-CONDITIONS**: name each condition, its owner, its check, and its
  deadline. Conditions without owners are wishes.
- Everything passes with evidence → **GO**.

Beware averaging: ten passes do not cancel one fail. The checklist is a
conjunction, not a score.

### 4. Report

```markdown
# Gate report: <deliverable>  — VERDICT
## Evidence table
| item | type | reading | verdict | evidence | limitation |
|---|---|---|---|---|---|
| first win reachable in 60s | scenario | hard (core promise) | PASS | tester recording 0:47 | — |
| tone matches voice guide | checklist | hard (edict "never") | FAIL | pull quotes drift casual | — |
| 3/5 readers want more | metric | soft (goal metrics) | UNVERIFIED | only 2 readers so far | readers not yet run |
| "twist lands on a cold read" | claim | hard (goal promises it) | SIMULATED | 3 named-persona passes | proxy, not real readers |
## Review findings (from scrutinize)
| finding | severity | disposition |
|---|---|---|
| <finding> | must-fix / should-fix / note | fixed / condition (owner, check) / recorded |
## Blockers (must fix)
## Conditions (fix before <date>, owner, check)
## Next actions
```

Ship the report as `reports/gate-<deliverable>.md` (create `reports/` on
first write; follow an existing repo report location if one exists). A gate
that produces no report will be re-litigated later.

## Evidence status

- `PASS` — the check ran, its evidence is recorded, the declared condition holds.
- `FAIL` — the check ran and failed, or a mandatory condition is unmet.
- `UNVERIFIED` — not performed, evidence missing, or unestablishable. Counts as FAIL for any done claim.
- `SIMULATED` — proxy assessment instead of real-world validation: record method, rubric, assumptions, limitations; use ≥3 named, meaningfully distinct personas; never present as human feedback. Counts as UNVERIFIED unless the user explicitly accepted the proxy for the stated purpose, recorded before the verdict.
- `EXPLORATORY` — investigation, hypothesis, or provisional assessment. Never presented as done.

## Worked examples

**Code**: gate = the full test suite, the repro checks from `triage`, the
`edict`'s "never edit generated files" directive, and the release metric
(p95 latency). FAIL on the latency metric → NO-GO even though all tests are
green.

**Writing**: gate = three readers can state the thesis unprompted (scenario),
no unresolved style-guide violations (checklist), and 2 of 3 finish the
piece (metric). 1 of 3 finished → NO-GO; the thesis passes do not save it.

**Business**: gate = offer visible in 10 seconds, 5 target conversations
held, 1 paid pilot signed. 4 conversations and 0 pilots → NO-GO, with the
diagnosis routed to `triage` (is it the offer or the channel?).

## Gates on the gate itself

- Every verdict row carries evidence. No evidence, no PASS.
- UNVERIFIED is stated out loud and treated as FAIL for the verdict.
- Every row was classified from the goal before its evidence; no row was
  reclassified in either direction to reach the verdict.
- Every `scrutinize` review finding is accounted for: open must-fix ⇒ NO-GO.
- The compass was written (or reviewed) *before* the work was judged — you
  cannot move the goalposts after the kick.
- The report is durable: someone who missed the whole project can audit the
  verdict from it alone.

## Never

- Never issue GO on "mostly" — "mostly" is GO-WITH-CONDITIONS at best.
- Never let a strong average drown a hard-floor failure.
- Never grade your own work with no independent evidence for judgment items.
- Never treat simulated feedback as human feedback, or three simulated
  reviews as three readers.
- Never delete or soften a failing item to reach GO. The compass is the
  contract; the work serves it, not the reverse.

## Suite map — artifacts → School tools

`clarion` (interview) → `school_clarion` · `blueprint` (spec) → `school_blueprint` · `edict` (commands) → `school_edict`
`weave` (formation) → `school_weave` · `compass` (acceptance) → `school_compass` · `brainstorm` (ideas) → `school_brainstorm`
CLI: `school <artifact>` — e.g. `school edict`, `school brainstorm` (legacy alias: `school prism`).
Bridge wire names: `clarion`, `blueprint`, `edict`, `weave`, `compass`, `prism` (`prism` = brainstorm, legacy wire name kept for compatibility).
