"""1A-2Z: scope isolation - project/session skills must never leak."""

from __future__ import annotations

from pathlib import Path

from core.routing.v26.experience import Experience, ExperienceOutcome
from core.routing.v26.identity import AgentIdentity, ProjectIdentity, SessionIdentity
from core.skillgen.generate import decide_scope, experience_scope
from core.skillgen.judge import Judgment
from core.skillgen.matcher import match
from core.skillgen.pipeline import SkillPipeline
from core.skillgen.registry import SkillRegistry
from core.skillgen.types import Skill, SkillScope, SkillState, scope_visible


def _skill(
    name: str,
    scope: SkillScope,
    agent_id: str = "a1",
    project_id: str = "",
    session_id: str = "",
    state: SkillState = SkillState.ACTIVE,
) -> Skill:
    return Skill(
        name=name,
        description="Shared flaky test diagnosis capability for everyone",
        purpose="Scope test fixture",
        triggers=["flaky test diagnosis"],
        state=state,
        scope=scope,
        agent_id=agent_id,
        project_id=project_id,
        session_id=session_id,
    )


class TestScopeVisible:
    def test_global_visible_everywhere(self) -> None:
        skill = _skill("global-one", SkillScope.GLOBAL, agent_id="", project_id="",
                       session_id="")
        assert scope_visible(skill, "", "", "") is True
        assert scope_visible(skill, "any-agent", "any-project", "any-session") is True

    def test_agent_scope_requires_matching_agent(self) -> None:
        skill = _skill("agent-one", SkillScope.AGENT, agent_id="a1")
        assert scope_visible(skill, "a1", "", "") is True
        assert scope_visible(skill, "a2", "", "") is False
        assert scope_visible(skill, "", "", "") is False  # empty never matches

    def test_project_scope_requires_matching_project(self) -> None:
        skill = _skill("project-one", SkillScope.PROJECT, project_id="p1")
        assert scope_visible(skill, "a1", "p1", "") is True
        assert scope_visible(skill, "a1", "p2", "") is False
        assert scope_visible(skill, "a1", "", "") is False

    def test_session_scope_requires_matching_session(self) -> None:
        skill = _skill("session-one", SkillScope.SESSION, session_id="s1")
        assert scope_visible(skill, "a1", "p1", "s1") is True
        assert scope_visible(skill, "a1", "p1", "s2") is False
        assert scope_visible(skill, "a1", "p1", "") is False


class TestMatcherIsolation:
    def _registry(self, tmp_path: Path) -> SkillRegistry:
        reg = SkillRegistry(tmp_path)
        reg.add(_skill("global-one", SkillScope.GLOBAL))
        reg.add(_skill("project-p1", SkillScope.PROJECT, project_id="p1"))
        reg.add(_skill("session-s1", SkillScope.SESSION, session_id="s1"))
        reg.add(_skill(
            "candidate-hidden", SkillScope.GLOBAL, state=SkillState.CANDIDATE
        ))
        return reg

    def test_wrong_project_only_sees_global(self, tmp_path: Path) -> None:
        reg = self._registry(tmp_path)
        names = {h["name"] for h in
                 match(reg, "flaky test diagnosis", project_id="p2")}
        assert names == {"global-one"}

    def test_matching_project_sees_global_and_own(self, tmp_path: Path) -> None:
        reg = self._registry(tmp_path)
        names = {h["name"] for h in
                 match(reg, "flaky test diagnosis", project_id="p1")}
        assert names == {"global-one", "project-p1"}

    def test_candidate_state_hidden_by_default(self, tmp_path: Path) -> None:
        reg = self._registry(tmp_path)
        names = {h["name"] for h in match(reg, "flaky test diagnosis")}
        assert "candidate-hidden" not in names

    def test_include_unusable_exposes_candidates(self, tmp_path: Path) -> None:
        reg = self._registry(tmp_path)
        names = {h["name"] for h in
                 match(reg, "flaky test diagnosis", include_unusable=True)}
        assert "candidate-hidden" in names

    def test_no_active_skills_returns_empty(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        reg.add(_skill("s1", SkillScope.SESSION, session_id="other"))
        assert match(reg, "flaky test diagnosis", session_id="mine") == []


class TestUseScopeCheck:
    def test_use_rejects_out_of_scope(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        reg.add(_skill("project-p1", SkillScope.PROJECT, project_id="p1"))
        pipeline = SkillPipeline(reg, judge=None)
        result = pipeline.use(name="project-p1", project_id="p2")
        assert result["ok"] is False
        assert result["reason"] == "out_of_scope"

    def test_use_allows_in_scope(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        reg.add(_skill("project-p1", SkillScope.PROJECT, project_id="p1"))
        pipeline = SkillPipeline(reg, judge=None)
        result = pipeline.use(name="project-p1", project_id="p1")
        assert result["ok"] is True
        assert "markdown" in result

    def test_use_rejects_non_retrievable_state(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        reg.add(_skill("archived-one", SkillScope.GLOBAL,
                       state=SkillState.ARCHIVED))
        pipeline = SkillPipeline(reg, judge=None)
        result = pipeline.use(name="archived-one")
        assert result["ok"] is False
        assert result["reason"] == "state:archived"


class TestScopeDerivation:
    def _exp(self, project: str = "", session: str = "") -> Experience:
        kw = {}
        if project:
            kw["project"] = ProjectIdentity(project_id=project)
        if session:
            kw["session"] = SessionIdentity(session_id=session)
        return Experience.create(
            agent=AgentIdentity(agent_id="a1"),
            observation="Recurring module resolution failure diagnosed and fixed",
            action="Applied the configuration fix and verified the build",
            outcome=ExperienceOutcome.SUCCESS,
            **kw,
        )

    def _judgment(self, scope: str, conf: float = 0.9,
                  generalizable: bool = True) -> Judgment:
        return Judgment(
            worth_creating=True,
            confidence=conf,
            skill_type="diagnostic",
            reason="reusable",
            generalizable=generalizable,
            proposed_scope=scope,
        )

    def test_experience_scope_levels(self) -> None:
        assert experience_scope(self._exp()) == SkillScope.AGENT
        assert experience_scope(self._exp(project="p1")) == SkillScope.PROJECT
        assert experience_scope(self._exp(session="s1")) == SkillScope.SESSION

    def test_global_requires_generalizable_and_confidence(self) -> None:
        exp = self._exp(project="p1")
        assert decide_scope(self._judgment("global", 0.9, True),
                            exp) == SkillScope.GLOBAL
        # low confidence: falls back to the narrower experience scope
        assert decide_scope(self._judgment("global", 0.5, True),
                            exp) == SkillScope.PROJECT
        # not generalizable: falls back too
        assert decide_scope(self._judgment("global", 0.95, False),
                            exp) == SkillScope.PROJECT

    def test_narrower_wins_over_proposal(self) -> None:
        # session experience may not be widened to project/agent by the model
        exp = self._exp(session="s1")
        assert decide_scope(self._judgment("project"), exp) == SkillScope.SESSION
        assert decide_scope(self._judgment("agent"), exp) == SkillScope.SESSION
        assert decide_scope(self._judgment("session"), exp) == SkillScope.SESSION

    def test_narrowing_blocked_without_matching_identity(self) -> None:
        # experience has no project/session ids: narrowing would create an
        # unreachable skill, so the pipeline clamps back to native scope
        exp = self._exp()
        assert decide_scope(self._judgment("session"), exp) == SkillScope.AGENT
        assert decide_scope(self._judgment("project"), exp) == SkillScope.AGENT
        assert decide_scope(self._judgment("agent"), exp) == SkillScope.AGENT

    def test_narrowing_allowed_with_matching_identity(self) -> None:
        sess_exp = self._exp(session="s1")
        assert decide_scope(self._judgment("session"), sess_exp) == SkillScope.SESSION
        # project proposal blocked: session experience carries no project id
        assert decide_scope(self._judgment("project"),
                            sess_exp) == SkillScope.SESSION
        proj_exp = self._exp(project="p1")
        assert decide_scope(self._judgment("project"),
                            proj_exp) == SkillScope.PROJECT
        # session proposal blocked: project-only experience carries no session
        assert decide_scope(self._judgment("session"),
                            proj_exp) == SkillScope.PROJECT

    def test_unknown_proposal_clamped_to_native(self) -> None:
        # invalid scope string defaults to session, then clamps to the
        # experience's native scope because no session id exists
        exp = self._exp()
        j = self._judgment("galaxy")
        assert decide_scope(j, exp) == SkillScope.AGENT


class TestFromDictFallbacks:
    def test_unknown_enums_fall_back_to_safe_defaults(self) -> None:
        raw = _skill("x-one", SkillScope.GLOBAL).to_dict()
        raw["scope"] = "weird"
        raw["state"] = "weird"
        skill = Skill.from_dict(raw)
        assert skill.scope == SkillScope.SESSION
        assert skill.state == SkillState.CANDIDATE
