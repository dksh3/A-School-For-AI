# SDD ledger — plan: docs/superpowers/plans/2026-10-02-adaptive-routing-loop.md

## Pre-flight conflict scan (run before Task 1)

| Pair | Shared surface | Checked | Finding |
|---|---|---|---|
| T1→T2 | plugin_source.py: T1 produces engageFor/readKnobs/appendEvidence/normalizeSeverity/memoryRoot/consts; T2 consumes for tools + metadata.engagement | plan T2 text references T1 names | none — sequential, same file |
| T2→T3 | TS↔MCP description parity (identical strings) | Global Constraint mandates identical; parity regex auto-covers | none |
| T1/T2→T3 | engage mapping light→skill, medium\|high→both | stated once in constraints, both sides tested | none |
| T3→T4 | stdio tests call assess/report/stats | T4 after T3, depends on T3 registrations | none |
| T5 | school/cli.py + new skill_source.py | no other task touches cli.py | none |
| T6 | docs/README only | runs after all | none |
| T2 vs identity test | exact tool-count assertions | plan notes possible trip | Ruling 4 |
| Global Constraint vs baseline | "ruff clean on every changed file" vs plugin_source.py pre-existing E501s (16) | baseline not clean | Ruling 2 |
| T1 self | tests specified vs code specified | create test_school_routing.py covering helpers | clean |
| T5 self | skill content inline in plan | full text provided | clean |

## Rulings

1. Ruling: work directly on `main` (no worktree) — session convention; 5 prior user-approved main commits (32d4506, 14127de, dafce0c, 70141cc, a5c8b55); user asked to "commit everything". — Cost if wrong: revertable history noise on main.
2. Ruling: "ruff clean on changed files" = no NEW ruff errors vs baseline (plugin_source.py has pre-existing E501s inside the embedded TS string; new long physical lines are forbidden). — Cost if wrong: minor lint debt remains.
3. Ruling: no `sh.exe` on this system → PowerShell equivalents of sdd-workspace/task-brief/review-package (same outputs: workspace `.superpowers/sdd/2026-10-02-adaptive-routing-loop/`, briefs by line-slice, review packages via git log/diff redirected to file). — Cost if wrong: none, artifacts equivalent.
4. Ruling: task tool exposes no model parameter → implementers and reviewers dispatched as `general` subagents (fix rounds resume via task_id); model-tier selection unavailable in harness. — Cost if wrong: less cost tuning; mitigated by precise briefs.
5. Ruling (standing): identity test tool-count/list updates are additive-only when T2 adds the two tools. — Cost if wrong: test loosened by two names.

## Progress


Task 1: dispatched (brief task-1-brief.md), report task-1-report.md, package task-1-review-package.md
Task 1: review — 1 Important (plan-mandated clampNum null/boolean), 5 Minors deferred (cache key path; skipped rows ms:0/hits:null; executionStart capMap leak; substring-only assertions; .evo/ gitignore gap)
Task 1: minor (deferred): knobsCache keys on mtimeMs only, not file path (plugin_source.py:299)
Task 1: minor (deferred): skip-gated executions write ms:0/hits:null, indistinguishable from instant recall (plugin_source.py:1065)
Task 1: minor (deferred): executionStart has no capMap; leaks if after-hook never fires (plugin_source.py:246)
Task 1: minor (deferred): test_school_routing.py assertions substring-only; trim/clamp/marker not behaviorally exercised
Task 1: minor (deferred): .gitignore covers .school/ .lerev/ but not .evo/ (pre-existing)
Task 1: Ruling: baseline 2483 in dispatch was stale — actual pre-task baseline 2487 + 9 new tests = 2496 (diff verified exactly 9 added); suite green. — Cost if wrong: none, arithmetic verified against b1 record.
Task 1: Ruling: verbatim-`none` engage gating NOT in T1 by design — normalizeSeverity/engageFor ignore it; Task 2's microAssess must emit engage 'none' only for a verbatim micro-model 'none'; MCP self-rated path never produces none. — Cost if wrong: none-gate moves task, enforced in T2/T3 tests.
Task 1: Ruling: clampNum null/boolean → per-key default IS a spec violation ("per-key defaults on invalid/missing values") despite plan's verbatim code — fix wins over plan text. — Cost if wrong: null becomes non-coercing (intended).
Task 1: fix round 1 dispatched (Important #1 only; minors deferred)
Task 1: fix round 1/5 (1 addressed, 0 open — clampNum null/boolean; commits 2c54e06..c31fb54)
Task 1: minor (deferred): clampNum still coerces ""/[] via Number() (plugin_source.py:292) — out-of-scope residual from fix review
Task 1: complete (commits a5c8b55..c31fb54, review clean)
Task 2: dispatched (task-2-brief.md), report task-2-report.md, package task-2-review-package.md
Task 2: review — 1 Important (plan-mandated routePrompt prompt >150 tokens worst case), 3 Minors deferred (source label when ROUTE=0 no-arg; stats all-or-nothing on corrupt JSONL line; bridge main importability assert dropped)
Task 2: minor (deferred): source "self-rated" mislabel when SCHOOL_ROUTE=0 with no severity arg (plugin_source.py:1270)
Task 2: minor (deferred): one corrupt JSONL line discards whole stats file (plugin_source.py:1319)
Task 2: minor (deferred): test_bridge_module_importable lacks callable(main) assert (test_school_plugin_bridge.py:103)
Task 2: Ruling: routePrompt situation truncated to 200 chars INSIDE routePrompt — spec/plan binding contract "prompt <=150 tokens" beats plan's verbatim full-situation embedding; tool-level 500-char display cap unchanged. — Cost if wrong: less situation context for micro-model (acceptable; stats/lessons carry detail).
Task 2: Ruling: report-count claims (suite 2506, node-check, MATCH) deferred to T6 live battery (plan mandates them there anyway); reviewer independently verified ruff delta = 0.
Task 2: fix round 1 dispatched (Important #1 only; minors deferred)
Task 2: fix round 1/5 (1 addressed, 0 open — routePrompt slice(0,200); commits e555fb9..740d6c4)
Task 2: complete (commits c31fb54..740d6c4, review clean)
Note (rebrand): teacher→school rebrand completed; all plan/brief paths now school/. plugin_source.py line numbers shifted (discovery/memory-chain edits) — re-locate symbols by grep when resuming Task 3. Description strings bulk-renamed identically on TS and MCP; parity tests hold.
Task 3: implementer DONE (b4a2d9d, 2516 passed, ruff 0 new). Concerns: 2 brief-inconsistency rulings (ok-default True; lesson into action field), EXPECTED_TOOLS in integration file, annotation set +stats, TS-side lesson-drop residual parked for T6.
Task 3: fix round 1/5 (TS lesson-drop addressed pending re-review; commits b4a2d9d..7ef7c03).
Task 3: complete (commits b4a2d9d..7ef7c03, review clean after 1 fix round: TS lesson-drop addressed).
Task 4: inline (user directive "ok resume, dont dispatch" - no subagent), complete
Task 4: brief adapted: async _server(tmp_path) pattern instead of sync stdio_session fixture; payload via json.loads(content[0].text) (file convention) instead of brief's res.structured_content; new class TestRouteStdio (assess missing-severity -> MCPError proven live: handler ValueError propagates through SDK, same as school_bogus path)
Task 4: evidence - tests/integration/test_mcp_stdio.py 18/18 passed (2 new); commit "test(mcp): route/stats stdio integration"
Task 5: inline (per "dont dispatch"), complete
Task 5: rulings - (a) skill description line split across 3 backslash-continuation lines inside ROUTING_SKILL_MD (physical lines <=100 for E501; final single-line YAML identical to plan); (b) install_skill root expression wrapped as parenthesized conditional (plan one-liner was 95 chars, wrapped for safety, semantics identical); (c) dropped plan's unused `from pathlib import Path` in test_school_skill.py (F401); (d) plan transcription slip corrected: tags <helpful|useless|neutral> (not "useful").
Task 5: evidence - tests/unit/test_school_skill.py 3/3; ruff skill_source/cli/skill tests clean; real `school install --force` prints "Skill installed: ...skills/school-routing/SKILL.md" + frontmatter verified; battery 2594 passed; commit "feat(skill): school-routing skill with audit/knobs/lessons workflow, shipped by install"

Task 6: inline (per "dont dispatch"), complete
Task 6: rulings - (a) micro-call live gate executed against headless `opencode serve --port 48123 --pure` in temp worktree, project config opencode.json setting small_model = groq/openai/gpt-oss-120b; default model hit Groq 8000 TPM (16k-token request hung), free mimo/nemotron models took 26-83s wall > ROUTE_TIMEOUT_MS=10000, --pure cut prompt to ~825 input tokens so groq answers ~1.5s model/7s wall - ROUTE_TIMEOUT_MS kept at plan-pinned 10000 (plan L19 contract + tests/unit/test_school_routing.py:10). - Cost if wrong: none, spec honored.
Task 6: ruling - (b) microAssess consumes client from School() ROOT ctx (school_route uses ctx.client/ctx.directory), execute context supplies worktree for appendEvidence - harness passed client at both levels. - Cost if wrong: none.
Task 6: evidence - real micro-call PASSED: source "micro-model", severity/engage/reason present, scratchCount 0 (scratch session deleted); node --check exit 0; install --force -> plugin MATCH (ROUTE_TIMEOUT_MS line) + skills/school-routing/SKILL.md True; doctor all 8 PASS "SCHOOL IS READY" exit 0; `school mcp config opencode` smoke exit 0 (valid JSON config); ruff 7-file task list All checks passed; battery 2594 passed in 123s (baseline held).
Task 6: complete, commit 8a81eeb "docs(routing): adaptive routing loop user guide" (docs/routing.md + README.md pointer only)
AR PLAN STATUS: all 6 tasks complete (T1 b4a2d9d..7ef7c03, T2 c31fb54..740d6c4, T3 b4a2d9d..7ef7c03-era, T4 0131512, T5 aaae255, T6 8a81eeb).

## Post-plan feature (user request): always-visible status
Feature: "i want this thing as a tool where it always shows up under the execution of a prompt ... even every single tool also depending on the situation (using the model/agent's computational power we can decide which tool to use and which skill too), and also the context optimizer, learner, and the diagnose and important ones always it should work and visually show" - brainstorming classified bounded; user's "finish that now and report to me everything" treated as design approval (no wait gate).
Design - commit c62e3ce "feat(school): always-visible status footer, dashboard tool, adaptive tool/skill picks" (9 files, +338/-15):
- experimental.text.complete hook appends "[school] route/next/ctx/recall/learn/dag" footer under EVERY assistant response; semantics verified in opencode 1.18.34 binary source (hook text is persisted via updatePart at text-end); SCHOOL_HOOKS=0 kill switch; idempotent via includes("[school] route:").
- school_dashboard tool (14th tool; TS+MCP twins, identical description for parity tests; read-only annotations; ordered after school_status everywhere); MCP twin derives route/recall from evidence tail + bridge status.
- routePrompt now asks micro-model for tools[] (<=3) / skills[] (<=2); parseRouteDecision validates/caps; school_route output includes picks; fallback defaultPicks by engagement (both->school_recall,school_search + school-routing skill; skill->skill; none->[]); schoolStatus.next surfaces in footer.
- Subsystem chips: ctx from recordCtxSavings (bridge payload tokens_in/out + heuristic path), learn from remember/learn result (ready/ok/fail/off), diag from bridge+hooks, recall from exec/prompt recall hits.
- Ruling: dashboard description teaches "call once per prompt" so the model shows the tool card under every turn; footer is the guaranteed path. - Cost if wrong: model may skip tool calls; footer unaffected.
- Ruling: school_dashboard ordered after school_status to satisfy test_school_plugin_bridge EXPECTED_OPENCODE_TOOLS order (dashboard-first failed order test; fixed by moving TS block, not by weakening the test).
- Ruling: MCP dashboard output is stateless (evidence tail + bridge), NOT parity-tested with plugin output - only DESCRIPTION parity is contractually enforced.
Tests: +9 (2603 total, all green): hooks EXPECTED_HOOKS+footer/dashboard class, routing picks contract, stdio dashboard call, live TestLiveStatusFooter (append, idempotence, kill switch, dashboard lines); tool-surface counts 13->14 in 3 files (hooks, bridge approved-surface, MCP EXPECTED_TOOL_ORDER/EXPECTED_TOOLS/read_only).
Gates: battery 2603 passed; ruff plugin_source 16 = baseline, new/changed files clean; node --check 0; install --force -> footer+dashboard MATCH in installed plugin + skill; doctor SCHOOL IS READY; mcp config exit 0. docs/routing.md gained "Always-visible status" section (committed earlier in 8a81eeb? no - updated here, included in c62e3ce).
NOTE: docs/routing.md always-visible section was edited after 8a81eeb and committed inside c62e3ce.
