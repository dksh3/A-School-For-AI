"""V2.3.2 adversarial testing — designed to fool confidence."""

from __future__ import annotations

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core.learner.base import LearningInput
from core.learner.calibration.estimator import estimate_confidence_v232
from core.learner.confidence import ConfidenceConfig
from core.learner.conflict import ConflictConfig
from core.learner.learner_v2 import HybridSimilarityLearner
from core.learner.retrieval_scorer import ScorerConfig


def _get_v232_confidence(learner, query):
    """Get V2.3.2 confidence from a learner prediction."""
    r = learner.predict(query)
    examples = learner._memory.get_all_hybrid()
    query_vector = learner._extractor.transform(query)

    # Compute raw blended similarities for all examples
    raw_sims = [(i, learner._blended_similarity(query_vector, None, ex))
                for i, ex in enumerate(examples)]
    # Sort by raw similarity descending, take top-k
    raw_sims.sort(key=lambda x: x[1], reverse=True)
    top_k = raw_sims[:learner._k]

    outputs = [examples[idx].output for idx, _ in top_k]
    blends = [sim for _, sim in top_k]

    # Vote weights = raw similarity (not retrieval-score-weighted)
    votes = {}
    for idx, raw_sim in top_k:
        example = examples[idx]
        votes[example.output] = votes.get(example.output, 0.0) + raw_sim
    total_weight = sum(votes.values())
    winner = max(votes, key=votes.get) if votes else ""
    winner_weight = votes.get(winner, 0.0)
    n_support = sum(1 for idx, _ in top_k if examples[idx].output == winner)

    v232 = estimate_confidence_v232(
        similarity=r.similarity,
        success_count=r.confidence_components.get("success_count", 0),
        failure_count=r.confidence_components.get("failure_count", 0),
        supporting_weight=winner_weight,
        total_weight=total_weight,
        supporting_count=n_support,
        total_count=len(top_k),
        outputs=outputs,
        output_similarities=blends,
    )
    return v232, r


def test_similarity_trap():
    """Highly similar memory is wrong."""
    print("1. SIMILARITY TRAP: Highly similar memory is wrong")
    learner = HybridSimilarityLearner(
        k=3, lexical_weight=1.0, semantic_weight=0.0,
        scorer_config=ScorerConfig(), conflict_config=ConflictConfig(),
        confidence_config=ConfidenceConfig(),
    )
    learner.learn(LearningInput(observation={"input": "sort a list", "output": "bubble_sort(x)"}))
    learner.learn(LearningInput(observation={"input": "reverse a string", "output": "s[::-1]"}))
    learner.learn(LearningInput(observation={"input": "find maximum", "output": "max(x)"}))

    v232, r = _get_v232_confidence(learner, "sort a list")
    print(f"  Query: 'sort a list' -> '{r.output}' (wrong!)")
    print(f"  Confidence: {v232.confidence:.4f} (should be LOW for wrong prediction)")
    print(f"  Similarity: {r.similarity:.4f}")
    return v232.confidence


def test_majority_trap():
    """Many duplicate wrong memories overwhelm one correct memory."""
    print("\n2. MAJORITY TRAP: Many wrong memories vs one correct")
    learner = HybridSimilarityLearner(
        k=5, lexical_weight=1.0, semantic_weight=0.0,
        scorer_config=ScorerConfig(), conflict_config=ConflictConfig(),
        confidence_config=ConfidenceConfig(),
    )
    for _ in range(4):
        learner.learn(LearningInput(
            observation={"input": "sort a list", "output": "bubble_sort(x)"}))
    learner.learn(LearningInput(observation={"input": "sort a list", "output": "sorted(x)"}))

    v232, r = _get_v232_confidence(learner, "sort a list")
    print(f"  Predicted: '{r.output}' (4 wrong vs 1 correct)")
    print(f"  Confidence: {v232.confidence:.4f}")
    return v232.confidence


def test_evidence_count_trap():
    """Many low-quality memories must not equal one extremely strong memory."""
    print("\n3. EVIDENCE COUNT TRAP: Many weak vs one strong")
    learner = HybridSimilarityLearner(
        k=5, lexical_weight=1.0, semantic_weight=0.0,
        scorer_config=ScorerConfig(), conflict_config=ConflictConfig(),
        confidence_config=ConfidenceConfig(),
    )
    for i in range(4):
        learner.learn(LearningInput(observation={"input": f"task_{i}", "output": "wrong"}))
    learner.learn(LearningInput(observation={"input": "sort a list", "output": "sorted(x)"}))
    for _ in range(20):
        learner.feedback("sort a list", "sorted(x)", correct=True)

    v232, r = _get_v232_confidence(learner, "sort a list")
    print("  Strong memory with 20 correct uses")
    print(f"  Confidence: {v232.confidence:.4f} (should be HIGH)")
    return v232.confidence


def test_feedback_poisoning():
    """Repeated incorrect feedback attempts to inflate confidence."""
    print("\n4. FEEDBACK POISONING: Repeated incorrect feedback")
    learner = HybridSimilarityLearner(
        k=3, lexical_weight=1.0, semantic_weight=0.0,
        scorer_config=ScorerConfig(), conflict_config=ConflictConfig(),
        confidence_config=ConfidenceConfig(),
    )
    learner.learn(LearningInput(observation={"input": "sort a list", "output": "sorted(x)"}))
    for _ in range(5):
        learner.feedback("sort a list", "sorted(x)", correct=True)
    for _ in range(10):
        learner.feedback("sort a list", "sorted(x)", correct=False)

    v232, r = _get_v232_confidence(learner, "sort a list")
    print("  5 correct, 10 incorrect feedback")
    print(f"  Confidence: {v232.confidence:.4f} (should be LOW after poisoning)")
    return v232.confidence


def test_novelty_trap():
    """Query looks lexically familiar but is semantically unrelated."""
    print("\n5. NOVELTY TRAP: Lexically similar but unrelated")
    learner = HybridSimilarityLearner(
        k=3, lexical_weight=1.0, semantic_weight=0.0,
        scorer_config=ScorerConfig(), conflict_config=ConflictConfig(),
        confidence_config=ConfidenceConfig(),
    )
    learner.learn(LearningInput(observation={"input": "sort a list", "output": "sorted(x)"}))
    learner.learn(LearningInput(observation={"input": "reverse a string", "output": "s[::-1]"}))
    learner.learn(LearningInput(observation={"input": "find maximum", "output": "max(x)"}))

    v232, r = _get_v232_confidence(learner, "sort of interesting")
    print("  Query: 'sort of interesting' (lexically similar to 'sort a list')")
    print(f"  Confidence: {v232.confidence:.4f} (should be LOW for unrelated)")
    return v232.confidence


def test_conflict_trap():
    """Two highly credible memories disagree."""
    print("\n6. CONFLICT TRAP: Two credible memories disagree")
    learner = HybridSimilarityLearner(
        k=3, lexical_weight=1.0, semantic_weight=0.0,
        scorer_config=ScorerConfig(), conflict_config=ConflictConfig(),
        confidence_config=ConfidenceConfig(),
    )
    learner.learn(LearningInput(observation={"input": "sort a list", "output": "sorted(x)"}))
    learner.learn(LearningInput(observation={"input": "sort a list", "output": "list.sort()"}))
    for _ in range(10):
        learner.feedback("sort a list", "sorted(x)", correct=True)
    for _ in range(10):
        learner.feedback("sort a list", "list.sort()", correct=True)

    v232, r = _get_v232_confidence(learner, "sort a list")
    print("  Two credible answers: 'sorted(x)' vs 'list.sort()'")
    print(f"  Confidence: {v232.confidence:.4f} (should be LOW due to conflict)")
    return v232.confidence


def test_calibration_manipulation():
    """Try to construct cases that artificially push confidence toward 1.0."""
    print("\n7. CALIBRATION MANIPULATION: Many duplicates")
    learner = HybridSimilarityLearner(
        k=5, lexical_weight=1.0, semantic_weight=0.0,
        scorer_config=ScorerConfig(), conflict_config=ConflictConfig(),
        confidence_config=ConfidenceConfig(),
    )
    for _ in range(10):
        learner.learn(LearningInput(observation={"input": "sort a list", "output": "sorted(x)"}))
    for _ in range(5):
        learner.feedback("sort a list", "sorted(x)", correct=True)

    v232, r = _get_v232_confidence(learner, "sort a list")
    print("  10 identical memories, 5 correct feedbacks")
    print(f"  Confidence: {v232.confidence:.4f}")
    return v232.confidence


def main():
    print("V2.3.2 ADVERSARIAL TESTING")
    print("="*60)

    results = {}
    results["similarity_trap"] = ("low", test_similarity_trap())
    results["majority_trap"] = ("low", test_majority_trap())
    results["evidence_count_trap"] = ("high", test_evidence_count_trap())
    results["feedback_poisoning"] = ("low", test_feedback_poisoning())
    results["novelty_trap"] = ("low", test_novelty_trap())
    results["conflict_trap"] = ("low", test_conflict_trap())
    results["calibration_manipulation"] = ("high", test_calibration_manipulation())

    print(f"\n{'='*60}")
    print("  ADVERSARIAL RESULTS SUMMARY")
    print(f"{'='*60}")
    for name, (expect, conf) in results.items():
        if expect == "low":
            status = "PASS" if conf < 0.7 else "FAIL"
        else:
            status = "PASS" if conf > 0.5 else "FAIL"
        print(f"  {name:30s}: conf={conf:.4f} expect={expect:4s} [{status}]")


if __name__ == "__main__":
    main()
