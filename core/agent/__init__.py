"""S7: Agent-native tool suite core."""

from core.agent.docfetcher import DocResult, fetch_docs
from core.agent.executor import ExecuteResult, execute
from core.agent.explorer import ExploreResult, explore
from core.agent.goals import GoalResult, goal
from core.agent.navigator import NavigateResult, navigate
from core.agent.observer import ObserveResult, observe
from core.agent.progress import ProgressResult, progress
from core.agent.researcher import ResearchResult, research
from core.agent.sessions import SessionResult, session
from core.agent.workflows import WorkflowResult, register_workflow, workflow

__all__ = [
    "DocResult",
    "ExecuteResult",
    "ExploreResult",
    "GoalResult",
    "NavigateResult",
    "ObserveResult",
    "ProgressResult",
    "ResearchResult",
    "SessionResult",
    "WorkflowResult",
    "execute",
    "explore",
    "fetch_docs",
    "goal",
    "navigate",
    "observe",
    "progress",
    "register_workflow",
    "research",
    "session",
    "workflow",
]
