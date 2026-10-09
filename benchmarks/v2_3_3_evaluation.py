"""V2.3.3 comprehensive evaluation framework.

Proper train/calibration/held-out test splits.
All dataset categories A-L. Professional calibration metrics.
Calibration method comparison. Version comparison.

No benchmark leakage. No metric manipulation.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core.learner.base import LearningInput
from core.learner.calibration.calibrator import (
    build_calibration_map,
    calibrate,
)
from core.learner.calibration.metrics import (
    CalibrationCase,
    brier_score,
    expected_calibration_error,
    selective_prediction_accuracy,
    selective_prediction_coverage,
)
from core.learner.confidence import ConfidenceConfig
from core.learner.conflict import ConflictConfig
from core.learner.learner_v2 import HybridSimilarityLearner
from core.learner.retrieval_scorer import ScorerConfig

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class EvalResult:
    dataset: str
    samples: list
    brier: float = 0.0
    ece: float = 0.0
    accuracy: float = 0.0
    mean_confidence: float = 0.0
    coverage_50: float = 0.0
    accuracy_50: float = 0.0
    coverage_70: float = 0.0
    accuracy_70: float = 0.0
    coverage_90: float = 0.0
    accuracy_90: float = 0.0


@dataclass
class EvalSample:
    query: str
    expected: str
    predicted: str
    confidence: float
    correct: bool
    dataset: str
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Dataset builders (large, realistic)
# ---------------------------------------------------------------------------

def _synonym_variants(base_words: list[str], n: int) -> list[str]:
    """Generate realistic query variations."""
    templates = [
        "{w}", "how to {w}", "implement {w}", "write {w}",
        "create {w}", "do {w}", "build {w}", "code {w}",
        "make {w}", "add {w}",
    ]
    result = []
    for w in base_words:
        for t in templates[:n]:
            result.append(t.format(w=w))
    return result


def _build_dataset_a():
    """Normal: representative everyday predictions.
    IMPORTANT: Test queries are paraphrased, NOT exact duplicates of training.
    """
    categories = {
        "sort": ("sorted(x)", ["sort a list", "sort array", "sort items", "sort elements",
                              "sort numbers"]),
        "reverse": ("s[::-1]", ["reverse a string", "flip string", "backwards text",
                                "invert string"]),
        "max": ("max(x)", ["find maximum", "find max", "largest value", "highest number"]),
        "min": ("min(x)", ["find minimum", "find min", "smallest value", "lowest number"]),
        "len": ("len(x)", ["count elements", "count items", "how many items", "get length"]),
        "join": ("''.join(x)", ["join strings", "concatenate", "merge strings", "string join"]),
        "split": ("x.split(s)", ["split string", "split by delimiter", "tokenize",
                                 "divide string"]),
        "filter": ("[i for i in x if c]", ["filter list", "filter elements", "select items",
                                           "keep matching"]),
        "map": ("[f(i) for i in x]", ["map function", "apply function", "transform each",
                                      "mapping"]),
        "file": ("open(f).read()", ["read file", "load file", "file contents", "read text file"]),
    }

    # Test queries are PARAPHRASED — never identical to training
    test_paraphrases = {
        "sort": ("sorted(x)", ["arrange numbers in order", "order the items",
                                "organize the collection", "put elements in sorted order",
                                "sort the data ascending"]),
        "reverse": ("s[::-1]", ["flip the text", "invert the string", "make string backwards",
                                 "reverse character order", "mirror the text"]),
        "max": ("max(x)", ["get the largest", "determine peak value", "find the biggest element",
                            "what is the maximum", "identify the highest"]),
        "min": ("min(x)", ["get the smallest", "determine lowest value",
                            "find the smallest element",
                            "what is the minimum", "identify the lowest"]),
        "len": ("len(x)", ["how many items are there", "what is the size", "count the objects",
                            "determine the length", "get element count"]),
        "join": ("''.join(x)", ["concatenate text", "combine strings together", "merge text",
                                 "smush strings", "join all parts"]),
        "split": ("x.split(s)", ["break apart text", "tokenize the string", "separate by delimiter",
                                  "cut text into pieces", "divide by separator"]),
        "filter": ("[i for i in x if c]", ["select matching items", "keep only valid entries",
                                             "filter out non-matching", "extract subset",
                                             "conditional selection"]),
        "map": ("[f(i) for i in x]", ["transform each element", "apply function to all",
                                        "run function on everything", "map over collection",
                                        "apply to each"]),
        "file": ("open(f).read()", ["load file data", "grab file contents", "read the file",
                                     "open and read text", "load text from file"]),
    }

    train, feedback, test = [], [], []
    for _cat, (output, queries) in categories.items():
        train.extend([{"input": q, "output": output} for q in queries])
        for q in queries:
            feedback.extend([(q, output, True)] * 5)
    for _cat, (output, queries) in test_paraphrases.items():
        test.extend([(q, output) for q in queries])
    return train, feedback, test


def _build_dataset_b():
    """Easy: strong evidence, high agreement."""
    train, feedback, test = [], [], []
    sort_queries = ["sort a list", "sort list", "sort array", "sort items", "sort elements",
                    "sort numbers", "sort the data", "sort collection", "order list",
                    "arrange elements"]
    for q in sort_queries:
        train.append({"input": q, "output": "sorted(x)"})
    for _ in range(20):
        for q in sort_queries[:5]:
            feedback.append((q, "sorted(x)", True))
    test = [(q, "sorted(x)") for q in sort_queries[5:]]
    return train, feedback, test


def _build_dataset_c():
    """Hard: weak evidence, ambiguous queries."""
    train = [
        {"input": "process data", "output": "transform(x)"},
        {"input": "handle input", "output": "parse(x)"},
    ]
    feedback = [("process data", "transform(x)", True)] * 3
    test = [
        ("process information", "transform(x)"),
        ("handle the data", "parse(x)"),
        ("manage input", "transform(x)"),
        ("deal with data", "parse(x)"),
        ("treat the input", "transform(x)"),
        ("work with data", "parse(x)"),
        ("manipulate data", "transform(x)"),
        ("read the input", "parse(x)"),
    ]
    return train, feedback, test


def _build_dataset_d():
    """Novel: queries outside learned distribution."""
    train = [
        {"input": "sort a list", "output": "sorted(x)"},
        {"input": "reverse string", "output": "s[::-1]"},
    ]
    feedback = [("sort a list", "sorted(x)", True)] * 5
    test = [
        ("deploy application", "deploy()"),
        ("train neural network", "model.fit()"),
        ("compile source code", "gcc main.c"),
        ("encrypt password", "hash(pw)"),
        ("calculate tax", "tax = income * rate"),
        ("draw a circle", "canvas.circle()"),
        ("send email", "smtp.send()"),
        ("resize image", "image.resize()"),
        ("compress file", "gzip.compress()"),
        ("parse XML", "etree.parse()"),
        ("send SMS", "sms.send()"),
        ("monitor CPU", "cpu.usage()"),
        ("backup database", "db.backup()"),
        ("scale image", "image.scale()"),
        ("hash password", "bcrypt.hash()"),
    ]
    return train, feedback, test


def _build_dataset_e():
    """Conflict: credible memories disagree."""
    train = [
        {"input": "sort a list", "output": "sorted(x)"},
        {"input": "sort a list", "output": "list.sort()"},
    ]
    feedback = []
    for _ in range(10):
        feedback.append(("sort a list", "sorted(x)", True))
        feedback.append(("sort a list", "list.sort()", True))
    test = [
        ("sort a list", "sorted(x)"),
        ("sort array", "sorted(x)"),
        ("sort items", "sorted(x)"),
        ("order list", "sorted(x)"),
        ("arrange elements", "sorted(x)"),
        ("sort numbers", "sorted(x)"),
    ]
    return train, feedback, test


def _build_dataset_f():
    """Poisoned: irrelevant memories injected."""
    train = [{"input": "sort a list", "output": "sorted(x)"}]
    noise = [
        ("cook dinner", "recipe"), ("walk the dog", "leash"), ("wash clothes", "detergent"),
        ("mow lawn", "mower"), ("paint wall", "brush"), ("fix plumbing", "wrench"),
        ("repair car", "tools"), ("bake cake", "oven"), ("knit sweater", "needles"),
        ("water plants", "hose"),
    ]
    for inp, out in noise:
        train.append({"input": inp, "output": out})
    feedback = [("sort a list", "sorted(x)", True)] * 10
    test = [
        ("sort a list", "sorted(x)"),
        ("sort array", "sorted(x)"),
        ("sort items", "sorted(x)"),
        ("order list", "sorted(x)"),
        ("arrange elements", "sorted(x)"),
    ]
    return train, feedback, test


def _build_dataset_g():
    """Duplicate poisoning: many copies of wrong memory."""
    train = []
    for _ in range(15):
        train.append({"input": "sort a list", "output": "bubble_sort(x)"})
    train.append({"input": "sort a list", "output": "sorted(x)"})
    feedback = [("sort a list", "bubble_sort(x)", True)] * 5
    feedback += [("sort a list", "sorted(x)", True)] * 8
    test = [
        ("sort a list", "sorted(x)"),
        ("sort array", "sorted(x)"),
        ("sort items", "sorted(x)"),
        ("order list", "sorted(x)"),
        ("arrange elements", "sorted(x)"),
    ]
    return train, feedback, test


def _build_dataset_h():
    """Recency trap: recent incorrect vs older reliable."""
    train = [{"input": "sort a list", "output": "sorted(x)"}]
    feedback = [("sort a list", "sorted(x)", True)] * 10
    feedback += [("sort a list", "bubble_sort(x)", True)] * 3
    test = [
        ("sort a list", "sorted(x)"),
        ("sort array", "sorted(x)"),
        ("sort items", "sorted(x)"),
        ("order list", "sorted(x)"),
        ("arrange elements", "sorted(x)"),
    ]
    return train, feedback, test


def _build_dataset_i():
    """Historical-success trap: successful but irrelevant."""
    train = [
        {"input": "sort a list", "output": "sorted(x)"},
        {"input": "cook dinner", "output": "recipe"},
    ]
    feedback = [("cook dinner", "recipe", True)] * 30
    feedback += [("sort a list", "sorted(x)", True)] * 5
    test = [
        ("sort a list", "sorted(x)"),
        ("sort array", "sorted(x)"),
        ("sort items", "sorted(x)"),
        ("order list", "sorted(x)"),
        ("arrange elements", "sorted(x)"),
    ]
    return train, feedback, test


def _build_dataset_j():
    """Feedback poisoning: repeated incorrect feedback."""
    train = [{"input": "sort a list", "output": "sorted(x)"}]
    feedback = [("sort a list", "sorted(x)", True)] * 5
    feedback += [("sort a list", "sorted(x)", False)] * 15
    test = [
        ("sort a list", "sorted(x)"),
        ("sort array", "sorted(x)"),
        ("sort items", "sorted(x)"),
        ("order list", "sorted(x)"),
        ("arrange elements", "sorted(x)"),
    ]
    return train, feedback, test


def _build_dataset_k():
    """Distribution shift: same concept, different wording."""
    train = [
        {"input": "sort a list", "output": "sorted(x)"},
        {"input": "reverse string", "output": "s[::-1]"},
        {"input": "find maximum", "output": "max(x)"},
    ]
    feedback = [
        ("sort a list", "sorted(x)", True),
        ("sort a list", "sorted(x)", True),
        ("sort a list", "sorted(x)", True),
        ("reverse string", "s[::-1]", True),
        ("reverse string", "s[::-1]", True),
        ("find maximum", "max(x)", True),
        ("find maximum", "max(x)", True),
    ]
    test = [
        ("arrange numbers in ascending order", "sorted(x)"),
        ("flip the string backwards", "s[::-1]"),
        ("determine the largest element", "max(x)"),
        ("organize the collection numerically", "sorted(x)"),
        ("invert the character sequence", "s[::-1]"),
        ("find the peak value", "max(x)"),
        ("put items in order", "sorted(x)"),
        ("mirror the text", "s[::-1]"),
        ("identify the greatest", "max(x)"),
    ]
    return train, feedback, test


def _build_dataset_l():
    """Persistence: serialize and reload."""
    train = [
        {"input": "sort a list", "output": "sorted(x)"},
        {"input": "reverse string", "output": "s[::-1]"},
        {"input": "find maximum", "output": "max(x)"},
    ]
    feedback = [
        ("sort a list", "sorted(x)", True),
        ("sort a list", "sorted(x)", True),
        ("sort a list", "sorted(x)", True),
        ("reverse string", "s[::-1]", True),
        ("reverse string", "s[::-1]", True),
        ("find maximum", "max(x)", True),
        ("find maximum", "max(x)", True),
    ]
    test = [
        ("sort a list", "sorted(x)"),
        ("reverse string", "s[::-1]"),
        ("find max value", "max(x)"),
    ]
    return train, feedback, test


ALL_DATASETS = {
    "A_normal": _build_dataset_a,
    "B_easy": _build_dataset_b,
    "C_hard": _build_dataset_c,
    "D_novel": _build_dataset_d,
    "E_conflict": _build_dataset_e,
    "F_poisoned": _build_dataset_f,
    "G_duplicate": _build_dataset_g,
    "H_recency": _build_dataset_h,
    "I_historical": _build_dataset_i,
    "J_feedback": _build_dataset_j,
    "K_shift": _build_dataset_k,
    "L_persistence": _build_dataset_l,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_learner():
    return HybridSimilarityLearner(
        k=5,
        lexical_weight=1.0,
        semantic_weight=0.0,
        scorer_config=ScorerConfig(),
        conflict_config=ConflictConfig(),
        confidence_config=ConfidenceConfig(use_v232=True),
    )


def _train_and_feedback(learner, train, feedback):
    for obs in train:
        learner.learn(LearningInput(observation=obs))
    for text, output, correct in feedback:
        learner.feedback(text, output, correct=correct)


def _eval_query(learner, query, expected, dataset_name) -> EvalSample:
    result = learner.predict(query)
    return EvalSample(
        query=query, expected=expected, predicted=result.output,
        confidence=result.confidence, correct=(result.output == expected),
        dataset=dataset_name,
    )


def _to_cases(samples):
    return [CalibrationCase(
        query=s.query, expected=s.expected, predicted=s.predicted,
        confidence=s.confidence, correct=s.correct,
    ) for s in samples]


# ---------------------------------------------------------------------------
# Evaluation with proper splits
# ---------------------------------------------------------------------------

def evaluate_dataset(name, builder, tmp_dir) -> EvalResult:
    train, feedback, test = builder()

    # Split test: 50% for calibration, 50% held-out for evaluation
    n_cal = len(test) // 2
    cal_pairs = test[:n_cal]
    held_out = test[n_cal:] if n_cal < len(test) else test

    # Build learner
    learner = _make_learner()
    _train_and_feedback(learner, train, feedback)

    # Evaluate on calibration set
    cal_samples = []
    for query, expected in cal_pairs:
        cal_samples.append(_eval_query(learner, query, expected, name))

    # Build calibration map from cal set
    raw_confs = [s.confidence for s in cal_samples]
    correctness = [s.correct for s in cal_samples]
    cal_map = build_calibration_map(raw_confs, correctness, n_bins=5, min_samples_per_bin=2)

    # Evaluate on held-out set
    held_samples = []
    for query, expected in held_out:
        sample = _eval_query(learner, query, expected, name)
        sample.confidence = calibrate(sample.confidence, cal_map)
        held_samples.append(sample)

    # If no held-out data, use all test data
    if not held_samples:
        held_samples = cal_samples

    # Compute metrics
    cases = _to_cases(held_samples)
    if not cases:
        return EvalResult(dataset=name, samples=[])

    brier = brier_score(cases)
    ece = expected_calibration_error(cases, n_bins=5)
    accuracy = sum(1 for s in held_samples if s.correct) / len(held_samples)
    mean_conf = sum(s.confidence for s in held_samples) / len(held_samples)

    # Selective prediction
    cov_50 = selective_prediction_coverage(cases, thresholds=[0.5]).get(0.5, 0.0)
    acc_50 = selective_prediction_accuracy(cases, thresholds=[0.5]).get(0.5, 0.0)
    cov_70 = selective_prediction_coverage(cases, thresholds=[0.7]).get(0.7, 0.0)
    acc_70 = selective_prediction_accuracy(cases, thresholds=[0.7]).get(0.7, 0.0)
    cov_90 = selective_prediction_coverage(cases, thresholds=[0.9]).get(0.9, 0.0)
    acc_90 = selective_prediction_accuracy(cases, thresholds=[0.9]).get(0.9, 0.0)

    return EvalResult(
        dataset=name, samples=held_samples,
        brier=brier, ece=ece, accuracy=accuracy, mean_confidence=mean_conf,
        coverage_50=cov_50, accuracy_50=acc_50,
        coverage_70=cov_70, accuracy_70=acc_70,
        coverage_90=cov_90, accuracy_90=acc_90,
    )


# ---------------------------------------------------------------------------
# Version comparison
# ---------------------------------------------------------------------------

def _run_version_comparison():
    train, feedback, test = _build_dataset_a()

    configs = {
        "V2.0": (None, None, None),
        "V2.1": (ScorerConfig(), None, None),
        "V2.2": (ScorerConfig(), ConflictConfig(), None),
        "V2.3": (ScorerConfig(), ConflictConfig(), ConfidenceConfig(use_v232=False)),
        "V2.3.2": (ScorerConfig(), ConflictConfig(), ConfidenceConfig(use_v232=True)),
    }

    results = {}
    for version, (scorer, conflict, confidence) in configs.items():
        learner = HybridSimilarityLearner(
            k=5, lexical_weight=1.0, semantic_weight=0.0,
            scorer_config=scorer, conflict_config=conflict,
            confidence_config=confidence,
        )
        _train_and_feedback(learner, train, feedback)

        all_cases = []
        for query, expected in test:
            result = learner.predict(query)
            all_cases.append(CalibrationCase(
                query=query, expected=expected, predicted=result.output,
                confidence=result.confidence, correct=(result.output == expected),
            ))

        brier = brier_score(all_cases)
        ece = expected_calibration_error(all_cases, n_bins=5)
        acc = sum(1 for c in all_cases if c.correct) / len(all_cases)
        mean_c = sum(c.confidence for c in all_cases) / len(all_cases)

        results[version] = {
            "brier": brier, "ece": ece, "accuracy": acc, "mean_confidence": mean_c,
        }

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("V2.3.3 COMPREHENSIVE EVALUATION")
    print("=" * 70)

    tmp_dir = Path(__file__).resolve().parent.parent / "tmp_eval"
    tmp_dir.mkdir(exist_ok=True)

    # Run all datasets
    all_results: list[EvalResult] = []
    for name, builder in ALL_DATASETS.items():
        result = evaluate_dataset(name, builder, tmp_dir)
        all_results.append(result)

    # Print results
    print(f"\n{'Dataset':<15} {'Brier':>8} {'ECE':>8} {'Acc':>8} {'MeanC':>8} "
          f"{'Cov50':>8} {'Acc50':>8} {'Cov70':>8} {'Acc70':>8} {'Cov90':>8} {'Acc90':>8}")
    print("-" * 120)
    for r in all_results:
        n = len(r.samples)
        print(f"{r.dataset:<15} {r.brier:>8.4f} {r.ece:>8.4f} {r.accuracy:>8.3f} "
              f"{r.mean_confidence:>8.3f} "
              f"{r.coverage_50:>8.3f} {r.accuracy_50:>8.3f} "
              f"{r.coverage_70:>8.3f} {r.accuracy_70:>8.3f} "
              f"{r.coverage_90:>8.3f} {r.accuracy_90:>8.3f}  (n={n})")

    # Aggregate
    all_samples = [s for r in all_results for s in r.samples]
    if all_samples:
        all_cases = _to_cases(all_samples)
        agg_brier = brier_score(all_cases)
        agg_ece = expected_calibration_error(all_cases, n_bins=5)
        agg_acc = sum(1 for s in all_samples if s.correct) / len(all_samples)
        agg_mean = sum(s.confidence for s in all_samples) / len(all_samples)
        print("-" * 120)
        print(f"{'AGGREGATE':<15} {agg_brier:>8.4f} {agg_ece:>8.4f} {agg_acc:>8.3f} "
              f"{agg_mean:>8.3f}  (n={len(all_samples)})")

    # Version comparison
    print("\n\nVERSION COMPARISON (Dataset A)")
    print("=" * 70)
    vr = _run_version_comparison()
    print(f"{'Version':<12} {'Brier':>8} {'ECE':>8} {'Accuracy':>10} {'MeanConf':>10}")
    print("-" * 50)
    for version, metrics in vr.items():
        print(f"{version:<12} {metrics['brier']:>8.4f} {metrics['ece']:>8.4f} "
              f"{metrics['accuracy']:>10.3f} {metrics['mean_confidence']:>10.3f}")

    # Persistence test
    print("\n\nPERSISTENCE TEST")
    print("=" * 70)
    learner1 = _make_learner()
    _train_and_feedback(learner1, *(_build_dataset_l()[:2]))
    r1 = learner1.predict("sort a list")

    save_path = tmp_dir / "learner_state"
    learner1.save_state(str(save_path))

    loaded = HybridSimilarityLearner.load_state(str(save_path))
    r2 = loaded.predict("sort a list")

    print(f"  Before save: conf={r1.confidence:.4f}, output={r1.output}")
    print(f"  After load:  conf={r2.confidence:.4f}, output={r2.output}")
    print(f"  Match: {r1.output == r2.output and abs(r1.confidence - r2.confidence) < 0.01}")

    print("\nDone.")


if __name__ == "__main__":
    main()
