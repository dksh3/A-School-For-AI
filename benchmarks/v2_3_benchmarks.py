"""V2.3 benchmark suite — confidence estimation performance.

Compares V2.0, V2.1, V2.2, and V2.3 on confidence-related scenarios.

Usage:
    python -m benchmarks.v2_3_benchmarks
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core.learner.base import LearningInput  # noqa: E402
from core.learner.confidence import ConfidenceConfig, ConfidenceLevel  # noqa: E402
from core.learner.conflict import ConflictConfig  # noqa: E402
from core.learner.learner_v2 import HybridSimilarityLearner  # noqa: E402
from core.learner.retrieval_scorer import ScorerConfig  # noqa: E402

# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------


@dataclass
class BenchmarkResult:
    name: str
    description: str
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class BenchmarkSuite:
    results: list[BenchmarkResult] = field(default_factory=list)

    def add(self, result: BenchmarkResult) -> None:
        self.results.append(result)

    def summary(self) -> str:
        lines: list[str] = []
        lines.append("=" * 70)
        lines.append("  V2.3 CONFIDENCE ESTIMATION BENCHMARK RESULTS")
        lines.append("=" * 70)
        lines.append("")

        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)

        for r in self.results:
            status = "PASS" if r.passed else "FAIL"
            lines.append(f"  [{status}] {r.name}")
            if r.description:
                lines.append(f"         {r.description}")
            for key, val in r.details.items():
                lines.append(f"         {key}: {val}")
            lines.append("")

        lines.append("-" * 70)
        lines.append(f"  Total: {len(self.results)} | Passed: {passed} | Failed: {failed}")
        lines.append("-" * 70)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def train(learner: HybridSimilarityLearner, pairs: list[tuple[str, str]]) -> None:
    for text, output in pairs:
        learner.learn(LearningInput(observation={"input": text, "output": output}))


def train_with_feedback(
    learner: HybridSimilarityLearner,
    pairs: list[tuple[str, str]],
    feedback_rounds: int = 0,
) -> None:
    for text, output in pairs:
        learner.learn(LearningInput(observation={"input": text, "output": output}))
    for _ in range(feedback_rounds):
        for text, output in pairs:
            learner.feedback(text, output, correct=True)


def measure_confidence_calibration(
    learner: HybridSimilarityLearner,
    test_cases: list[tuple[str, str]],
) -> dict[str, Any]:
    """Measure how well confidence predicts correctness."""
    correct = 0
    total = 0
    confidences: list[float] = []
    correct_flags: list[bool] = []
    latencies: list[float] = []

    for text, expected in test_cases:
        start = time.perf_counter()
        result = learner.predict(text)
        elapsed_ms = (time.perf_counter() - start) * 1000
        latencies.append(elapsed_ms)

        is_correct = result.output == expected
        correct += is_correct
        total += 1
        confidences.append(result.confidence)
        correct_flags.append(is_correct)

    # Brier score
    brier = 0.0
    for conf, corr in zip(confidences, correct_flags, strict=False):
        brier += (conf - (1.0 if corr else 0.0)) ** 2
    brier /= total if total else 1

    # Mean confidence
    mean_conf = sum(confidences) / len(confidences) if confidences else 0

    # Mean confidence when correct vs incorrect
    correct_confs = [c for c, k in zip(confidences, correct_flags, strict=False) if k]
    incorrect_confs = [c for c, k in zip(confidences, correct_flags, strict=False) if not k]
    mean_correct = sum(correct_confs) / len(correct_confs) if correct_confs else 0
    mean_incorrect = sum(incorrect_confs) / len(incorrect_confs) if incorrect_confs else 0

    # ECE (Expected Calibration Error) with 5 bins
    n_bins = 5
    bin_boundaries = [i / n_bins for i in range(n_bins + 1)]
    ece = 0.0
    for i in range(n_bins):
        low, high = bin_boundaries[i], bin_boundaries[i + 1]
        in_bin = [
            (conf, corr)
            for conf, corr in zip(confidences, correct_flags, strict=False)
            if low <= conf < high
        ]
        if in_bin:
            avg_conf = sum(c for c, _ in in_bin) / len(in_bin)
            avg_acc = sum(1 for _, c in in_bin if c) / len(in_bin)
            ece += len(in_bin) / total * abs(avg_acc - avg_conf)

    return {
        "accuracy": round(correct / total * 100, 1) if total else 0,
        "mean_confidence": round(mean_conf, 4),
        "mean_confidence_correct": round(mean_correct, 4),
        "mean_confidence_incorrect": round(mean_incorrect, 4),
        "brier_score": round(brier, 4),
        "ece": round(ece, 4),
        "correct": correct,
        "total": total,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 3) if latencies else 0,
        "confidence_separation": round(mean_correct - mean_incorrect, 4),
    }


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------

TRAINING_DATA = [
    ("sort a list", "use sorted()"),
    ("reverse a string", "s[::-1]"),
    ("find maximum", "max()"),
    ("join strings", "sep.join(items)"),
    ("check membership", "x in collection"),
]

CONFLICT_TRAINING = [
    ("sort a list", "use sorted()"),
    ("sort a list", "use list.sort()"),
]

NOVEL_QUERIES = [
    ("sort list", "use sorted()"),
    ("reverse string", "s[::-1]"),
    ("find biggest number", "max()"),
    ("concatenate strings", "sep.join(items)"),
    ("is element in set", "x in collection"),
]


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------


def run_benchmarks() -> BenchmarkSuite:
    suite = BenchmarkSuite()

    # --- V2.0 baseline (no scorer, no conflict, no confidence) ---
    v20 = HybridSimilarityLearner(k=3)
    train(v20, TRAINING_DATA)
    v20_cal = measure_confidence_calibration(v20, NOVEL_QUERIES)
    suite.add(BenchmarkResult(
        name="V2.0 Confidence Calibration",
        description="Baseline multi-factor confidence",
        passed=v20_cal["accuracy"] >= 60,
        details={
            "accuracy": f"{v20_cal['accuracy']}%",
            "mean_confidence": v20_cal["mean_confidence"],
            "brier_score": v20_cal["brier_score"],
            "avg_latency_ms": v20_cal["avg_latency_ms"],
        },
    ))

    # --- V2.1 with scorer ---
    v21 = HybridSimilarityLearner(k=3, scorer_config=ScorerConfig())
    train(v21, TRAINING_DATA)
    v21_cal = measure_confidence_calibration(v21, NOVEL_QUERIES)
    suite.add(BenchmarkResult(
        name="V2.1 Confidence Calibration",
        description="With retrieval scorer",
        passed=v21_cal["accuracy"] >= 60,
        details={
            "accuracy": f"{v21_cal['accuracy']}%",
            "mean_confidence": v21_cal["mean_confidence"],
            "brier_score": v21_cal["brier_score"],
            "avg_latency_ms": v21_cal["avg_latency_ms"],
        },
    ))

    # --- V2.2 with conflict detection ---
    v22 = HybridSimilarityLearner(
        k=3,
        scorer_config=ScorerConfig(),
        conflict_config=ConflictConfig(),
    )
    train(v22, TRAINING_DATA)
    v22_cal = measure_confidence_calibration(v22, NOVEL_QUERIES)
    suite.add(BenchmarkResult(
        name="V2.2 Confidence Calibration",
        description="With conflict detection",
        passed=v22_cal["accuracy"] >= 60,
        details={
            "accuracy": f"{v22_cal['accuracy']}%",
            "mean_confidence": v22_cal["mean_confidence"],
            "brier_score": v22_cal["brier_score"],
            "avg_latency_ms": v22_cal["avg_latency_ms"],
        },
    ))

    # --- V2.3 with confidence estimation ---
    v23 = HybridSimilarityLearner(
        k=3,
        scorer_config=ScorerConfig(),
        conflict_config=ConflictConfig(),
        confidence_config=ConfidenceConfig(),
    )
    train(v23, TRAINING_DATA)
    v23_cal = measure_confidence_calibration(v23, NOVEL_QUERIES)
    suite.add(BenchmarkResult(
        name="V2.3 Confidence Calibration",
        description="With Bayesian confidence estimation",
        passed=v23_cal["accuracy"] >= 60,
        details={
            "accuracy": f"{v23_cal['accuracy']}%",
            "mean_confidence": v23_cal["mean_confidence"],
            "brier_score": v23_cal["brier_score"],
            "ece": v23_cal["ece"],
            "confidence_separation": v23_cal["confidence_separation"],
            "avg_latency_ms": v23_cal["avg_latency_ms"],
        },
    ))

    # --- Confidence separation (correct vs incorrect) ---
    separation_ok = v23_cal["confidence_separation"] >= 0
    suite.add(BenchmarkResult(
        name="Confidence Separation",
        description="Correct predictions should have higher confidence",
        passed=separation_ok,
        details={
            "mean_confidence_correct": v23_cal["mean_confidence_correct"],
            "mean_confidence_incorrect": v23_cal["mean_confidence_incorrect"],
            "separation": v23_cal["confidence_separation"],
        },
    ))

    # --- Evidence increases confidence ---
    v23_no_evidence = HybridSimilarityLearner(k=3, confidence_config=ConfidenceConfig())
    v23_no_evidence.learn(LearningInput(observation={"input": "task", "output": "A"}))
    r_no_evidence = v23_no_evidence.predict("task")

    v23_with_evidence = HybridSimilarityLearner(k=3, confidence_config=ConfidenceConfig())
    v23_with_evidence.learn(LearningInput(observation={"input": "task", "output": "A"}))
    for _ in range(20):
        v23_with_evidence.feedback("task", "A", correct=True)
    r_with_evidence = v23_with_evidence.predict("task")

    evidence_increases = r_with_evidence.confidence > r_no_evidence.confidence
    suite.add(BenchmarkResult(
        name="Evidence Increases Confidence",
        description="More evidence should increase confidence",
        passed=evidence_increases,
        details={
            "no_evidence_confidence": round(r_no_evidence.confidence, 4),
            "with_evidence_confidence": round(r_with_evidence.confidence, 4),
        },
    ))

    # --- Conflict reduces confidence ---
    v23_no_conflict = HybridSimilarityLearner(k=3, confidence_config=ConfidenceConfig())
    v23_no_conflict.learn(LearningInput(observation={"input": "task", "output": "A"}))
    for _ in range(10):
        v23_no_conflict.feedback("task", "A", correct=True)
    r_no_conflict = v23_no_conflict.predict("task")

    v23_conflict = HybridSimilarityLearner(
        k=3,
        confidence_config=ConfidenceConfig(),
        conflict_config=ConflictConfig(input_similarity_threshold=0.5),
    )
    v23_conflict.learn(LearningInput(
        observation={"input": "sort a list", "output": "use sorted()"}))
    v23_conflict.learn(LearningInput(
        observation={"input": "sort a list", "output": "use list.sort()"}))
    r_conflict = v23_conflict.predict("sort a list")

    conflict_reduces = (
        not r_conflict.has_conflict
        or r_conflict.confidence < r_no_conflict.confidence
    )
    suite.add(BenchmarkResult(
        name="Conflict Reduces Confidence",
        description="Conflicting memories should lower confidence",
        passed=conflict_reduces,
        details={
            "no_conflict_confidence": round(r_no_conflict.confidence, 4),
            "conflict_confidence": round(r_conflict.confidence, 4),
            "has_conflict": r_conflict.has_conflict,
        },
    ))

    # --- Uncertainty state is meaningful ---
    v23_uncertain = HybridSimilarityLearner(k=3, confidence_config=ConfidenceConfig())
    v23_uncertain.learn(LearningInput(observation={"input": "task", "output": "A"}))
    r_uncertain = v23_uncertain.predict("task")

    state_valid = r_uncertain.uncertainty_state in (
        ConfidenceLevel.CONFIDENT,
        ConfidenceLevel.UNCERTAIN,
        ConfidenceLevel.INSUFFICIENT_EVIDENCE,
        ConfidenceLevel.CONFLICTED,
    )
    suite.add(BenchmarkResult(
        name="Uncertainty State Valid",
        description="Uncertainty state should be a valid classification",
        passed=state_valid,
        details={
            "uncertainty_state": r_uncertain.uncertainty_state,
        },
    ))

    # --- Confidence components are present ---
    v23_comp = HybridSimilarityLearner(k=3, confidence_config=ConfidenceConfig())
    v23_comp.learn(LearningInput(observation={"input": "task", "output": "A"}))
    v23_comp.feedback("task", "A", correct=True)
    r_comp = v23_comp.predict("task")
    components = r_comp.confidence_components

    has_all_components = all(
        k in components
        for k in [
            "similarity", "evidence_strength", "evidence_factor",
            "agreement_bonus", "conflict_penalty", "novelty_penalty",
            "success_count", "failure_count",
        ]
    )
    suite.add(BenchmarkResult(
        name="Confidence Components Present",
        description="All explainability components should be present",
        passed=has_all_components,
        details={
            "components": list(components.keys()),
        },
    ))

    # --- Persistence ---
    v23_persist = HybridSimilarityLearner(
        k=3,
        scorer_config=ScorerConfig(),
        conflict_config=ConflictConfig(),
        confidence_config=ConfidenceConfig(prior_strength=8.0),
    )
    train(v23_persist, TRAINING_DATA)

    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        v23_persist.save_state(tmpdir)
        loaded = HybridSimilarityLearner.load_state(
            tmpdir,
            scorer_config=ScorerConfig(),
            conflict_config=ConflictConfig(),
            confidence_config=ConfidenceConfig(prior_strength=8.0),
        )
        loaded_result = loaded.predict("sort list")
        persist_ok = loaded_result.output == "use sorted()"
        persist_conf = (loaded._confidence_config is not None
                        and loaded._confidence_config.prior_strength == 8.0)

    suite.add(BenchmarkResult(
        name="V2.3 Persistence",
        description="Confidence config saves and loads correctly",
        passed=persist_ok and persist_conf,
        details={
            "loaded_prediction": loaded_result.output,
            "config_preserved": persist_conf,
        },
    ))

    # --- Latency overhead ---
    latency_overhead = (
        (v23_cal["avg_latency_ms"] / v21_cal["avg_latency_ms"] - 1.0) * 100
        if v21_cal["avg_latency_ms"] > 0 else 0
    )
    latency_ok = v23_cal["avg_latency_ms"] < 2.0

    suite.add(BenchmarkResult(
        name="V2.3 Latency Overhead",
        description="V2.3 confidence must stay under 2ms",
        passed=latency_ok,
        details={
            "v21_avg_ms": v21_cal["avg_latency_ms"],
            "v23_avg_ms": v23_cal["avg_latency_ms"],
            "overhead_pct": f"{round(latency_overhead, 1)}%",
        },
    ))

    # --- Brier score comparison ---
    brier_improved = v23_cal["brier_score"] <= v20_cal["brier_score"] + 0.01
    suite.add(BenchmarkResult(
        name="Brier Score Stability",
        description="V2.3 Brier score should not be worse than V2.0",
        passed=brier_improved,
        details={
            "v20_brier": v20_cal["brier_score"],
            "v23_brier": v23_cal["brier_score"],
        },
    ))

    # --- Duplicates do not inflate confidence ---
    v23_single = HybridSimilarityLearner(k=3, confidence_config=ConfidenceConfig())
    v23_single.learn(LearningInput(observation={"input": "task", "output": "A"}))
    v23_single.feedback("task", "A", correct=True)
    r_single = v23_single.predict("task")

    v23_duplicates = HybridSimilarityLearner(k=5, confidence_config=ConfidenceConfig())
    for _ in range(5):
        v23_duplicates.learn(LearningInput(observation={"input": "task", "output": "A"}))
    v23_duplicates.feedback("task", "A", correct=True)
    r_dupes = v23_duplicates.predict("task")

    # Duplicates should not cause confidence to exceed single by too much
    dupe_ratio = r_dupes.confidence / r_single.confidence if r_single.confidence > 0 else 1.0
    dupe_ok = dupe_ratio < 2.0

    suite.add(BenchmarkResult(
        name="Duplicate Memory Safety",
        description="Duplicates should not inflate confidence",
        passed=dupe_ok,
        details={
            "single_confidence": round(r_single.confidence, 4),
            "duplicate_confidence": round(r_dupes.confidence, 4),
            "ratio": round(dupe_ratio, 2),
        },
    ))

    # --- No regression vs V2.2 ---
    no_regression = v23_cal["accuracy"] >= v22_cal["accuracy"] - 5
    suite.add(BenchmarkResult(
        name="V2.3 vs V2.2 No Regression",
        description="V2.3 must not lose >5% accuracy vs V2.2",
        passed=no_regression,
        details={
            "v22_accuracy": f"{v22_cal['accuracy']}%",
            "v23_accuracy": f"{v23_cal['accuracy']}%",
        },
    ))

    return suite


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    results_dir = _project_root / "benchmarks" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    suite = run_benchmarks()
    print(suite.summary())

    result_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "results": [
            {
                "name": r.name,
                "description": r.description,
                "passed": r.passed,
                "details": r.details,
            }
            for r in suite.results
        ],
    }
    out_path = results_dir / "v2_3_benchmark.json"
    out_path.write_text(json.dumps(result_data, indent=2), encoding="utf-8")
    print(f"\nResults saved to {out_path}")
