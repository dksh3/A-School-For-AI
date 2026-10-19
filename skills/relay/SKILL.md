---
name: relay
description: Use when work must run in parallel agents/teammates/lanes and needs collision-free merging — lane briefs, done-checks, ordered merges, gate after every merge. Any domain — not only coding. Not for one coherent judgment, shared-file edits, or when briefs cannot be written.
---

# Relay — Parallel Coordination

One runner runs the whole race; a relay team hands off a baton and nobody
collides. `relay` is the coordination skill of the Forge suite: it splits
work across parallel workers (sub-agents, teammates, or future-you sessions)
so total time drops while quality does not. The two failure modes it exists
to prevent: **collisions** (two workers on the same object) and **unmergeable
output** (work that cannot be combined without a rewrite).

**Universal by contract.** Parallelism is not a coding idea. A book ships
with parallel lanes (research / drafting / design). A launch runs parallel
workstreams (offer / channel / ops readiness). A research project runs
literature / experiments / writing. The rules below are the same in every
domain and for every kind of worker — LLM agents, humans, or hybrids.

## When to use me

- A `chart` plan has lanes, or the work decomposes into independent pieces.
- You can spawn sub-agents or delegate to people.
- The deadline is real and the critical path is too long for serial work.

Do not parallelize when: the work is one coherent judgment (one head, one
voice), the pieces share a single file/object, or the merge would cost more
than the parallelism saved. Serial is a valid formation.

## Workflow

### 1. Split along natural seams

Cut the `chart` so lanes are **independent by construction**:

- One owner per object: no two lanes ever edit the same file, chapter,
  spreadsheet, or customer.
- Interfaces first: lanes meet at *handoffs* (a schema, an outline, a
  shared vocabulary from the `blueprint`'s glossary), not in the middle of
  each other's work.
- Balance honestly: split by estimated time on the critical path, not by
  step count.

### 2. Brief each lane — the lane contract

Every lane gets a written brief. No brief, no start:

```markdown
## Lane <name> — <goal>
- Scope (owns): <exact objects this lane may touch>
- Forbidden (hands off): <everything else, named explicitly>
- Done-check: <the forge check that proves this lane finished>
- Interfaces: <what it consumes, what it must produce, formats>
- Deadline / checkpoint times
```

The **done-check** is what makes the baton trustworthy: a lane reports done
by *showing its check passing*, not by claiming effort.

### 2b. On an agent harness — how the lanes actually run

Where the harness supports background subagents (this session does):

- **Lane** → one background subagent (or worker session) per brief; the brief
  *is* that worker's prompt. One lane per dispatch, never shared files
  between concurrent lanes.
- **Checkpoint** → a structured progress report (start / blocked / done)
  with the done-check output attached.
- **Merge** → controlled integration in the pre-declared order: apply one
  lane's changes, run the combined checks, then the next.
- **Coordinator** → the session holding the plan: owns briefs, merge order,
  and the final verification.

Never pretend a subagent ran: if no lanes were actually dispatched, the
coordination claim is UNVERIFIED. No background workers available? Fall back
to **sequential execution**: run one lane to its done-check, merge + gate,
then the next — the contracts stay identical, only the concurrency goes
away.

### 3. Run with fixed checkpoints

Lanes run in parallel and report at **scheduled checkpoints** (start /
blocked / done), never "whenever". Rules:

- A blocked lane reports the block immediately and waits — it does not
  improvise into another lane's scope. Blocked is a normal state, not a
  failure.
- The coordinator answers scope questions between checkpoints (humans: in
  minutes — unanswered questions produce collisions hours later).
- If two lanes discover they need the same object mid-run, freeze both,
  re-draw the boundary, then resume. Do not negotiate scope while both are
  typing.

### 4. Merge in a defined order — gate after every merge

Merge order is decided **before** the run (usually: foundations first, then
dependents — follow the `weave` dependency links, the same `needs:` /
`Command.depends_on` links `chart` writes).

1. Integrate one lane's output against the interfaces.
2. Run the combined checks (`gate` on the merged state, not on the lane in
   isolation — interaction bugs live between lanes).
3. Only then merge the next lane. A red merge stops the relay; fix or revert
   before continuing.

Conflicts are resolved by returning to the **briefs**: the lane contract says
who owned what. If the briefs overlap, the split was wrong — fix the split,
don't blame the workers.

### 5. Close the relay

When all lanes are merged and the full `gate` passes, write the debrief: which
seams held, which collided, and what the next split should change. Ship it as
`reports/relay-<goal>.md` (create `reports/` on first write) and send the
durable lesson to memory via `school_remember` — it is the whole point of
running a relay instead of a marathon.

## Formation patterns

| Work | Lanes | Seam |
|---|---|---|
| codebase | per module/package | public interface per lane |
| book | research / drafting / line-edit | chapters or part boundaries |
| launch | offer / marketing / operations | deliverable per workstream |
| research | literature / experiments / writing | claims and figures per lane |
| event | program / logistics / comms | owner per checklist domain |

Start with 2–3 lanes. Coordination cost grows with lanes²; the fastest team
is the smallest one that still fits the deadline.

## Gates

- Every lane has a brief with scope, forbidden scope, and a done-check.
- One object, one owner — checked literally against the lane contracts.
- Merge order and conflict policy written before the run starts.
- A `gate` run after every merge, on the merged state.
- Blocked lanes escalate instead of improvising.

## Never

- Never let two lanes edit the same object "just this once" — that once is
  how relays drop batons.
- Never accept "done" without the lane's done-check passing.
- Never merge everything at the end and discover incompatibility in one big
  bang. Merge early, gate often.
- Never spawn lanes you cannot brief or check. Parallelism without contracts
  is just parallel mess.

## Suite map — artifacts → School tools

`clarion` (interview) → `school_clarion` · `blueprint` (spec) → `school_blueprint` · `edict` (commands) → `school_edict`
`weave` (formation) → `school_weave` · `compass` (acceptance) → `school_compass` · `brainstorm` (ideas) → `school_brainstorm`
CLI: `school <artifact>` — e.g. `school edict`, `school brainstorm` (legacy alias: `school prism`).
Bridge wire names: `clarion`, `blueprint`, `edict`, `weave`, `compass`, `prism` (`prism` = brainstorm, legacy wire name kept for compatibility).
