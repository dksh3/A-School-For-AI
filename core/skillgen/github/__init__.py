"""1A-2Z Phase 2: GitHub skill discovery and safe analysis.

Extends core/skillgen - NOT a parallel system. Flow: capability gap ->
bounded GitHub search -> deterministic candidate filtering -> targeted file
retrieval (never cloning) -> deterministic security classification of
UNTRUSTED content -> model-assisted analysis (budgeted, fail-closed JSON) ->
local duplicate comparison -> EXPLICIT user-approved import into the normal
Phase 1 registry and lifecycle.

Phase 3 (marketplace) and Phase 4 (general internet acquisition) are out of
scope. Nothing is ever executed, installed, or imported automatically.
"""

from core.skillgen.github.analyzer import analyze, parse_analysis
from core.skillgen.github.cache import TTLCache, shared_cache
from core.skillgen.github.candidate import filter_candidates, find_skill_files
from core.skillgen.github.client import GitHubClient, GitHubError, default_client
from core.skillgen.github.comparator import find_local_duplicate, improvement_report
from core.skillgen.github.discovery import (
    analyze_external,
    compare,
    discover,
    import_external,
    search_github,
)
from core.skillgen.github.extractor import build_imported_skill, extract_capability
from core.skillgen.github.importer import import_candidate, license_info, review_preview
from core.skillgen.github.models import (
    DiscoveryResult,
    ExternalAnalysis,
    GitHubCandidate,
    RepoMeta,
    SecurityLevel,
    SkillFile,
    TrustState,
)
from core.skillgen.github.search import generate_queries
from core.skillgen.github.security import classify_content, effective_level

__all__ = [
    "DiscoveryResult",
    "ExternalAnalysis",
    "GitHubCandidate",
    "GitHubClient",
    "GitHubError",
    "RepoMeta",
    "SecurityLevel",
    "SkillFile",
    "TTLCache",
    "TrustState",
    "analyze",
    "analyze_external",
    "build_imported_skill",
    "classify_content",
    "compare",
    "default_client",
    "discover",
    "effective_level",
    "extract_capability",
    "filter_candidates",
    "find_local_duplicate",
    "find_skill_files",
    "generate_queries",
    "improvement_report",
    "import_candidate",
    "import_external",
    "license_info",
    "parse_analysis",
    "review_preview",
    "search_github",
    "shared_cache",
]
