---
name: triage
description: Use when something is broken, regressed, or keeps failing and the cause is unknown — "X is broken", "it worked yesterday", "the fix didn't hold". Reproduce, bisect one factor, fix the cause, verify. Any domain — not only coding. Skip triage when nothing is failing (forge) or the problem is taste (scrutinize).
---

# Triage — Root-Cause Debugging

Something is broken and you do not know why. `triage` is the diagnosis skill
of the Forge suite: it turns "it doesn't work" into a proven cause and a
verified fix. Named for the hospital discipline: stabilize first, find the
wound, treat the wound — not the alarm beeping about it.

**Universal by contract.** The thing that is "broken" is any outcome that
fails its check — a failing test, a confusing chapter, a launch with zero
replies, a churn spike, a flaky process, a habit that keeps collapsing on
Tuesdays. The method is the same because the logic is the same: make the
failure repeatable, vary one factor at a time, and believe evidence over
narrative. Works for every agent type — LLM, human, or hybrid.

## When to use me

- A `forge` check is red and the reason is not obvious.
- A user reports "X is broken/wrong/bad" without a diagnosis.
- Something used to work and stopped — a regression with a time boundary.
- The same failure keeps coming back (that is a symptom being treated).

If nothing is failing, you want `forge` (build) or `scrutinize` (review).

## The loop

### 1. Reproduce — make the failure repeatable

A failure you cannot reproduce is a rumor. Before touching anything:

- Write the **repro**: the exact steps, inputs, and conditions that produce
  the failure, and the exact observed vs expected outcome.
- Turn the repro into a `forge` check: it fails now (RED, for the right
  reason) and will pass when the cause is fixed. This is your fixed target —
  everything after this is judged against it.
- If it will not reproduce, hunt *conditions* first (timing, environment,
  data shape, who is doing it, how tired they are). Intermittency is data:
  record every occurrence with its conditions and look for the pattern.

Record the repro in this shape (ship it as `reports/triage-<failure>.md`,
`reports/` created on first write):

```markdown
## Repro: <failure>
Steps: <exact steps, inputs, conditions>
Observed: <what happens>
Expected: <what should happen>
Forge-check (RED): <the repro as a check — fails now, for the right reason>
Isolation: <one factor varied> → boundary: <where behavior flips>
Cause: <mechanism, not a story>
Predicts (2nd): <independent consequence> — seen: <yes/no + evidence>
Fix: <smallest change to the mechanism>
Regression check: <so it cannot return silently>
```

### 2. Isolate — shrink the space of suspects

Vary **one factor at a time** and observe. Never change two things between
runs — a fix that "works" after two changes is a coin flip wearing a lab coat.

- **Bisect the timeline**: what changed between the last good state and the
  first bad one? Halve the interval until the boundary is one change.
- **Bisect the surface**: does the failure follow the input, the
  environment, the person, or the hour? Move the failing case to a working
  context and the working case to the failing context; the failure follows
  its true cause.
- **Find the boundary**, not just an example: the exact value/length/timing/
  audience where behavior flips. The boundary tells you *why*.

### 3. Fix the cause — the five-whys discipline

Ask "why" until the answer is a mechanism, not a story. Then check the
mechanism predicts the evidence (if your cause were true, what else would we
see? see it). Fix the mechanism. Symptom patches are loans against future
triage sessions — if you take one deliberately, append the cause to the
`blueprint`'s `risks` (the model's debt list) as open risk, with its trigger
and its interest.

**Treatments are `forge` commands**: each fix is executed RED → GREEN →
REFACTOR against the repro check.

### 4. Verify — prove it and prove nothing else broke

- The repro check now passes. ✗ → ✅
- The failure's *conditions* also pass (same input shape, same environment,
  same timing class) — not just your happy-path variant.
- Regression suite around the area passes; if the bug lived there a while,
  add a check so it cannot return silently.
- For flaky failures, one pass proves nothing: run the repro N ≥ 10 times
  (or over the period it used to fail in) before claiming victory.

Close the loop: run the `gate` checklist on the whole deliverable, then write
the lesson down via `school_remember` (what the boundary was, what the
mechanism was — tags `["triage", <area>]`, only when it is durable enough to
change future work) so the next agent starts at step 2 instead of step 1.

## Worked examples

**Code regression** — "the export broke". Repro: the failing test with the
customer's exact file. Bisect: last release passes, this one fails; within
the release, the CSV change is the boundary — the failure follows files with
quoted commas. Cause: the parser changed quote handling. Fix with `forge`
against the repro; regression check for quoted commas added.

**Writing** — "chapter 7 is boring, readers drop". Repro: three readers stop
at the same page and cannot say what the chapter is *about*. Isolate: the
drop follows the subplot detour, not the character (swap scenes: attention
follows the detour). Cause: the chapter has no question on its first page.
Fix: open on the question, re-test with fresh readers at the same page.

**Business** — "signups converted, now they churn in week one". Repro: the
week-one cohort funnel. Isolate: churn follows the source (paid traffic),
not the plan price (price change didn't move it); boundary is onboarding
step 3, where the value moment used to be. Cause: the redesign moved the
first win past the free-trial end. Fix: restore a first win inside day one;
verify cohort week-one retention recovers over two cohorts.

## Gates

- No fix is proposed before the repro exists and is checkable.
- No two variables change between observations.
- No "verified" claim on a flaky failure from a single pass — say "needs N
  runs" and run them.
- The fix must predict a *second*, independently observed consequence of the
  cause; if it cannot, you have a coincidence, not a cause.

## Never

- Never fix by reverting things at random until it goes quiet — that is
  cargo-cult healing and it will return.
- Never patch the symptom while calling it done; if you must ship a symptom
  patch, append the cause to the `blueprint`'s `risks` as open risk.
- Never accept "it works now" with no mechanism. Future you will pay.
- Never blame a person before you have isolated a condition. Systems, not
  villains.

## Suite map — artifacts → School tools

`clarion` (interview) → `school_clarion` · `blueprint` (spec) → `school_blueprint` · `edict` (commands) → `school_edict`
`weave` (formation) → `school_weave` · `compass` (acceptance) → `school_compass` · `brainstorm` (ideas) → `school_brainstorm`
CLI: `school <artifact>` — e.g. `school edict`, `school brainstorm` (legacy alias: `school prism`).
Bridge wire names: `clarion`, `blueprint`, `edict`, `weave`, `compass`, `prism` (`prism` = brainstorm, legacy wire name kept for compatibility).
