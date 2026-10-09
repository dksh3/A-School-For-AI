"""V2.3.2 small-dataset benchmark — matches V2.3.1 conditions.

This is the REAL challenge: 5-10 training examples, k=3, low similarity.
This is where V2.3 showed Brier=0.619, ECE=0.696.
"""

from __future__ import annotations

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core.learner.base import LearningInput
from core.learner.calibration.calibrator import (
    build_calibration_map,
    calibrate,
)
from core.learner.calibration.estimator import estimate_confidence_v232
from core.learner.calibration.metrics import (
    CalibrationCase,
    compute_full_report,
)
from core.learner.confidence import ConfidenceConfig
from core.learner.conflict import ConflictConfig
from core.learner.learner_v2 import HybridSimilarityLearner
from core.learner.retrieval_scorer import ScorerConfig


def build_small_dataset():
    """Build a dataset matching V2.3.1 conditions: 5-10 training examples."""
    training = [
        ("sort a list", "sorted(x)"),
        ("reverse a string", "s[::-1]"),
        ("find maximum", "max(x)"),
        ("join strings", "+".join),
        ("check membership", "x in y"),
    ]
    feedback = [
        ("sort a list", "sorted(x)", True),
        ("sort a list", "sorted(x)", True),
        ("sort a list", "sorted(x)", True),
        ("reverse a string", "s[::-1]", True),
        ("reverse a string", "s[::-1]", True),
        ("find maximum", "max(x)", True),
    ]
    return training, feedback


def run_small_benchmark():
    """Run benchmark with small dataset (V2.3.1 conditions)."""
    print("V2.3.2 Small-Dataset Benchmark (V2.3.1 conditions)")
    print("="*60)

    training, feedback = build_small_dataset()
    print(f"Training: {len(training)} examples, Feedback: {len(feedback)} entries")

    test_cases = [
        # Known queries
        ("sort a list", "sorted(x)"),
        ("reverse a string", "s[::-1]"),
        ("find maximum", "max(x)"),
        ("join strings", "+".join),
        ("check membership", "x in y"),
        # Similar but not identical
        ("sort items", "sorted(x)"),
        ("reverse text", "s[::-1]"),
        ("find biggest", "max(x)"),
        # Novel
        ("parse JSON", "json.loads(x)"),
        ("read file", "f.read()"),
    ]

    # --- V2.3 ---
    print("\n--- V2.3 ---")
    v23_learner = HybridSimilarityLearner(
        k=3, lexical_weight=1.0, semantic_weight=0.0,
        scorer_config=ScorerConfig(), conflict_config=ConflictConfig(),
        confidence_config=ConfidenceConfig(),
    )
    for inp, out in training:
        v23_learner.learn(LearningInput(observation={"input": inp, "output": out}))
    for inp, out, correct in feedback:
        v23_learner.feedback(inp, out, correct)

    v23_cases = []
    for query, expected in test_cases:
        r = v23_learner.predict(query)
        v23_cases.append(CalibrationCase(
            query=query, expected=expected, confidence=r.confidence,
            predicted=r.output, correct=r.output == expected,
            metadata={"similarity": r.similarity},
        ))
    v23_report = compute_full_report(v23_cases)
    print(f"  Brier: {v23_report.brier:.4f}")
    print(f"  ECE: {v23_report.ece:.4f}")
    print(f"  Mean confidence: {v23_report.mean_confidence:.4f}")
    print(f"  Discrimination: {v23_report.discrimination_gap:.4f}")
    for c in v23_cases:
        print(f"    conf={c.confidence:.4f} sim={c.metadata.get('similarity',0):.4f} "
              f"{'CORRECT' if c.correct else 'WRONG':7s} '{c.query}' -> '{c.predicted}'")

    # --- V2.3.2 ---
    print("\n--- V2.3.2 ---")
    v232_learner = HybridSimilarityLearner(
        k=3, lexical_weight=1.0, semantic_weight=0.0,
        scorer_config=ScorerConfig(), conflict_config=ConflictConfig(),
        confidence_config=ConfidenceConfig(),
    )
    for inp, out in training:
        v232_learner.learn(LearningInput(observation={"input": inp, "output": out}))
    for inp, out, correct in feedback:
        v232_learner.feedback(inp, out, correct)

    v232_cases = []
    raw_confs = []
    for query, expected in test_cases:
        r = v232_learner.predict(query)
        v232_result = estimate_confidence_v232(
            similarity=r.similarity,
            success_count=r.confidence_components.get("success_count", 0),
            failure_count=r.confidence_components.get("failure_count", 0),
            supporting_weight=r.confidence_components.get("supporting_count", 0) * 1.0,
            total_weight=r.confidence_components.get("total_count", 0) * 1.0,
            supporting_count=r.confidence_components.get("supporting_count", 0),
            total_count=r.confidence_components.get("total_count", 0),
            outputs=[s[0] for s in r.prediction.similarities] if r.prediction.similarities else [],
            output_similarities=([s for _, s in r.prediction.similarities]
                                 if r.prediction.similarities else []),
        )
        raw_confs.append(v232_result.confidence)
        v232_cases.append(CalibrationCase(
            query=query, expected=expected, confidence=v232_result.confidence,
            predicted=r.output, correct=r.output == expected,
            metadata={"similarity": r.similarity, "raw": v232_result.raw_confidence},
        ))
    v232_report = compute_full_report(v232_cases)
    print(f"  Brier: {v232_report.brier:.4f}")
    print(f"  ECE: {v232_report.ece:.4f}")
    print(f"  Mean confidence: {v232_report.mean_confidence:.4f}")
    print(f"  Discrimination: {v232_report.discrimination_gap:.4f}")
    for c in v232_cases:
        print(f"    conf={c.confidence:.4f} sim={c.metadata.get('similarity',0):.4f} "
              f"{'CORRECT' if c.correct else 'WRONG':7s} '{c.query}' -> '{c.predicted}'")

    # --- V2.3.2 + calibration ---
    print("\n--- V2.3.2 + calibration ---")
    correctness = [c.correct for c in v232_cases]
    cal_map = build_calibration_map(raw_confs, correctness, n_bins=5, min_samples_per_bin=2)
    print(f"  Calibration buckets: {len(cal_map.buckets)}")
    for b in cal_map.buckets:
        print(f"    [{b.raw_low:.3f}, {b.raw_high:.3f}] -> {b.calibrated:.3f} (n={b.count})")

    v232_cal_cases = []
    for case in v232_cases:
        cal_conf = calibrate(case.confidence, cal_map)
        v232_cal_cases.append(CalibrationCase(
            query=case.query, expected=case.expected, confidence=cal_conf,
            predicted=case.predicted, correct=case.correct,
            metadata={**case.metadata, "calibrated": True},
        ))
    v232_cal_report = compute_full_report(v232_cal_cases)
    print(f"  Brier: {v232_cal_report.brier:.4f}")
    print(f"  ECE: {v232_cal_report.ece:.4f}")
    print(f"  Mean confidence: {v232_cal_report.mean_confidence:.4f}")

    # --- Summary ---
    print(f"\n{'='*60}")
    print("  SUMMARY (small dataset, V2.3.1 conditions)")
    print(f"{'='*60}")
    for label, r in [("V2.3", v23_report), ("V2.3.2", v232_report),
                     ("V2.3.2+cal", v232_cal_report)]:
        print(f"  {label:15s}: Brier={r.brier:.4f} ECE={r.ece:.4f} "
              f"mean_conf={r.mean_confidence:.4f}")


if __name__ == "__main__":
    run_small_benchmark()
