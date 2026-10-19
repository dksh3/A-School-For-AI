# Question Budget — Configurable Adaptive Questioning

`school elicit` can run a **budgeted adaptive questioning controller**: the user sets the
maximum number of questions School may ask, and School adapts each next question to the
latest answer and evidence until the objective is covered or the budget is spent.

## Configuration

| Field | Default | Allowed | Meaning |
|---|---|---|---|
| `question_budget` | `20` | integer `1..100` | Strict maximum of **user-facing** questions for the session |
| `strategy` | `adaptive` | `adaptive` | Selection strategy (only `adaptive` is supported) |
| `depth` | `balanced` | `balanced` | Depth policy (only `balanced` is supported) |
| `allow_followups` | `true` | bool | Follow-up questions allowed (they share the same budget) |
| `stop_early` | `true` | bool | Stop when the objective is genuinely covered |

- Maximum budget is **100** (`MAX_QUESTION_BUDGET`). Values above the limit are
  **rejected, never silently clamped** — the error names the limit.
- Zero, negative, booleans-as-integers (`True`), malformed strings, floats, `None`, and
  lists are all rejected with an actionable `ValueError` message. Invalid configuration
  can never create an unbounded loop.
- Configuration is established at session creation and **fixed for the life of the
  session**. A resumed session refuses configuration drift (`--question-budget`,
  `--no-followups`, `--no-early-stop` mismatches) and tells you to start a new session.

## Setting a custom budget (real entry point)

```bash
python school/cli.py elicit --file req.json --question-budget 5 --session sess.json
python school/cli.py elicit --session sess.json                       # resume, no reset
python school/cli.py elicit --file req.json --answers ans.json --question-budget 8
python school/cli.py elicit --file req.json --no-followups --no-early-stop
```

`--answers` takes a JSON list of `{"id" | "question", "answer", "confidence"?}` rows.
An unknown question id is an error (`question not in this session`) — never a silent drop.

## Budget accounting (exact rule)

1. A question consumes **1 unit only when it is actually presented** to the user
   (`ask_next()` returns it).
2. **Follow-ups consume the same counter** as original questions.
3. Rephrases, retries, and refused duplicates **never consume and never refill** the
   budget (`repeats_refused` is tracked separately).
4. Internal analysis (prioritization, status computation, rendering) is not counted.
5. The count never exceeds the configured maximum; the final allowed question reports
   `remaining after: 0`.
6. A resumed session **preserves** the presented count from its session file. Malformed
   session state is rejected with an error — it never silently restores a fresh budget.

## Adaptive selection

Selection reuses `core/forge/requirements.py` (`prioritize` / `next_batch` /
`mark_asked` / `elicitation_status`) — there is no competing ranking system. After each
answer the controller re-validates, records, updates state, and recomputes the next
question. Deterministic tie-breaking (materiality, then id). Answered, duplicate, and
reliably-derivable questions are never re-asked.

Follow-ups (when `allow_followups`) are raised **deterministically** when an answer is:

- ambiguous or incomplete (empty, uncertain markers such as "not sure", trailing `?`),
- low confidence (`< 0.5` → the unknown becomes `CONFLICTED`),
- contradictory with a previous answer to the same variable (both become `CONFLICTED`).

Follow-ups are not an LLM question generator; they restate the specific gap.

## Early stopping vs honest stops

| Stop reason | Meaning | Outcome |
|---|---|---|
| `early-stopped` | Objective covered *and* verification defined; more questions would not reduce uncertainty | `succeeded` |
| `complete` | Allowance spent exactly as the objective became covered | `succeeded` |
| `budget-exhausted` | Questioning allowance spent — **not** a success claim | `budget exhausted (not success)` |
| `no-questions-remaining` | Queue empty but verification is undefined — **not** a success claim | `incomplete (not success)` |
| `blocked` | Material unresolved/conflicted questions remain; affected conclusions stay `UNRESOLVED` | `incomplete (not success)` |

Stopping is **never** triggered by generator failure, parse/persistence errors, a
convenient answer, or a merely emptied queue. Budget exhaustion means the allowance is
spent; it never means the investigation succeeded. Material unresolved questions block
closure (`UNRESOLVED` → conclusions marked `BLOCKED`).

## Persistence / resume semantics

- Session JSON (version 1) stores: config, presented count, asked keys, answers,
  follow-up/repeat counters, verification flag, stop reason/detail, and full unknown
  states (including evidence links via `depends_on` / provenance).
- Written atomically (`.tmp` + `os.replace`).
- Loader is strict: wrong version, wrong shapes, out-of-range counts, or invalid config
  raise `ValueError` (`elicit error: cannot restore session: …`, exit 2). Malformed data
  is never converted into an empty investigation or a fresh budget.
- Legacy `elicit --file/--interview/--asked` invocations are byte-identical to before —
  controller mode only activates when at least one new flag is passed.

## Known limitations

- Follow-up generation is deterministic (marker/contradiction rules), not generative.
- `strategy`/`depth` are typed and validated but only `adaptive`/`balanced` exist;
  the fields are forward-compatible hooks.
- The session file's `questions_log()` shape matches the investigation engine's question
  entries (`{id, question, why, answer, effect}`) so logs can feed an investigation
  case, but the two stores remain separate (a shared findings-identity contract is a
  documented open design decision, not implemented).
