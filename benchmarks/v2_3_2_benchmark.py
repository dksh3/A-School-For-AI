"""V2.3.2 comprehensive calibration benchmark.

Runs all calibration scenarios, compares V2.3 vs V2.3.2, produces detailed report.
"""

from __future__ import annotations

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core.learner.base import LearningInput
from core.learner.calibration.calibrator import (
    CalibrationMap,
    build_calibration_map,
    calibrate,
)
from core.learner.calibration.dataset import build_all_scenarios, run_scenario
from core.learner.calibration.estimator import (
    estimate_confidence_v232,
)
from core.learner.calibration.metrics import (
    CalibrationCase,
    brier_score,
    compute_full_report,
)
from core.learner.confidence import ConfidenceConfig
from core.learner.conflict import ConflictConfig
from core.learner.learner_v2 import HybridSimilarityLearner
from core.learner.retrieval_scorer import ScorerConfig


def v23_factory():
    """Create a V2.3 learner (existing formula)."""
    return HybridSimilarityLearner(
        k=5,
        lexical_weight=1.0,
        semantic_weight=0.0,
        scorer_config=ScorerConfig(),
        conflict_config=ConflictConfig(),
        confidence_config=ConfidenceConfig(),
    )


def v232_factory():
    """Create a V2.3.2 learner (new formula)."""
    return HybridSimilarityLearner(
        k=5,
        lexical_weight=1.0,
        semantic_weight=0.0,
        scorer_config=ScorerConfig(),
        conflict_config=ConflictConfig(),
        confidence_config=ConfidenceConfig(),
    )


def run_v23_scenario(scenario) -> list[CalibrationCase]:
    """Run scenario with V2.3 estimator."""
    return run_scenario(scenario, v23_factory)


def run_v232_raw_scenario(scenario) -> list[CalibrationCase]:
    """Run scenario with V2.3.2 estimator (no calibration layer)."""
    learner = v232_factory()
    for inp, out in scenario.training.examples:
        learner.learn(LearningInput(observation={"input": inp, "output": out}))
    for inp, out, correct in scenario.training.feedback:
        learner.feedback(inp, out, correct)

    results = []
    for case in scenario.test_cases:
        r = learner.predict(case.query)
        # Use V2.3.2 estimator directly
        v232_result = estimate_confidence_v232(
            similarity=r.similarity,
            success_count=r.confidence_components.get("success_count", 0),
            failure_count=r.confidence_components.get("failure_count", 0),
            supporting_weight=r.confidence_components.get("supporting_count", 0) * 1.0,
            total_weight=r.confidence_components.get("total_count", 0) * 1.0,
            supporting_count=r.confidence_components.get("supporting_count", 0),
            total_count=r.confidence_components.get("total_count", 0),
            outputs=[r.prediction.similarities[i][0] if i < len(r.prediction.similarities) else ""
                     for i in range(len(r.prediction.similarities))],
            output_similarities=[s for _, s in r.prediction.similarities],
        )
        results.append(CalibrationCase(
            query=case.query,
            expected=case.expected,
            confidence=v232_result.confidence,
            predicted=r.output,
            correct=r.output == case.expected,
            metadata={
                "similarity": r.similarity,
                "uncertainty_state": r.uncertainty_state,
                "scenario": scenario.name,
                "raw_confidence": v232_result.raw_confidence,
            },
        ))
    return results


def run_v232_calibrated_scenario(scenario, cal_map) -> list[CalibrationCase]:
    """Run scenario with V2.3.2 + calibration layer."""
    learner = v232_factory()
    for inp, out in scenario.training.examples:
        learner.learn(LearningInput(observation={"input": inp, "output": out}))
    for inp, out, correct in scenario.training.feedback:
        learner.feedback(inp, out, correct)

    results = []
    for case in scenario.test_cases:
        r = learner.predict(case.query)
        v232_result = estimate_confidence_v232(
            similarity=r.similarity,
            success_count=r.confidence_components.get("success_count", 0),
            failure_count=r.confidence_components.get("failure_count", 0),
            supporting_weight=r.confidence_components.get("supporting_count", 0) * 1.0,
            total_weight=r.confidence_components.get("total_count", 0) * 1.0,
            supporting_count=r.confidence_components.get("supporting_count", 0),
            total_count=r.confidence_components.get("total_count", 0),
            outputs=[r.prediction.similarities[i][0] if i < len(r.prediction.similarities) else ""
                     for i in range(len(r.prediction.similarities))],
            output_similarities=[s for _, s in r.prediction.similarities],
        )
        calibrated_conf = calibrate(v232_result.confidence, cal_map)
        results.append(CalibrationCase(
            query=case.query,
            expected=case.expected,
            confidence=calibrated_conf,
            predicted=r.output,
            correct=r.output == case.expected,
            metadata={
                "similarity": r.similarity,
                "uncertainty_state": r.uncertainty_state,
                "scenario": scenario.name,
                "raw_confidence": v232_result.raw_confidence,
                "calibrated": True,
            },
        ))
    return results


def print_report(label: str, cases: list[CalibrationCase]):
    """Print a calibration report."""
    report = compute_full_report(cases)
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  Cases: {report.n_cases} (correct={report.n_correct}, incorrect={report.n_incorrect})")
    print(f"  Accuracy: {report.accuracy:.1%}")
    print(f"  Mean confidence: {report.mean_confidence:.4f}")
    print(f"  Brier score: {report.brier:.4f}")
    print(f"  ECE: {report.ece:.4f}")
    print(f"  Discrimination gap: {report.discrimination_gap:.4f}")
    print(f"  Abstention quality: {report.abstention_quality:.4f}")

    print("\n  Selective prediction:")
    for thresh, acc in sorted(report.selective_accuracy.items()):
        cov = sum(1 for c in cases if c.confidence >= thresh) / len(cases) if cases else 0
        print(f"    conf>={thresh:.1f}: accuracy={acc:.1%}, coverage={cov:.1%}")

    print("\n  Reliability curve:")
    print(f"    {'Bin':>10s} | {'Count':>5s} | {'Mean Conf':>10s} | {'Accuracy':>8s} | {'Gap':>6s}")
    for bucket in report.reliability:
        if bucket.count > 0:
            print(f"    {bucket.bin_low:.1f}-{bucket.bin_high:.1f} | {bucket.count:5d} | "
                  f"{bucket.mean_confidence:10.4f} | {bucket.accuracy:8.4f} | "
                  f"{bucket.gap:6.4f}")


def main():
    print("V2.3.2 Calibration Benchmark")
    print("="*60)

    scenarios = build_all_scenarios()
    print(f"Scenarios: {len(scenarios)}")

    # Collect all cases
    v23_all = []
    v232_all = []
    v232_cal_all = []

    for scenario in scenarios:
        print(f"\n--- {scenario.name} ({scenario.category}): {scenario.description} ---")

        v23_cases = run_v23_scenario(scenario)
        v232_cases = run_v232_raw_scenario(scenario)
        v232_cal_cases = run_v232_calibrated_scenario(
            scenario, CalibrationMap(buckets=[], fallback_mode=True))
        v23_all.extend(v23_cases)
        v232_all.extend(v232_cases)
        v232_cal_all.extend(v232_cal_cases)

        v23_brier = brier_score(v23_cases)
        v232_brier = brier_score(v232_cases)
        print(f"  V2.3 Brier: {v23_brier:.4f} | V2.3.2 Brier: {v232_brier:.4f} | "
              f"Delta: {v232_brier-v23_brier:+.4f}")

    # Overall reports
    print_report("V2.3 (existing formula)", v23_all)
    print_report("V2.3.2 (new formula, no calibration)", v232_all)

    # Build calibration map from V2.3.2 raw results
    raw_confs = [c.metadata.get("raw_confidence", c.confidence) for c in v232_all]
    correctness = [c.correct for c in v232_all]
    cal_map = build_calibration_map(raw_confs, correctness, n_bins=10, min_samples_per_bin=2)
    print(f"\nCalibration map: {len(cal_map.buckets)} buckets, fallback={cal_map.fallback_mode}")

    # Re-run with calibration
    v232_cal_all = []
    for scenario in scenarios:
        cases = run_v232_calibrated_scenario(scenario, cal_map)
        v232_cal_all.extend(cases)

    print_report("V2.3.2 (new formula + calibration)", v232_cal_all)

    # Version comparison
    print(f"\n{'='*60}")
    print("  VERSION COMPARISON")
    print(f"{'='*60}")
    for label, cases in [("V2.3", v23_all), ("V2.3.2 raw", v232_all),
                         ("V2.3.2 calibrated", v232_cal_all)]:
        r = compute_full_report(cases)
        print(f"  {label:25s}: Brier={r.brier:.4f}, ECE={r.ece:.4f}, "
              f"mean_conf={r.mean_confidence:.4f}, discrim={r.discrimination_gap:.4f}, "
              f"abstain={r.abstention_quality:.4f}")


if __name__ == "__main__":
    main()
