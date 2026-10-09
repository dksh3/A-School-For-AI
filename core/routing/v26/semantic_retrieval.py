"""Semantic retrieval scoring for V2.6 memory entries.

Provides blended TF-IDF + optional semantic similarity ranking for
MemoryEntry retrieval. Replaces substring matching with principled
similarity computation.

Design principles:
- Similarity is ALWAYS the primary signal
- No fake embeddings — use existing FeatureExtractor and SemanticEncoder
- Graceful degradation when semantic encoder is unavailable
- Deterministic and bounded cost
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.learner.feature_extractor import FeatureExtractor
from core.learner.similarity import cosine_similarity
from core.routing.v26.identity import coerce_float, coerce_int, coerce_text

if TYPE_CHECKING:
    from core.learner.semantic_encoder import SemanticEncoder
    from core.routing.v26.memory_types import MemoryEntry


def scored_query(
    entries: list[MemoryEntry],
    query: str,
    extractor: FeatureExtractor,
    encoder: SemanticEncoder | None = None,
    limit: int = 10,
    lexical_weight: float = 0.4,
    semantic_weight: float = 0.6,
) -> list[MemoryEntry]:
    """Score and rank memory entries by similarity to query.

    Uses blended TF-IDF cosine similarity. When a semantic encoder is
    available, blends lexical and semantic similarity.

    Fail-open: hostile entries, queries, limits, or weights degrade
    gracefully (offending entries are skipped, limits are clamped)
    instead of raising.

    Args:
        entries: Candidate memory entries to score.
        query: The search query text.
        extractor: TF-IDF feature extractor (for IDF weighting).
        encoder: Optional semantic encoder for dense similarity.
        limit: Maximum results to return.
        lexical_weight: Weight for TF-IDF similarity.
        semantic_weight: Weight for semantic similarity.

    Returns:
        List of MemoryEntry sorted by relevance descending, limited.
    """
    try:
        return _scored_query_impl(
            entries,
            query,
            extractor,
            encoder=encoder,
            limit=limit,
            lexical_weight=lexical_weight,
            semantic_weight=semantic_weight,
        )
    except Exception:  # noqa: BLE001 - fail-open: hostile input never breaks retrieval
        return []


def _scored_query_impl(
    entries: list[MemoryEntry],
    query: str,
    extractor: FeatureExtractor,
    encoder: SemanticEncoder | None = None,
    limit: int = 10,
    lexical_weight: float = 0.4,
    semantic_weight: float = 0.6,
) -> list[MemoryEntry]:
    """Inner scoring routine; may raise on hostile input (caught by caller)."""
    query_text = query if isinstance(query, str) else coerce_text(query)
    if not query_text or not entries:
        return []

    # Normalize weights (non-finite/non-numeric degrade to lexical-only)
    lexical_weight = coerce_float(lexical_weight, 0.4)
    semantic_weight = coerce_float(semantic_weight, 0.6)
    total_weight = lexical_weight + semantic_weight
    if total_weight > 0:
        lex_w = lexical_weight / total_weight
        sem_w = semantic_weight / total_weight
    else:
        lex_w = 1.0
        sem_w = 0.0

    safe_limit = max(0, coerce_int(limit, 10))

    # Extract query features
    try:
        query_vec = extractor.transform(query_text)
    except Exception:  # noqa: BLE001 - hostile text must not break retrieval
        return []

    # Encode query semantic vector if encoder available
    query_semantic: list[float] | None = None
    if encoder is not None:
        try:
            query_semantic = encoder.encode_single(query_text)
        except Exception:  # noqa: BLE001
            query_semantic = None

    # Score each entry
    scored: list[tuple[float, MemoryEntry]] = []
    for entry in entries:
        try:
            # Lexical similarity (TF-IDF cosine with IDF weighting)
            entry_vec = extractor.transform(entry.content)
            lex_sim = cosine_similarity(query_vec, entry_vec, extractor)

            # Semantic similarity (dense cosine if available)
            sem_sim = 0.0
            if query_semantic is not None and encoder is not None:
                try:
                    entry_sem = entry.metadata.get("_semantic_vector")
                    if (
                        entry_sem is not None
                        and isinstance(entry_sem, list)
                        and len(entry_sem) == len(query_semantic)
                    ):
                        from core.learner.semantic_encoder import dense_cosine_similarity
                        sem_sim = dense_cosine_similarity(query_semantic, entry_sem)
                except Exception:  # noqa: BLE001
                    sem_sim = 0.0

            blended = lex_w * lex_sim + sem_w * sem_sim
            scored.append((blended, entry))
        except Exception:  # noqa: BLE001 - skip unreadable entries, keep ranking
            continue

    # Sort by score descending (NaN-safe: comparable values only)
    scored.sort(key=lambda x: x[0], reverse=True)

    return [entry for _, entry in scored[:safe_limit]]
