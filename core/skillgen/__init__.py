"""1A-2Z: automatic skill generation and evolution.

Phase 1 loop: experience -> candidate detection -> value filter -> small-model
judgment -> generalization -> skill generation -> validation -> testing ->
registration -> versioning -> reuse -> feedback -> improvement. Deterministic
signals first; the model only judges potentially valuable candidates; 1A-2Z
always stays in control of what gets written.

Phase 2 adds GitHub skill discovery as an isolated extension (see
core.skillgen.github): bounded search, untrusted-content analysis, explicit
approval import. Phase 3 (marketplace) and Phase 4 (general internet
acquisition) remain out of scope.
"""

from core.skillgen.budget import ModelCallBudget
from core.skillgen.candidate import Candidate, detect, score_candidate, to_report
from core.skillgen.evolve import apply_feedback, consolidate, evaluate_lifecycle
from core.skillgen.generate import build_manual_skill, generalize
from core.skillgen.judge import (
    Judgment,
    ModelJudge,
    build_judgment_prompt,
    default_judge,
    parse_judgment,
)
from core.skillgen.matcher import match, score_match
from core.skillgen.pipeline import SkillPipeline, quick_observe
from core.skillgen.registry import SkillRegistry, registry_for, similarity
from core.skillgen.types import (
    RETRIEVABLE_STATES,
    Skill,
    SkillScope,
    SkillState,
    scope_visible,
)
from core.skillgen.validate import validate_skill

__all__ = [
    "Candidate",
    "Judgment",
    "ModelCallBudget",
    "ModelJudge",
    "RETRIEVABLE_STATES",
    "Skill",
    "SkillPipeline",
    "SkillRegistry",
    "SkillScope",
    "SkillState",
    "apply_feedback",
    "build_judgment_prompt",
    "build_manual_skill",
    "consolidate",
    "default_judge",
    "detect",
    "evaluate_lifecycle",
    "generalize",
    "match",
    "parse_judgment",
    "quick_observe",
    "registry_for",
    "score_candidate",
    "score_match",
    "similarity",
    "scope_visible",
    "to_report",
    "validate_skill",
]
