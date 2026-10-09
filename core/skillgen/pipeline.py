"""1A-2Z skill pipeline: experience -> skill (Phase 1).

Order: experience -> candidate detection -> value filter -> model judgment
-> generalization -> generation -> validation -> testing -> registration ->
versioning. Deterministic stages run first and are cheap; only candidates
above threshold with budget remaining and a configured judge consume a
model call. The model judges - 1A-2Z executes and stays in control.
"""

from __future__ import annotations

import contextlib
from typing import Any

from core.routing.v26.experience import Experience, ExperienceOutcome
from core.routing.v26.identity import AgentIdentity
from core.skillgen.budget import ModelCallBudget
from core.skillgen.candidate import MIN_CANDIDATE_SCORE, Candidate, detect, to_report
from core.skillgen.evolve import apply_feedback, consolidate, evaluate_lifecycle, revise
from core.skillgen.generate import build_manual_skill, generalize
from core.skillgen.judge import Judgment, ModelJudge, build_judgment_prompt, parse_judgment
from core.skillgen.matcher import match
from core.skillgen.registry import SkillRegistry, similarity
from core.skillgen.types import Skill, SkillState, safe_float, safe_int, safe_str, scope_visible
from core.skillgen.validate import validate_skill

# Deterministic gate: judgment only when score clears the threshold.
JUDGE_MIN_SCORE = MIN_CANDIDATE_SCORE


def _task_key(task: Any, experience: Experience) -> str:
    key = safe_str(task, 200)
    if not key:
        try:
            session = experience.session
            key = safe_str(session.session_id, 200) if session is not None else ""
        except Exception:  # noqa: BLE001 - hostile experience
            key = ""
    return (key or "default")[:64]


class SkillPipeline:
    """The 1A-2Z loop for one registry (worktree)."""

    def __init__(
        self,
        registry: SkillRegistry,
        judge: ModelJudge | None = None,
        max_model_calls: int | None = None,
    ) -> None:
        self.registry = registry
        self._judge = judge
        self.budget = ModelCallBudget(registry.stats, max_per_task=max_model_calls)

    # -- judge wiring ------------------------------------------------------

    @property
    def judge(self) -> ModelJudge | None:
        if self._judge is not None:
            return self._judge
        from core.skillgen.judge import default_judge

        self._judge = default_judge()
        return self._judge

    def set_judge(self, judge: ModelJudge | None) -> None:
        self._judge = judge

    # -- stage helpers -----------------------------------------------------

    def _existing_similarity(self, experience: Experience) -> tuple[float, str]:
        """Similarity of the experience text to the closest existing skill."""
        probe = Skill(
            name="probe",
            description=(
                f"{safe_str(experience.observation, 2000)} "
                f"{safe_str(experience.action, 2000)}"
            ),
            purpose="",
        )
        best_sim, best_name = 0.0, ""
        for skill in self.registry.all():
            sim = similarity(skill, probe)
            if sim > best_sim:
                best_sim, best_name = sim, skill.name
        return best_sim, best_name

    def _self_test(self, skill: Skill) -> tuple[bool, str]:
        """Testing stage: the skill must retrieve for its own triggers."""
        query = " ".join(safe_str(t, 100) for t in skill.triggers[:2]) or safe_str(skill.name, 100)
        hits = match(self.registry, query, agent_id=skill.agent_id,
                     project_id=skill.project_id, session_id=skill.session_id,
                     include_unusable=True, limit=5)
        names = [h["name"] for h in hits]
        if skill.name in names:
            return True, "trigger self-test passed"
        return False, "skill did not retrieve for its own triggers"

    # -- main entry: automatic path ---------------------------------------

    def observe(
        self,
        experience: Experience,
        task: str = "",
        agent_id: str = "opencode",
        project_id: str = "",
        session_id: str = "",
    ) -> dict[str, Any]:
        """Run the full pipeline for one experience (cheap reject first).

        Fail-open: any hostile input yields a structured rejection report.
        """
        try:
            return self._observe(experience, task, agent_id, project_id, session_id)
        except Exception as exc:  # noqa: BLE001 - fail open at the stage boundary
            try:
                eid = safe_str(experience.experience_id, 200)
            except Exception:  # noqa: BLE001 - hostile experience object
                eid = ""
            report = {
                "experience_id": eid,
                "candidate": False,
                "action": "rejected:internal_error",
                "error": type(exc).__name__,
            }
            with contextlib.suppress(Exception):
                self.registry.log_event("internal_error", f"observe: {exc}"[:300])
            return report

    def _observe(
        self,
        experience: Experience,
        task: str = "",
        agent_id: str = "opencode",
        project_id: str = "",
        session_id: str = "",
    ) -> dict[str, Any]:
        report: dict[str, Any] = {"experience_id": experience.experience_id}
        task_key = _task_key(task, experience)

        sim, merge_hint = self._existing_similarity(experience)
        candidate = detect(experience, existing_similarity=sim,
                           existing_merge_hint=merge_hint)
        if candidate is None:
            report.update({"candidate": False, "action": "rejected:not_candidate"})
            return report
        report["candidate"] = True
        report.update(to_report(candidate))

        # Duplicate of an existing skill: fold in, no model call.
        if merge_hint and sim >= 0.85:
            target = self.registry.get(merge_hint)
            if target is not None:
                exp = candidate.experience
                target.created_from.append(exp.experience_id)
                target.record("experience_absorbed",
                              f"near-duplicate experience folded in "
                              f"(sim={sim:.2f})",
                              experience_id=exp.experience_id)
                evaluate_lifecycle(target)
                self.registry.save()
                report.update({
                    "action": "merged_experience",
                    "skill": target.name,
                    "score": candidate.score,
                })
                return report

        if candidate.score < JUDGE_MIN_SCORE:
            report.update({"action": "rejected:below_threshold",
                           "threshold": JUDGE_MIN_SCORE})
            return report

        if candidate.novelty < 0.15 and merge_hint:
            report.update({"action": "rejected:insufficient_novelty",
                           "related": merge_hint})
            return report

        # --- model judgment (budgeted) ---
        judge = self.judge
        if judge is None:
            report.update({"action": "rejected:no_judge_configured"})
            return report
        if not self.budget.allow(task_key):
            report.update({"action": "rejected:budget_exhausted",
                           "budget": self.budget.report(task_key)})
            return report
        self.budget.record(task_key)
        report["judged"] = True
        try:
            raw, model_id = judge(build_judgment_prompt(candidate))
        except Exception as exc:  # judge failure must never break the caller
            report.update({"action": "rejected:judge_error",
                           "error": str(exc)[:200],
                           "budget": self.budget.report(task_key)})
            self.registry.log_event("judge_error", str(exc)[:300])
            self.registry.save()
            return report
        judgment = parse_judgment(raw, model_id=model_id)
        report["judgment"] = judgment.to_dict()
        report["budget"] = self.budget.report(task_key)

        if not judgment.worth_creating:
            report["action"] = "rejected:model_not_worth"
            self.registry.log_event("judged_reject", judgment.reason[:300])
            self.registry.save()
            return report
        if not judgment.safety_ok:
            report["action"] = "rejected:model_safety"
            self.registry.save()
            return report

        # --- generalization + generation ---
        skill = generalize(candidate.experience, judgment, model_id, merge_hint)

        # Duplicate check against registry (post-generation).
        best = self.registry.best_match(skill)
        if best is not None and best[1] >= 0.85:
            target = self.registry.get(best[0])
            if target is not None:
                for exp_id in skill.created_from:
                    if exp_id not in target.created_from:
                        target.created_from.append(exp_id)
                target.record("experience_absorbed",
                              f"new candidate was a duplicate (sim={best[1]:.2f})",
                              experience_id=skill.created_from[-1])
                self.registry.save()
                report.update({"action": "merged_duplicate",
                               "skill": target.name, "similar": best[1]})
                return report

        # --- validation ---
        skill.state = SkillState.VALIDATING
        ok, reason = validate_skill(skill)
        if not ok:
            skill.state = SkillState.CANDIDATE
            report.update({"action": "rejected:validation", "reason": reason})
            self.registry.save()
            return report

        # --- testing + registration ---
        existing_same = self.registry.get(skill.name)
        if existing_same is not None:
            # Same name already registered (e.g. regenerated from a similar
            # experience): fold the evidence in instead of double-registering.
            for exp_id in skill.created_from:
                if exp_id not in existing_same.created_from:
                    existing_same.created_from.append(exp_id)
            existing_same.record(
                "experience_absorbed",
                "same-name regeneration merged",
                experience_id=skill.created_from[-1],
            )
            self.registry.save()
            report.update({"action": "merged_duplicate",
                           "skill": existing_same.name, "similar": 1.0})
            return report
        self.registry.add(skill)
        tested, test_reason = self._self_test(skill)
        skill.record("validated", reason, experience_id=skill.created_from[-1])
        if not tested:
            skill.state = SkillState.CANDIDATE
            self.registry.save()
            report.update({"action": "rejected:self_test",
                           "reason": test_reason, "skill": skill.name})
            return report
        skill.state = SkillState.ACTIVE
        skill.record("activated", test_reason, experience_id=skill.created_from[-1])
        self.registry.log_event("created", f"{skill.name} v{skill.version} "
                                           f"conf={skill.confidence:.2f}")
        self.registry.save()
        report.update({
            "action": "created",
            "skill": skill.name,
            "version": skill.version,
            "state": skill.state.value,
            "scope": skill.scope.value,
            "confidence": skill.confidence,
        })
        return report

    def observe_experience_dict(
        self, data: dict[str, Any], task: str = "", **kw: Any
    ) -> dict[str, Any]:
        """Convenience: run observe() from a serialized experience."""
        try:
            experience = Experience.from_dict(data)
        except Exception as exc:  # noqa: BLE001 - hostile payload: graceful reject
            return {"action": "rejected:bad_experience", "error": type(exc).__name__}
        return self.observe(experience, task=task, **kw)

    # -- explicit agent path (skill_create) --------------------------------

    def create_manual(
        self,
        payload: dict[str, Any],
        agent_id: str = "opencode",
        project_id: str = "",
        session_id: str = "",
    ) -> dict[str, Any]:
        """Agent-authored skill: validated + tested, never trusted raw."""
        try:
            return self._create_manual(payload, agent_id, project_id, session_id)
        except Exception as exc:  # noqa: BLE001 - fail open: graceful rejection
            return {"ok": False, "action": "rejected:internal_error",
                    "reason": f"internal_error:{type(exc).__name__}"}

    def _create_manual(
        self,
        payload: dict[str, Any],
        agent_id: str = "opencode",
        project_id: str = "",
        session_id: str = "",
    ) -> dict[str, Any]:
        agent_id = safe_str(agent_id, 200) or "opencode"
        skill = build_manual_skill(payload, agent_id, project_id, session_id)
        if not skill.name:
            return {"ok": False, "action": "rejected:validation",
                    "reason": "name required"}
        existing = self.registry.get(skill.name)
        if existing is not None:
            # Same name: treat as revision request, not a new skill.
            merged = revise(existing, payload, actor=agent_id)
            merged.record("revised", "manual update via skill_create",
                          actor=agent_id)
            ok, reason = validate_skill(merged)
            if not ok:
                merged.state = SkillState.CANDIDATE
                self.registry.save()
                return {"ok": False, "action": "rejected:validation",
                        "reason": reason, "skill": merged.name}
            merged.state = (
                SkillState.ACTIVE if merged.state == SkillState.PROVEN
                else merged.state
            )
            self.registry.save()
            return {"ok": True, "action": "revised", "skill": merged.name,
                    "version": merged.version, "state": merged.state.value}

        skill.state = SkillState.VALIDATING
        ok, reason = validate_skill(skill)
        if not ok:
            return {"ok": False, "action": "rejected:validation",
                    "reason": reason}
        best = self.registry.best_match(skill)
        if best is not None and best[1] >= 0.85:
            target = self.registry.get(best[0])
            if target is not None:
                self.registry.merge_into(
                    target.name, skill, "manual create was a duplicate"
                )
                self.registry.save()
                return {"ok": True, "action": "merged_duplicate",
                        "skill": target.name, "similar": best[1],
                        "version": target.version}
        self.registry.add(skill)
        tested, test_reason = self._self_test(skill)
        skill.record("validated", reason, actor=agent_id)
        if not tested:
            skill.state = SkillState.CANDIDATE
            self.registry.save()
            return {"ok": False, "action": "rejected:self_test",
                    "reason": test_reason, "skill": skill.name}
        skill.state = SkillState.ACTIVE
        skill.record("activated", test_reason, actor=agent_id)
        self.registry.log_event("created", f"{skill.name} (manual) "
                                           f"conf={skill.confidence:.2f}")
        self.registry.save()
        return {"ok": True, "action": "created", "skill": skill.name,
                "version": skill.version, "state": skill.state.value,
                "scope": skill.scope.value, "confidence": skill.confidence}

    # -- reuse + feedback + evolution --------------------------------------

    def use(
        self,
        name: str = "",
        query: str = "",
        agent_id: str = "opencode",
        project_id: str = "",
        session_id: str = "",
    ) -> dict[str, Any]:
        """Retrieve a skill for use (scope-checked) and record the use."""
        try:
            name = safe_str(name, 200)
            query = safe_str(query, 2000)
            if name:
                skill = self.registry.get(name)
                if skill is None:
                    return {"ok": False, "reason": "not_found", "skill": name}
                if not scope_visible(skill, agent_id, project_id, session_id):
                    return {"ok": False, "reason": "out_of_scope", "skill": name}
                if skill.state not in {SkillState.ACTIVE, SkillState.PROVEN}:
                    return {"ok": False, "reason": f"state:{skill.state.value}",
                            "skill": name}
                skill.use_count += 1
                skill.record("used", "retrieved for reuse")
                self.registry.save()
                return {"ok": True, "skill": skill.name, "state": skill.state.value,
                        "confidence": skill.confidence, "version": skill.version,
                        "procedure": list(skill.procedure),
                        "triggers": list(skill.triggers),
                        "constraints": list(skill.constraints),
                        "markdown": skill.to_skill_md()}
            if not query:
                return {"ok": False, "reason": "name or query required"}
            hits = match(self.registry, query, agent_id=agent_id,
                         project_id=project_id, session_id=session_id, limit=5)
            return {"ok": True, "matches": hits}
        except Exception as exc:  # noqa: BLE001 - fail open
            return {"ok": False, "reason": f"internal_error:{type(exc).__name__}"}

    def feedback(
        self,
        name: str,
        success: bool,
        note: str = "",
        agent_id: str = "opencode",
    ) -> dict[str, Any]:
        try:
            name = safe_str(name, 200)
            skill = self.registry.get(name)
            if skill is None:
                return {"ok": False, "reason": "not_found", "skill": name}
            try:
                truth = bool(success)
            except Exception:  # noqa: BLE001 - hostile __bool__
                truth = False
            apply_feedback(skill, truth, safe_str(note, 500))
            self.registry.log_event(
                "feedback", f"{skill.name}: {'+' if truth else '-'} "
                            f"conf={safe_float(skill.confidence, 0.5):.3f} "
                            f"state={skill.state.value}"
            )
            self.registry.save()
            return {"ok": True, "skill": skill.name, "state": skill.state.value,
                    "confidence": skill.confidence,
                    "success_count": skill.success_count,
                    "failure_count": skill.failure_count}
        except Exception as exc:  # noqa: BLE001 - fail open
            return {"ok": False, "reason": f"internal_error:{type(exc).__name__}"}

    def evolve(self, action: str = "consolidate", name: str = "",
               changes: dict[str, Any] | None = None,
               agent_id: str = "opencode") -> dict[str, Any]:
        """Explicit evolution: consolidate duplicates or revise a skill."""
        try:
            action = safe_str(action, 32)
            name = safe_str(name, 200)
            agent_id = safe_str(agent_id, 200) or "opencode"
            if action == "consolidate":
                merged = consolidate(self.registry)
                return {"ok": True, "merged": merged, "count": len(merged)}
            if action == "revise":
                skill = self.registry.get(name)
                if skill is None:
                    return {"ok": False, "reason": "not_found", "skill": name}
                if not isinstance(changes, dict) or not changes:
                    return {"ok": False, "reason": "changes required"}
                skill = revise(skill, changes, actor=agent_id)
                ok, reason = validate_skill(skill)
                if not ok:
                    skill.state = SkillState.CANDIDATE
                    self.registry.save()
                    return {"ok": False, "action": "rejected:validation",
                            "reason": reason}
                self.registry.save()
                return {"ok": True, "action": "revised", "skill": skill.name,
                        "version": skill.version}
            if action == "recompute":
                states = {}
                for s in self.registry.all():
                    states[safe_str(s.name, 100)] = evaluate_lifecycle(s).value
                self.registry.save()
                return {"ok": True, "states": states}
            return {"ok": False, "reason": f"unknown action: {action}"}
        except Exception as exc:  # noqa: BLE001 - fail open
            return {"ok": False, "reason": f"internal_error:{type(exc).__name__}"}

    def status(self) -> dict[str, Any]:
        """Registry + budget observability (skill_status)."""
        try:
            by_state: dict[str, int] = {}
            for skill in self.registry.all():
                key = safe_str(skill.state.value, 32)
                by_state[key] = by_state.get(key, 0) + 1
            from core.skillgen.judge import default_judge

            judge = self._judge if self._judge is not None else default_judge()
            events = self.registry.stats.get("events", [])
            if not isinstance(events, list):
                events = []
            return {
                "ok": True,
                "skills": len(self.registry.all()),
                "by_state": by_state,
                "model_calls_total": safe_int(self.registry.stats.get("model_calls_total", 0)),
                "judge_configured": judge is not None,
                "storage": safe_str(self.registry.path, 500),
                "recent_events": SkillRegistry._safe_events(events)[-5:],
            }
        except Exception as exc:  # noqa: BLE001 - fail open
            return {"ok": False, "reason": f"internal_error:{type(exc).__name__}"}


def quick_observe(
    worktree: str,
    experience: Experience,
    task: str = "",
    judge: ModelJudge | None = None,
    **kw: Any,
) -> dict[str, Any]:
    """One-shot helper: registry from worktree + observe (used by tools/tests)."""
    from core.skillgen.registry import registry_for

    pipeline = SkillPipeline(registry_for(worktree), judge=judge)
    return pipeline.observe(experience, task=task, **kw)


__all__ = [
    "SkillPipeline",
    "quick_observe",
    "Candidate",
    "Judgment",
    "parse_judgment",
    "ModelJudge",
    "ExperienceOutcome",
    "AgentIdentity",
]
