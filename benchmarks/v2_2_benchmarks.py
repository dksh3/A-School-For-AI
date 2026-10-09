"""V2.2 benchmark suite — conflict detection and resolution performance.

Compares V2.0, V2.1, and V2.2 on conflict-related scenarios.

Usage:
    python -m benchmarks.v2_2_benchmarks
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
        lines.append("  V2.2 CONFLICT DETECTION BENCHMARK RESULTS")
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


def measure_accuracy(
    learner: HybridSimilarityLearner, pairs: list[tuple[str, str]],
) -> dict[str, Any]:
    correct = 0
    latencies: list[float] = []
    for text, expected in pairs:
        start = time.perf_counter()
        result = learner.predict(text)
        elapsed_ms = (time.perf_counter() - start) * 1000
        latencies.append(elapsed_ms)
        if result.output == expected:
            correct += 1
    total = len(pairs)
    return {
        "accuracy": round(correct / total * 100, 1) if total else 0,
        "correct": correct,
        "total": total,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 3) if latencies else 0,
    }


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------

NO_CONFLICT = [
    ("sort a list", "use sorted()"),
    ("reverse a string", "s[::-1]"),
    ("find maximum", "max()"),
    ("join strings", "sep.join(items)"),
    ("check membership", "x in collection"),
]

CONFLICT_EXACT = [
    ("sort a list", "use sorted()"),
    ("sort a list", "use list.sort()"),
]

CONTEXT_DEPENDENT = [
    ("open file Python 3.10", "open(path)"),
    ("open file Python 3.12", "open(path, encoding='utf-8')"),
]

NO_CONFLICT_QUERIES = [
    ("sort list", "use sorted()"),
    ("reverse string", "s[::-1]"),
    ("find biggest", "max()"),
]

CONFLICT_QUERIES = [
    "sort a list",
]

CONTEXT_QUERIES = [
    ("open file Python 3.10", "open(path)"),
    ("open file Python 3.12", "open(path, encoding='utf-8')"),
]


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------


def run_benchmarks() -> BenchmarkSuite:
    suite = BenchmarkSuite()

    # --- V2.0 baseline (no scorer, no conflict) ---
    v20 = HybridSimilarityLearner(k=3)
    train(v20, NO_CONFLICT)
    v20_results = measure_accuracy(v20, NO_CONFLICT_QUERIES)
    suite.add(BenchmarkResult(
        name="V2.0 No-Conflict Retrieval",
        description="Baseline accuracy without conflict detection",
        passed=v20_results["accuracy"] >= 60,
        details={
            "accuracy": f"{v20_results['accuracy']}%",
            "avg_latency_ms": v20_results["avg_latency_ms"],
        },
    ))

    # --- V2.1 with scorer (no conflict) ---
    v21 = HybridSimilarityLearner(k=3, scorer_config=ScorerConfig())
    train(v21, NO_CONFLICT)
    v21_results = measure_accuracy(v21, NO_CONFLICT_QUERIES)
    suite.add(BenchmarkResult(
        name="V2.1 No-Conflict Retrieval",
        description="With scorer but no conflict detection",
        passed=v21_results["accuracy"] >= 60,
        details={
            "accuracy": f"{v21_results['accuracy']}%",
            "avg_latency_ms": v21_results["avg_latency_ms"],
        },
    ))

    # --- V2.2 with conflict detection (no conflict) ---
    v22 = HybridSimilarityLearner(
        k=3,
        scorer_config=ScorerConfig(),
        conflict_config=ConflictConfig(),
    )
    train(v22, NO_CONFLICT)
    v22_results = measure_accuracy(v22, NO_CONFLICT_QUERIES)
    suite.add(BenchmarkResult(
        name="V2.2 No-Conflict Retrieval",
        description="With conflict detection, no actual conflicts",
        passed=v22_results["accuracy"] >= 60,
        details={
            "accuracy": f"{v22_results['accuracy']}%",
            "avg_latency_ms": v22_results["avg_latency_ms"],
        },
    ))

    # --- V2.2 no regression vs V2.1 ---
    no_regression = v22_results["accuracy"] >= v21_results["accuracy"] - 5
    suite.add(BenchmarkResult(
        name="V2.2 vs V2.1 No Regression",
        description="V2.2 must not lose >5% accuracy vs V2.1",
        passed=no_regression,
        details={
            "v21_accuracy": f"{v21_results['accuracy']}%",
            "v22_accuracy": f"{v22_results['accuracy']}%",
        },
    ))

    # --- Conflict detection: exact contradictions ---
    v22_conflict = HybridSimilarityLearner(
        k=3,
        conflict_config=ConflictConfig(input_similarity_threshold=0.5),
    )
    train(v22_conflict, CONFLICT_EXACT)
    conflict_detected = 0
    total_queries = 0
    for query in CONFLICT_QUERIES:
        result = v22_conflict.predict(query)
        total_queries += 1
        if result.has_conflict:
            conflict_detected += 1

    detection_rate = conflict_detected / total_queries if total_queries else 0
    suite.add(BenchmarkResult(
        name="Conflict Detection: Exact Contradictions",
        description="Detect conflicts when same input has different outputs",
        passed=detection_rate > 0,
        details={
            "detection_rate": f"{detection_rate * 100:.0f}%",
            "detected": conflict_detected,
            "total": total_queries,
        },
    ))

    # --- Conflict detection: context-dependent (no false conflict) ---
    v22_context = HybridSimilarityLearner(
        k=3,
        conflict_config=ConflictConfig(input_similarity_threshold=0.8),
    )
    train(v22_context, CONTEXT_DEPENDENT)
    false_conflicts = 0
    for query, _expected in CONTEXT_QUERIES:
        result = v22_context.predict(query)
        if result.has_conflict:
            false_conflicts += 1

    suite.add(BenchmarkResult(
        name="Context-Dependent: No False Conflicts",
        description="Different outputs for different contexts should not conflict",
        passed=false_conflicts <= 1,
        details={
            "false_conflicts": false_conflicts,
            "total_queries": len(CONTEXT_QUERIES),
        },
    ))

    # --- Confidence behavior with conflicts ---
    v22_conf = HybridSimilarityLearner(
        k=3,
        conflict_config=ConflictConfig(input_similarity_threshold=0.5),
    )
    train(v22_conf, CONFLICT_EXACT)
    base_confs = []
    conflict_confs = []
    for query in CONFLICT_QUERIES:
        result = v22_conf.predict(query)
        base_confs.append(result.base_confidence)
        conflict_confs.append(result.confidence)

    avg_base = sum(base_confs) / len(base_confs) if base_confs else 0
    avg_conf = sum(conflict_confs) / len(conflict_confs) if conflict_confs else 0
    confidence_reduced = avg_conf < avg_base

    suite.add(BenchmarkResult(
        name="Confidence Reduced on Conflict",
        description="Conflict should lower confidence",
        passed=confidence_reduced or len(base_confs) == 0,
        details={
            "avg_base_confidence": f"{avg_base:.3f}",
            "avg_adjusted_confidence": f"{avg_conf:.3f}",
        },
    ))

    # --- Feedback-driven resolution ---
    v22_fb = HybridSimilarityLearner(
        k=3,
        conflict_config=ConflictConfig(
            input_similarity_threshold=0.5,
            min_evidence_samples=2,
        ),
    )
    train(v22_fb, CONFLICT_EXACT)

    # Give feedback favoring "use sorted()"
    for _ in range(8):
        result = v22_fb.predict("sort a list")
        if result.output == "use sorted()":
            v22_fb.feedback("sort a list", "use sorted()", correct=True)
        elif result.output == "use list.sort()":
            v22_fb.feedback("sort a list", "use list.sort()", correct=False,
                             actual_output="use sorted()")

    final = v22_fb.predict("sort a list")
    resolved = final.is_resolved or final.output == "use sorted()"

    suite.add(BenchmarkResult(
        name="Feedback-Driven Resolution",
        description="Consistent feedback should resolve conflict",
        passed=resolved,
        details={
            "final_output": final.output,
            "conflict_state": final.overall_conflict_state.value,
            "has_conflict": final.has_conflict,
        },
    ))

    # --- Persistence ---
    v22_persist = HybridSimilarityLearner(
        k=3,
        scorer_config=ScorerConfig(),
        conflict_config=ConflictConfig(),
    )
    train(v22_persist, NO_CONFLICT)

    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        v22_persist.save_state(tmpdir)
        loaded = HybridSimilarityLearner.load_state(
            tmpdir,
            scorer_config=ScorerConfig(),
            conflict_config=ConflictConfig(),
        )
        loaded_result = loaded.predict("sort list")
        persist_ok = loaded_result.output == "use sorted()"

    suite.add(BenchmarkResult(
        name="V2.2 Persistence",
        description="Conflict config saves and loads correctly",
        passed=persist_ok,
        details={
            "loaded_prediction": loaded_result.output,
        },
    ))

    # --- Latency overhead ---
    latency_overhead = (
        (v22_results["avg_latency_ms"] / v21_results["avg_latency_ms"] - 1.0) * 100
        if v21_results["avg_latency_ms"] > 0 else 0
    )
    latency_ok = v22_results["avg_latency_ms"] < 2.0

    suite.add(BenchmarkResult(
        name="V2.2 Latency Overhead",
        description="V2.2 conflict detection must stay under 2ms",
        passed=latency_ok,
        details={
            "v21_avg_ms": v21_results["avg_latency_ms"],
            "v22_avg_ms": v22_results["avg_latency_ms"],
            "overhead_pct": f"{round(latency_overhead, 1)}%",
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
    out_path = results_dir / "v2_2_benchmark.json"
    out_path.write_text(json.dumps(result_data, indent=2), encoding="utf-8")
    print(f"\nResults saved to {out_path}")
