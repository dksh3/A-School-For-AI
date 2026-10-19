---
name: scrutinize
description: Use when the work is finished and needs adversarial self-review before anyone else sees it — especially before a gate run. Red-flag checklist, two hostile read-throughs, prioritized fix list. Catches unknown problems in code, prose, plans, decisions — not only coding. Not a substitute for gate (verdict) or triage (root cause).
---

# Scrutinize — Adversarial Self-Review

You are the first reviewer of everything you make — and the cheapest hour of
review is the one before anyone else spends theirs. `scrutinize` is the
quality-review skill of the Forge suite: it attacks your own deliverable
before reality does, with a red-flag checklist, hostile read-throughs, and a
verdict with a prioritized fix list.

**Universal by contract.** Review is not a code-review ritual. A chapter gets
scrutinized (where does a reader get confused? what claim is unsupported?).
A launch plan gets scrutinized (where is the wishful step? which metric is
vanity?). A research conclusion gets scrutinized (where does the evidence
stop and the story begin?). Works for every agent type — if you made it, you
can turn around and attack it.

## When to use me

- A deliverable is "done" per `forge` but has not met outside eyes yet.
- Before a `gate` run — self-review clears the cheap failures first.
- Before any irreversible act (publish, send, deploy, sign, announce).
- When you wrote something fast and your confidence outruns your evidence.

Not a substitute for `gate` (verdict against a contract) or `triage` (root
cause of a known failure). Scrutinize finds *unknown* problems.

## Workflow

### 1. Cool down, then put on the attacker's hat

Never scrutinize in the same breath you wrote in. Switch context first
(walk, other task, a pause). Then run the passes **in order** and record
every finding — do not fix as you go; fixing mid-review hides patterns.

### 2. Pass one — the red-flag checklist

Sweep the whole deliverable for these, in this order:

1. **Scope creep / scope shrink** — did the work wander beyond the
   `blueprint`'s goal or quietly skip its must-haves? Diff the deliverable
   against the plan's non-goals.
2. **Unverified claims** — every statement presented as fact: what is its
   evidence? Sentences that need a check but have none are red flags, not
   flourishes. Cross-check against the `compass` metrics.
3. **Hidden assumptions** — the unspoken "obviously", "just", "everyone
   knows". Write each assumption out and ask: if this is false, what
   collapses?
4. **Silent failures** — what happens when this is used wrong, late, tired,
   or off-label? Where does it fail *quietly* instead of loudly?
5. **Voice and style drift** — does it sound like itself throughout? (For
   code: naming, structure, and idioms; for prose: tone and tense; for
   plans: same granularity of steps.)
6. **Mirror problems** — for every fix or feature, what is its symmetric
   failure? "Fast" bought with what? "Simple" dropped which necessary case?
7. **Edge cases** — empty, huge, hostile, concurrent, first-time, tenth-time,
   the exact boundary values. Name them; probe the top three.
8. **Orphans and leftovers** — dead references, TODOs masquerading as
   content, artifacts from earlier drafts that contradict the final one.

### 3. Pass two — hostile read-throughs

Read the deliverable **as someone who wants it to fail** (a skeptical
reviewer, a competitor, an auditor — role-storm personas: the auditor who
wants a citation for everything, the competitor hunting the weak claim, the
regulator checking the floor rules; `brainstorm` role-storm generates more
when three is not enough):
write down every attack line. Then read it **as the actual user on their
worst day** (tired, hurried, first-time): write down every moment of
confusion or abandonment. Both lists are findings — and they go in the
report as two separate sections, never merged.

### 4. Triage the findings — verdict + fix list

Sort findings into: **must-fix** (breaks the goal, a hard floor, an `edict`
directive, or honest trust), **should-fix** (quality; schedule via `chart`),
and **note** (record and move on). Then score competing fixes with
`brainstorm`'s convergent lens — impact vs feasibility — when you must cut
scope.

Verdict: **CLEAN** (no must-fix), **FIX-LIST** (must-fixes listed and
owners/estimates assigned), or **REWORK**. REWORK is not a bigger fix list:
it is the verdict when a must-fix invalidates the goal's structure — when
fixing it would change *what the deliverable is* rather than improve it. Go
back to `chart`, don't polish.

### 5. Fix, then re-scrutinize the delta

Run the fixes as `forge` commands (each with its check — "fix the voice drift
in section 2" gets a check: "read aloud section 2 and the ending; they sound
like the same author"). Re-review only the changed parts plus their blast
radius, then hand to `gate` with the review report attached — the report
lives at `reports/scrutinize-<deliverable>.md` (create `reports/` on first
write) and `gate` maps it by severity: must-fix → blockers, should-fix →
conditions with owners, notes → recorded.

## Report format

```markdown
# Scrutinize: <deliverable>
Verdict: CLEAN | FIX-LIST | REWORK
## Must-fix (before gate)
1. <finding> — <where> — fix via <command> — check: <...>
## Should-fix (scheduled)
## Notes
## Attack lines (hostile pass)
## Confusion moments (user pass)
```

## Worked examples

**Prose**: red-flag sweep finds an unverified claim ("readers prefer series")
and voice drift in chapter 4 (the rest is wry, ch. 4 is cheerful). Hostile
pass produces the attack "the data is old"; user pass shows confusion at the
chapter's first page. Verdict FIX-LIST: source or soften the claim, rewrite
ch. 4 opening, unify voice — each with a check.

**Code**: sweep finds a silent failure (bad input returns `None` instead of
raising), a mirror problem (the caching fix introduced stale-read risk at the
cache boundary), and an orphaned config key from the old design. Verdict
FIX-LIST with the stale-read fix as must-fix and a `triage`-style boundary
check.

**A plan**: sweep finds two steps with no done-state and one wishful
estimate (3 hours for "rewrite everything"). Hostile pass: "what if the
vendor says no?" finds no fallback. Verdict REWORK back to `chart`.

## Gates on the review itself

- Findings are recorded before any fixing; the list is the product of the
  review.
- Every must-fix has a fix command and a check — or it is not fixable, and
  the verdict is REWORK.
- Both hostile and user read-throughs happened; the report carries both
  lists.
- Judgment calls carry evidence (a quote, a repro, a number) — "feels off"
  is a note, not a finding.

## Never

- Never review the moment you finish writing. Fresh eyes are the whole tool.
- Never soften a finding to reach CLEAN. A quiet review is a useless review.
- Never fix silently during the review passes — you will lose the pattern.
- Never let "looks good to me" be your only pass. You are the first reviewer,
  not the last gate.

## Suite map — artifacts → School tools

`clarion` (interview) → `school_clarion` · `blueprint` (spec) → `school_blueprint` · `edict` (commands) → `school_edict`
`weave` (formation) → `school_weave` · `compass` (acceptance) → `school_compass` · `brainstorm` (ideas) → `school_brainstorm`
CLI: `school <artifact>` — e.g. `school edict`, `school brainstorm` (legacy alias: `school prism`).
Bridge wire names: `clarion`, `blueprint`, `edict`, `weave`, `compass`, `prism` (`prism` = brainstorm, legacy wire name kept for compatibility).
