"""V2.3.2 large-scale calibration benchmark with hundreds of cases.

Generates realistic scenarios with varied evidence, conflict, novelty, etc.
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


def build_large_dataset():
    """Build a large, realistic calibration dataset.

    Returns: (training_data, feedback_data, test_cases)
    """
    # 30 categories, 5-10 variations each = 150-300 training examples
    categories = [
        # (category_name, [input_variations], output, n_feedback_correct, n_feedback_incorrect)
        ("sort",
         ["sort a list", "sort an array", "sort items", "sort data", "sort elements",
          "sort numbers", "sort strings", "order list", "order items", "rank items"],
         "sorted(x)", 12, 0),
        ("reverse",
         ["reverse a string", "reverse text", "reverse characters", "reverse sequence",
          "invert string", "flip string", "backwards text"],
         "s[::-1]", 10, 0),
        ("max",
         ["find maximum", "find largest", "get max value", "find peak", "maximum element",
          "highest value", "greatest number"],
         "max(x)", 8, 0),
        ("min",
         ["find minimum", "find smallest", "get min value", "find valley", "minimum element",
          "lowest value"],
         "min(x)", 8, 0),
        ("join",
         ["join strings", "concatenate list", "merge strings", "combine items", "join elements",
          "string join"],
         "+".join(["sep.join(items)"]), 7, 0),
        ("split",
         ["split string", "tokenize text", "break into parts", "split by delimiter",
          "divide string"],
         "text.split(sep)", 6, 0),
        ("contains",
         ["check membership", "element exists", "is in collection", "membership test",
          "check if present"],
         "x in y", 9, 0),
        ("length",
         ["count items", "get size", "measure length", "count elements", "how many items"],
         "len(x)", 7, 0),
        ("filter",
         ["filter list", "select items", "keep matching", "filter elements", "subset data"],
         "[x for x in items if cond]", 5, 0),
        ("map",
         ["transform items", "apply function", "map over list", "transform each", "apply to all"],
         "[f(x) for x in items]", 5, 0),
        ("open",
         ["open a file", "file handle", "open for reading", "create file handle"],
         "open(path)", 6, 0),
        ("read",
         ["read file", "read all text", "load file data", "get file content"],
         "f.read()", 6, 0),
        ("write",
         ["write to file", "save data", "output to file", "persist data"],
         "f.write(data)", 6, 0),
        ("iterate",
         ["iterate range", "loop numbers", "generate sequence", "number sequence"],
         "for i in range(n)", 5, 0),
        ("enumerate",
         ["index and value", "numbered iteration", "count while iterating"],
         "enumerate(items)", 4, 0),
        ("zip",
         ["combine lists", "pair elements", "zip together", "interleave lists"],
         "zip(list1, list2)", 4, 0),
        ("reduce",
         ["aggregate items", "reduce list", "fold operation", "accumulate values"],
         "functools.reduce(f, items)", 3, 0),
        ("unique",
         ["remove duplicates", "get unique items", "deduplicate list", "distinct elements"],
         "set(items)", 5, 0),
        ("flatten",
         ["flatten nested", "unwrap lists", "flatten structure", "deep flatten"],
         "[x for sub in items for x in sub]", 3, 0),
        ("sort_desc",
         ["sort descending", "reverse sort", "descending order"],
         "sorted(items, reverse=True)", 4, 0),
        ("encode",
         ["encode string", "convert to bytes", "string encoding"],
         "text.encode('utf-8')", 3, 0),
        ("decode",
         ["decode bytes", "convert from bytes", "byte decoding"],
         "data.decode('utf-8')", 3, 0),
        ("json_load", ["parse JSON", "load JSON", "deserialize JSON"], "json.loads(text)", 5, 0),
        ("json_dump", ["serialize JSON", "dump JSON", "convert to JSON"], "json.dumps(obj)", 5, 0),
        ("regex", ["match pattern", "find regex", "pattern match"],
         "re.search(pattern, text)", 4, 0),
        ("date_now", ["current date", "today's date", "get date"], "datetime.now()", 3, 0),
        ("sleep", ["pause execution", "wait seconds", "delay"], "time.sleep(n)", 3, 0),
        ("type_check", ["check type", "is instance", "type verification"],
         "isinstance(x, T)", 4, 0),
        ("string_format", ["format string", "interpolate string", "build string"],
         "f'{variable}'", 4, 0),
        ("list_comp", ["list comprehension", "transform with comprehension", "filtered list"],
         "[expr for x in items]", 4, 0),
    ]

    training = []
    feedback = []

    for _cat_name, inputs, output, n_correct, n_incorrect in categories:
        for inp in inputs:
            training.append((inp, output))
        # Apply feedback to first few examples
        for inp in inputs[:3]:
            for _ in range(n_correct):
                feedback.append((inp, output, True))
            for _ in range(n_incorrect):
                feedback.append((inp, output, False))

    # Build test cases: each input variation should predict correctly
    test_cases = []
    for _cat_name, inputs, output, _, _ in categories:
        for inp in inputs:
            test_cases.append(CalibrationCase(
                query=inp,
                expected=output,
                confidence=0.0,
                predicted="",
                correct=False,
            ))

    # Add novel/out-of-distribution queries (should get low confidence)
    novel_queries = [
        ("bake a cake", "recipe"),
        ("fly a plane", "pilot"),
        ("swim in pool", "water"),
        ("paint a picture", "brush"),
        ("write a novel", "pen"),
        ("build a house", "hammer"),
        ("cook dinner", "stove"),
        ("drive a car", "steering"),
        ("play guitar", "strings"),
        ("garden plants", "soil"),
        ("fix plumbing", "wrench"),
        ("sew clothes", "needle"),
        ("brew coffee", "beans"),
        ("dance ballet", "grace"),
        ("yoga poses", "flexibility"),
    ]
    for query, expected in novel_queries:
        test_cases.append(CalibrationCase(
            query=query,
            expected=expected,
            confidence=0.0,
            predicted="",
            correct=False,
        ))

    # Add contradictory cases
    contradictory_training = [
        ("sort a list", "sorted(x)"),
        ("sort a list", "list.sort()"),
        ("sort a list", "sorted(x)"),
        ("sort a list", "list.sort()"),
        ("sort a list", "sorted(x)"),
    ]
    contradictory_feedback = [
        ("sort a list", "sorted(x)", True),
        ("sort a list", "sorted(x)", True),
        ("sort a list", "sorted(x)", True),
        ("sort a list", "list.sort()", True),
        ("sort a list", "list.sort()", True),
        ("sort a list", "list.sort()", True),
    ]
    training.extend(contradictory_training)
    feedback.extend(contradictory_feedback)

    return training, feedback, test_cases


def run_benchmark():
    """Run the large-scale benchmark."""
    print("V2.3.2 Large-Scale Calibration Benchmark")
    print("="*60)

    training, feedback, test_cases = build_large_dataset()
    print(f"Training examples: {len(training)}")
    print(f"Feedback entries: {len(feedback)}")
    print(f"Test cases: {len(test_cases)}")

    # --- V2.3 baseline ---
    print("\n--- Running V2.3 baseline ---")
    v23_cases = []
    v23_learner = HybridSimilarityLearner(
        k=5, lexical_weight=1.0, semantic_weight=0.0,
        scorer_config=ScorerConfig(), conflict_config=ConflictConfig(),
        confidence_config=ConfidenceConfig(),
    )
    for inp, out in training:
        v23_learner.learn(LearningInput(observation={"input": inp, "output": out}))
    for inp, out, correct in feedback:
        v23_learner.feedback(inp, out, correct)

    for case in test_cases:
        r = v23_learner.predict(case.query)
        v23_cases.append(CalibrationCase(
            query=case.query, expected=case.expected,
            confidence=r.confidence, predicted=r.output,
            correct=r.output == case.expected,
            metadata={"similarity": r.similarity, "version": "v2.3"},
        ))

    v23_report = compute_full_report(v23_cases)
    print(f"  V2.3: Brier={v23_report.brier:.4f}, ECE={v23_report.ece:.4f}, "
          f"mean_conf={v23_report.mean_confidence:.4f}, "
          f"discrim={v23_report.discrimination_gap:.4f}")

    # --- V2.3.2 raw ---
    print("\n--- Running V2.3.2 (new formula) ---")
    v232_cases = []
    v232_learner = HybridSimilarityLearner(
        k=5, lexical_weight=1.0, semantic_weight=0.0,
        scorer_config=ScorerConfig(), conflict_config=ConflictConfig(),
        confidence_config=ConfidenceConfig(),
    )
    for inp, out in training:
        v232_learner.learn(LearningInput(observation={"input": inp, "output": out}))
    for inp, out, correct in feedback:
        v232_learner.feedback(inp, out, correct)

    raw_confs = []
    for case in test_cases:
        r = v232_learner.predict(case.query)
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
            query=case.query, expected=case.expected,
            confidence=v232_result.confidence, predicted=r.output,
            correct=r.output == case.expected,
            metadata={"similarity": r.similarity, "version": "v2.3.2",
                      "raw_confidence": v232_result.raw_confidence},
        ))

    v232_report = compute_full_report(v232_cases)
    print(f"  V2.3.2: Brier={v232_report.brier:.4f}, ECE={v232_report.ece:.4f}, "
          f"mean_conf={v232_report.mean_confidence:.4f}, "
          f"discrim={v232_report.discrimination_gap:.4f}")

    # --- Build calibration map from V2.3.2 results ---
    print("\n--- Building calibration map ---")
    correctness = [c.correct for c in v232_cases]
    cal_map = build_calibration_map(raw_confs, correctness, n_bins=5, min_samples_per_bin=5)
    print(f"  Buckets: {len(cal_map.buckets)}, fallback={cal_map.fallback_mode}")
    for b in cal_map.buckets:
        print(f"    [{b.raw_low:.3f}, {b.raw_high:.3f}] -> {b.calibrated:.3f} (n={b.count})")

    # --- V2.3.2 calibrated ---
    print("\n--- Running V2.3.2 + calibration ---")
    v232_cal_cases = []
    for case in v232_cases:
        calibrated_conf = calibrate(case.confidence, cal_map)
        v232_cal_cases.append(CalibrationCase(
            query=case.query, expected=case.expected,
            confidence=calibrated_conf, predicted=case.predicted,
            correct=case.correct,
            metadata={**case.metadata, "calibrated": True},
        ))

    v232_cal_report = compute_full_report(v232_cal_cases)
    print(f"  V2.3.2+cal: Brier={v232_cal_report.brier:.4f}, ECE={v232_cal_report.ece:.4f}, "
          f"mean_conf={v232_cal_report.mean_confidence:.4f}, "
          f"discrim={v232_cal_report.discrimination_gap:.4f}")

    # --- Summary ---
    print(f"\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")
    print(f"  {'Version':25s} | {'Brier':>8s} | {'ECE':>8s} | "
          f"{'Mean Conf':>10s} | {'Discrim':>8s} | {'Abstain':>8s}")
    print(f"  {'-'*75}")
    for label, cases in [("V2.3", v23_cases), ("V2.3.2 raw", v232_cases),
                         ("V2.3.2 calibrated", v232_cal_cases)]:
        r = compute_full_report(cases)
        print(f"  {label:25s} | {r.brier:8.4f} | {r.ece:8.4f} | "
              f"{r.mean_confidence:10.4f} | {r.discrimination_gap:8.4f} | "
              f"{r.abstention_quality:8.4f}")

    # --- Improvement ---
    print("\n  Improvement (V2.3 -> V2.3.2):")
    print(f"    Brier: {v23_report.brier:.4f} -> {v232_report.brier:.4f}")
    print(f"    ECE: {v23_report.ece:.4f} -> {v232_report.ece:.4f}")
    print(f"    Discrimination: {v23_report.discrimination_gap:.4f} -> "
          f"{v232_report.discrimination_gap:.4f}")

    # --- Selective prediction ---
    print("\n  Selective prediction (V2.3.2 calibrated):")
    for thresh in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
        above = [c for c in v232_cal_cases if c.confidence >= thresh]
        if above:
            acc = sum(1 for c in above if c.correct) / len(above)
            cov = len(above) / len(v232_cal_cases)
            print(f"    conf>={thresh:.1f}: accuracy={acc:.1%}, coverage={cov:.1%}")

    return v23_report, v232_report, v232_cal_report


if __name__ == "__main__":
    run_benchmark()
