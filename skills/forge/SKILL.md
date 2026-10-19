---
name: forge
description: Use when executing a task that needs provable done — write the check first and watch it fail (RED), smallest change that passes (GREEN), improve and re-verify (REFACTOR). Any verifiable check: test, checklist, threshold, reader check. Any domain — not only coding. Not for exploration (see brainstorm) or unverifiable judgment (scrutinize).
---

# Forge — Test-Driven Execution

Execute work the way a smith forges metal: heat, strike, check, repeat —
never ship anything you have not proven. `forge` is the execution skill of
the Forge suite: it takes a **command** (a step from an `edict`, a task from
a `blueprint`, or a raw request) and drives it RED → GREEN → REFACTOR.

**Universal by contract.** This is not a coding skill with metaphors bolted
on. A "test" here is *any verifiable check* — a unit test, a checklist item,
a metric threshold, a taste test, a reconciliation, a question a reader must
be able to answer. If a claim can be checked before it is trusted, it can be
forged. Works for LLM agents, humans, and hybrids; works for coding, writing,
research, business, planning, education, creative work, ops, data, and life.

## When to use me

- You have a command to execute — one step of an `edict`, one task from a
  `chart` plan, or a direct request — and "done" must be provable.
- Someone asks you to "just do X" and you refuse to guess what done means.
- You are tempted to write the deliverable first and find the check later
  (stop: that is grading your own homework).

Do **not** use me for pure exploration (use `brainstorm` first) or
for pure judgment calls with no verifiable outcome (use `scrutinize`).

## The loop

Run this loop **per command**. Show all three states visibly.

### 1. RED — write the check first

Before producing anything, state the verifiable outcome as a check that a
stranger could run. The check must be:

- **Binary** — pass or fail, not "looks good".
- **Cheap** — runnable in seconds, or it will be skipped.
- **Honest** — it fails right now, for the *right reason* (the work is
  undone), not because the check is broken.

> RED gate: demonstrate the check failing before you start. A check you
> cannot show failing is not a check — it is a wish.

Domain examples of a "test":

| Domain | A verifiable check looks like |
|---|---|
| coding | `pytest tests/x.py` passes; the bug repro no longer reproduces |
| writing | three beta readers correctly summarize the chapter's twist |
| research | the preregistered analysis reproduces the headline number |
| business | five cold emails out, one reply booked within 48h |
| education | the student solves an unseen variant unassisted |
| ops | the runbook drill completes inside the on-call time budget |
| life | the habit log shows seven consecutive days |

When a check needs humans you cannot reach in this session (beta readers,
customers, students), do not fake it and do not stall: run a named-persona
proxy (≥3 meaningfully distinct personas), record the claim as `SIMULATED`
with method, rubric, assumptions, and limitations — or escalate to the human.
A simulated reader is never a real reader.

### 2. GREEN — smallest change that passes

Make the minimal change that turns the check green. Rules:

- Optimize for *passing the check*, not for impressing anyone.
- If you think of an improvement mid-GREEN, write it down for REFACTOR —
  do not smuggle it in now.
- If the check cannot be made green in one sitting, split the command (go
  back to `chart` and cut it smaller) instead of half-passing.

### 3. REFACTOR — improve with the check green

Now improve: structure, clarity, tone, efficiency, naming. Re-run the check
after every change. Refactoring without re-running is just breaking things
quietly.

### 4. Record and continue

Fill the command log for the command — then honor the `edict`'s always/never
directives and move to the next command. Batch nothing. If the work came from
`weave`, respect its lanes and dependencies (`needs:` = `Command.depends_on`) —
do not start a command whose prerequisites are unproven.

```markdown
## Command: <title>
Check (RED): <the check, stated so it can fail>
Shown failing: <actual failing evidence — command + output, or a quote>
Change (GREEN): <smallest change>
Evidence: <passing evidence — the same check re-run>
Re-verify: <what must be re-checked after this change>
```

Where it lives: ship each command log in `reports/forge-<deliverable>.md`
(create `reports/` on first write; follow an existing repo report location if
one exists). A lesson that should outlive the report — one that changes how
future work is done — goes to memory via `school_remember`. Reports are
working artifacts; memories are durable lessons.

## Adaptation table

| If your work is... | Then the check is... | And REFACTOR means... |
|---|---|---|
| code | tests, repro scripts, type checks | simplify, name well, delete dead paths |
| prose | reader comprehension, rubric, style guide | tighten voice, cut filler, fix rhythm |
| a plan | every step has an owner and a done-state | merge steps, expose the critical path |
| a decision | the stated evidence would survive a hostile review | sharpen criteria, name the reversals |
| a habit | a log entry exists for the period | reduce friction, protect the trigger |

## Evidence status

- `PASS` — the check ran, its evidence is recorded, the declared condition holds.
- `FAIL` — the check ran and failed, or a mandatory condition is unmet.
- `UNVERIFIED` — not performed, evidence missing, or unestablishable. Counts as FAIL for any done claim.
- `SIMULATED` — proxy assessment instead of real-world validation: record method, rubric, assumptions, limitations; use ≥3 named, meaningfully distinct personas; never present as human feedback. Counts as UNVERIFIED unless the user explicitly accepted the proxy for the stated purpose, recorded before the verdict.
- `EXPLORATORY` — investigation, hypothesis, or provisional assessment. Never presented as done.

## Gates (non-negotiable)

- No command is "done" with a red or missing check. No exceptions for size.
- The check is written **before** the change. Retrofitted checks only prove
  you can predict the past.
- Evidence accompanies every done-mark — a number, an output, or a quote,
  never just "completed".
- If reality refuses to be checkable, say so explicitly and downgrade the
  claim to "exploratory" — do not dress a guess as a pass.

## Worked example (writing domain)

Command: "Draft the launch essay's opening, which must make a busy founder
read past paragraph two."

1. **RED** — check: hand the first 150 words to two founders; ask each "what
   is this essay promising, and do you want more?" Both must want more. Run
   it on the current empty state → obviously fails (nothing to read). ✗
2. **GREEN** — draft the smallest opening that could pass: one promise, one
   tension, one reason to continue. Test again. Adjust until both say yes.
3. **REFACTOR** — cut 20% of the words without losing the promise. Re-test
   with one fresh reader (fresh eyes catch regression).

## Never

- Never mark a command done because it "should work".
- Never write the check after the change and call it verification.
- Never weaken the check to make it pass — fix the work or split the
  command.
- Never let "tests" mean "code" in your head. If it can be checked, it can
  be forged.

## Suite map — artifacts → School tools

`clarion` (interview) → `school_clarion` · `blueprint` (spec) → `school_blueprint` · `edict` (commands) → `school_edict`
`weave` (formation) → `school_weave` · `compass` (acceptance) → `school_compass` · `brainstorm` (ideas) → `school_brainstorm`
CLI: `school <artifact>` — e.g. `school edict`, `school brainstorm` (legacy alias: `school prism`).
Bridge wire names: `clarion`, `blueprint`, `edict`, `weave`, `compass`, `prism` (`prism` = brainstorm, legacy wire name kept for compatibility).
