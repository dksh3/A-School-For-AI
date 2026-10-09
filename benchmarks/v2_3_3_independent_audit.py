"""V2.3.3 Independent Calibration Audit.

This benchmark is written independently of the production code.
It uses:
- Independently generated test data (no train/test overlap)
- Independent metric implementations (Brier, ECE from scratch)
- Strict data separation (train / calibration / held-out test)
- Raw prediction tables for every sample
- Multiple abstention thresholds
- Calibration leakage experiments

The goal is to determine whether the reported metrics are genuinely valid.
"""

from __future__ import annotations

import math
import random
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
from core.learner.confidence import ConfidenceConfig
from core.learner.conflict import ConflictConfig
from core.learner.learner_v2 import HybridSimilarityLearner
from core.learner.retrieval_scorer import ScorerConfig

# ======================================================================
# INDEPENDENT METRIC IMPLEMENTATIONS (NOT using production code)
# ======================================================================

def independent_brier(confidences: list[float], correct: list[bool]) -> float:
    """Brier score: mean((confidence - correct)^2). Range [0, 1]."""
    n = len(confidences)
    if n == 0:
        return 0.0
    return sum(
        (c - (1.0 if cor else 0.0)) ** 2
        for c, cor in zip(confidences, correct, strict=False)
    ) / n


def independent_ece(confidences: list[float], correct: list[bool], n_bins: int = 10) -> float:
    """Expected Calibration Error: weighted |accuracy - confidence| per bin."""
    n = len(confidences)
    if n == 0:
        return 0.0

    bins: list[list[tuple[float, bool]]] = [[] for _ in range(n_bins)]
    for c, cor in zip(confidences, correct, strict=False):
        bin_idx = min(int(c * n_bins), n_bins - 1)
        bins[bin_idx].append((c, cor))

    total = 0.0
    for b in bins:
        if not b:
            continue
        bin_acc = sum(1 for _, cor in b if cor) / len(b)
        bin_conf = sum(c for c, _ in b) / len(b)
        total += len(b) / n * abs(bin_acc - bin_conf)
    return total


def independent_reliability(confidences: list[float], correct: list[bool], n_bins: int = 10):
    """Return (bin_centers, bin_accuracies, bin_counts) for reliability diagram."""
    n = len(confidences)
    if n == 0:
        return [], [], []

    bins: list[list[tuple[float, bool]]] = [[] for _ in range(n_bins)]
    for c, cor in zip(confidences, correct, strict=False):
        bin_idx = min(int(c * n_bins), n_bins - 1)
        bins[bin_idx].append((c, cor))

    centers, accs, counts = [], [], []
    for i, b in enumerate(bins):
        if not b:
            continue
        centers.append((i + 0.5) / n_bins)
        accs.append(sum(1 for _, cor in b if cor) / len(b))
        counts.append(len(b))
    return centers, accs, counts


# ======================================================================
# DATASETS — TRULY INDEPENDENT (no train/test overlap)
# ======================================================================

def _build_train():
    """Training data: these exact (input, output) pairs go into the learner."""
    return [
        {"input": "sort a list", "output": "sorted(x)"},
        {"input": "reverse a string", "output": "s[::-1]"},
        {"input": "find maximum value", "output": "max(x)"},
        {"input": "find minimum value", "output": "min(x)"},
        {"input": "count elements", "output": "len(x)"},
        {"input": "join strings together", "output": "''.join(x)"},
        {"input": "split string by delimiter", "output": "x.split(s)"},
        {"input": "filter list items", "output": "[i for i in x if c]"},
        {"input": "map function over list", "output": "[f(i) for i in x]"},
        {"input": "read file contents", "output": "open(f).read()"},
    ]


def _build_feedback():
    """Feedback data: same queries as training, multiple confirmations."""
    feedback = []
    for obs in _build_train():
        for _ in range(5):
            feedback.append((obs["input"], obs["output"], True))
    return feedback


def _build_calibration():
    """Calibration data: PARAPHRASED queries with known outputs.
    These are NEVER inserted into the learner. They are used only
    to build the calibration map."""
    return [
        # Sort variations
        ("arrange numbers in order", "sorted(x)"),
        ("order the items", "sorted(x)"),
        ("organize the collection", "sorted(x)"),
        # Reverse variations
        ("flip the text", "s[::-1]"),
        ("invert the string", "s[::-1]"),
        # Max variations
        ("get the largest", "max(x)"),
        ("determine peak value", "max(x)"),
        # Min variations
        ("get the smallest", "min(x)"),
        ("determine lowest value", "min(x)"),
        # Count variations
        ("how many items", "len(x)"),
        ("what is the size", "len(x)"),
        # Join variations
        ("concatenate text", "''.join(x)"),
        ("combine strings", "''.join(x)"),
        # Split variations
        ("break apart text", "x.split(s)"),
        ("tokenize the string", "x.split(s)"),
        # Filter variations
        ("select matching items", "[i for i in x if c]"),
        ("keep only valid entries", "[i for i in x if c]"),
        # Map variations
        ("transform each element", "[f(i) for i in x]"),
        ("apply function to all", "[f(i) for i in x]"),
        # File variations
        ("load file data", "open(f).read()"),
    ]


def _build_held_out_test():
    """Held-out test data: NEVER seen during training, calibration, or tuning.
    These queries are phrased differently from training AND calibration."""
    return [
        # Easy: close paraphrases (high similarity expected)
        ("sort the elements", "sorted(x)"),
        ("reverse the characters", "s[::-1]"),
        ("find the maximum element", "max(x)"),
        ("find the minimum element", "min(x)"),
        ("get the length of the list", "len(x)"),
        ("merge text strings", "''.join(x)"),
        ("separate by separator", "x.split(s)"),
        ("keep items matching condition", "[i for i in x if c]"),
        ("apply transformation to each", "[f(i) for i in x]"),
        ("open and read a file", "open(f).read()"),
        # Hard: weaker paraphrases
        ("put numbers in ascending order", "sorted(x)"),
        ("make the string go backwards", "s[::-1]"),
        ("what is the biggest number", "max(x)"),
        ("what is the smallest number", "min(x)"),
        ("tell me how many there are", "len(x)"),
        ("smush the strings together", "''.join(x)"),
        ("cut the text into pieces", "x.split(s)"),
        ("throw out the ones that don't match", "[i for i in x if c]"),
        ("run a function on everything", "[f(i) for i in x]"),
        ("grab the contents of the file", "open(f).read()"),
        # Novel: completely different topics (should NOT match)
        ("deploy the application", ""),
        ("train a machine learning model", ""),
        ("compile the source code", ""),
        ("send an email message", ""),
        ("calculate the tax amount", ""),
        ("resize the image dimensions", ""),
        ("compress the archive file", ""),
        ("parse the XML document", ""),
        ("monitor the CPU usage", ""),
        ("backup the database", ""),
    ]


# ======================================================================
# LEARNER HELPER
# ======================================================================

def _make_learner(abstention_threshold: float = 0.2) -> HybridSimilarityLearner:
    return HybridSimilarityLearner(
        k=5,
        lexical_weight=1.0,
        semantic_weight=0.0,
        scorer_config=ScorerConfig(),
        conflict_config=ConflictConfig(),
        confidence_config=ConfidenceConfig(abstention_threshold=abstention_threshold),
    )


def _train_learner(learner, train, feedback):
    for obs in train:
        learner.learn(LearningInput(observation=obs))
    for text, output, correct in feedback:
        learner.feedback(text, output, correct=correct)


# ======================================================================
# PHASE 4: Independent metric verification
# ======================================================================

def _verify_metrics():
    """Compare independent vs production metrics."""
    print("\n" + "=" * 70)
    print("PHASE 4: INDEPENDENT METRIC VERIFICATION")
    print("=" * 70)

    # Create a known calibration curve
    confidences = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    correct = [False, False, False, False, True, True, True, True, True, True]

    ind_brier = independent_brier(confidences, correct)
    ind_ece = independent_ece(confidences, correct, n_bins=5)

    print(f"  Independent Brier: {ind_brier:.6f}")
    print(f"  Independent ECE:   {ind_ece:.6f}")

    # Verify with production metrics
    from core.learner.calibration.metrics import (
        CalibrationCase,
        brier_score,
        expected_calibration_error,
    )
    cases = [
        CalibrationCase(query=f"q{i}", expected="e", predicted="p",
                        confidence=c, correct=cor)
        for i, (c, cor) in enumerate(zip(confidences, correct, strict=False))
    ]
    prod_brier = brier_score(cases)
    prod_ece = expected_calibration_error(cases, n_bins=5)

    print(f"  Production Brier:  {prod_brier:.6f}")
    print(f"  Production ECE:    {prod_ece:.6f}")

    brier_match = abs(ind_brier - prod_brier) < 1e-10
    ece_match = abs(ind_ece - prod_ece) < 1e-10

    print(f"\n  Brier match: {'PASS' if brier_match else 'FAIL'} "
          f"(diff={abs(ind_brier - prod_brier):.2e})")
    print(f"  ECE match:   {'PASS' if ece_match else 'FAIL'} (diff={abs(ind_ece - prod_ece):.2e})")

    return brier_match, ece_match


# ======================================================================
# PHASE 5: Why is Brier=0.000? — Direct investigation
# ======================================================================

def _investigate_brier():
    """Run Dataset A from existing benchmark and show exactly why Brier=0.000."""
    print("\n" + "=" * 70)
    print("PHASE 5: WHY IS BRIER=0.000? — DIRECT INVESTIGATION")
    print("=" * 70)

    # Reproduce the existing benchmark's Dataset A exactly
    categories = {
        "sort": ("sorted(x)", ["sort a list", "sort array", "sort items",
                                "sort elements", "sort numbers"]),
        "reverse": ("s[::-1]", ["reverse a string", "flip string",
                                 "backwards text", "invert string"]),
        "max": ("max(x)", ["find maximum", "find max",
                            "largest value", "highest number"]),
    }

    train, feedback = [], []
    test = []
    for _cat, (output, queries) in categories.items():
        train.extend([{"input": q, "output": output} for q in queries])
        for q in queries:
            feedback.extend([(q, output, True)] * 5)
        test.extend([(q, output) for q in queries])

    learner = _make_learner()
    _train_learner(learner, train, feedback)

    print(f"\n  Training samples: {len(train)}")
    print(f"  Test samples: {len(test)}")

    # Check overlap
    train_inputs = {obs["input"] for obs in train}
    test_inputs = {q for q, _ in test}
    overlap = train_inputs & test_inputs
    print(f"  Train/test INPUT overlap: {len(overlap)} / {len(test_inputs)} "
          f"({100*len(overlap)/len(test_inputs):.0f}%)")

    if overlap:
        print(f"\n  *** CRITICAL FINDING: {len(overlap)} test queries are "
              "EXACT DUPLICATES of training queries ***")
        print("  This means every test query finds a perfect match in memory.")
        print("  Confidence will always be ~1.0, correctness will always be True.")
        print("  Brier = mean((1.0 - 1.0)^2) = 0.000")
        print("\n  This is a BENCHMARK DESIGN FLAW, not a production algorithm bug.")
    else:
        print("\n  No overlap found. Investigating further...")

    # Show raw predictions
    print("\n  Raw predictions (first 10):")
    print(f"  {'Query':<25} {'Expected':<15} {'Predicted':<15} {'Conf':>8} {'Correct':>8}")
    print(f"  {'-'*75}")

    confidences = []
    correctness = []
    for query, expected in test[:10]:
        r = learner.predict(query)
        conf = r.confidence
        pred = r.output
        cor = (pred == expected)
        confidences.append(conf)
        correctness.append(cor)
        print(f"  {query:<25} {expected:<15} {pred:<15} {conf:>8.4f} {str(cor):>8}")

    brier = independent_brier(confidences, correctness)
    print(f"\n  Brier on first 10: {brier:.6f}")

    # Full test set
    all_conf = []
    all_cor = []
    for query, expected in test:
        r = learner.predict(query)
        all_conf.append(r.confidence)
        all_cor.append(r.output == expected)

    full_brier = independent_brier(all_conf, all_cor)
    full_ece = independent_ece(all_conf, all_cor, n_bins=5)
    print(f"  Brier on full test ({len(test)} samples): {full_brier:.6f}")
    print(f"  ECE on full test:   {full_ece:.6f}")
    print(f"  Mean confidence:    {sum(all_conf)/len(all_conf):.4f}")
    print(f"  All correct:        {all(all_cor)}")

    return full_brier


# ======================================================================
# PHASE 2+3: Independent audit with strict separation
# ======================================================================

def _run_independent_audit():
    """Run the truly independent evaluation."""
    print("\n" + "=" * 70)
    print("PHASE 2+3: INDEPENDENT AUDIT (STRICT DATA SEPARATION)")
    print("=" * 70)

    train = _build_train()
    feedback = _build_feedback()
    calibration_data = _build_calibration()
    test_data = _build_held_out_test()

    print(f"\n  TRAIN:       {len(train)} samples (inserted into learner)")
    print(f"  FEEDBACK:    {len(feedback)} feedback entries")
    print(f"  CALIBRATION: {len(calibration_data)} samples (used ONLY for calibrator)")
    print(f"  HELD-OUT:    {len(test_data)} samples (NEVER used for anything else)")

    # Verify no overlap
    train_inputs = {obs["input"] for obs in train}
    cal_inputs = {q for q, _ in calibration_data}
    test_inputs = {q for q, _ in test_data}

    train_cal_overlap = train_inputs & cal_inputs
    train_test_overlap = train_inputs & test_inputs
    cal_test_overlap = cal_inputs & test_inputs

    print(f"\n  Train/Cal overlap:   {len(train_cal_overlap)}")
    print(f"  Train/Test overlap:  {len(train_test_overlap)}")
    print(f"  Cal/Test overlap:    {len(cal_test_overlap)}")

    if train_test_overlap:
        print(f"\n  *** LEAKAGE: {len(train_test_overlap)} test queries overlap with training! ***")
        for q in sorted(train_test_overlap):
            print(f"    - {q}")

    # Step 1: Train learner
    learner = _make_learner()
    _train_learner(learner, train, feedback)

    # Step 2: Evaluate on calibration data (to build calibrator)
    cal_confidences = []
    cal_correct = []
    for query, expected in calibration_data:
        r = learner.predict(query)
        cal_confidences.append(r.confidence)
        cal_correct.append(r.output == expected)

    # Step 3: Build calibration map from CALIBRATION data only
    cal_map = build_calibration_map(cal_confidences, cal_correct, n_bins=5, min_samples_per_bin=2)

    # Step 4: Evaluate on HELD-OUT test data
    raw_results = []
    for query, expected in test_data:
        r = learner.predict(query)
        raw_results.append({
            "query": query,
            "expected": expected,
            "predicted": r.output,
            "raw_confidence": r.confidence,
            "abstained": r.abstained,
            "uncertainty_state": r.uncertainty_state if r.confidence_result else "unknown",
        })

    # Step 5: Apply calibration to HELD-OUT data
    for result in raw_results:
        result["cal_confidence"] = calibrate(result["raw_confidence"], cal_map)

    # Step 6: Compute metrics
    raw_conf = [r["raw_confidence"] for r in raw_results]
    cal_conf = [r["cal_confidence"] for r in raw_results]
    correct = [r["predicted"] == r["expected"] for r in raw_results]

    raw_brier = independent_brier(raw_conf, correct)
    cal_brier = independent_brier(cal_conf, correct)
    raw_ece = independent_ece(raw_conf, correct, n_bins=5)
    cal_ece = independent_ece(cal_conf, correct, n_bins=5)
    accuracy = sum(correct) / len(correct)
    mean_raw = sum(raw_conf) / len(raw_conf)
    mean_cal = sum(cal_conf) / len(cal_conf)
    abstentions = sum(1 for r in raw_results if r["abstained"])

    print("\n  RESULTS:")
    print(f"  {'Metric':<25} {'Raw':>10} {'Calibrated':>10}")
    print(f"  {'-'*47}")
    print(f"  {'Brier':<25} {raw_brier:>10.4f} {cal_brier:>10.4f}")
    print(f"  {'ECE':<25} {raw_ece:>10.4f} {cal_ece:>10.4f}")
    print(f"  {'Accuracy':<25} {accuracy:>10.4f}")
    print(f"  {'Mean confidence':<25} {mean_raw:>10.4f} {mean_cal:>10.4f}")
    print(f"  {'Abstentions':<25} {abstentions:>10d}")
    print(f"  {'Coverage':<25} {(len(correct)-abstentions)/len(correct):>10.4f}")

    # Raw prediction table
    print(f"\n  RAW PREDICTION TABLE (all {len(raw_results)} samples):")
    print(f"  {'#':>3} {'Expected':<35} {'Predicted':<35} "
          f"{'Raw':>6} {'Cal':>6} {'Cor':>4} {'Abst':>5}")
    print(f"  {'-'*100}")
    for i, r in enumerate(raw_results):
        cor = "Y" if r["predicted"] == r["expected"] else "N"
        abst = "YES" if r["abstained"] else ""
        print(f"  {i:>3} {r['expected']:<35} {r['predicted']:<35} "
              f"{r['raw_confidence']:>6.3f} {r['cal_confidence']:>6.3f} {cor:>4} {abst:>5}")

    # Confidence distribution
    print("\n  CONFIDENCE DISTRIBUTION:")
    print(f"  Min:    {min(raw_conf):.4f}")
    print(f"  Max:    {max(raw_conf):.4f}")
    print(f"  Mean:   {sum(raw_conf)/len(raw_conf):.4f}")
    sorted_conf = sorted(raw_conf)
    median = sorted_conf[len(sorted_conf)//2]
    print(f"  Median: {median:.4f}")

    # Confidence for correct vs incorrect
    correct_confs = [c for c, cor in zip(raw_conf, correct, strict=False) if cor]
    incorrect_confs = [c for c, cor in zip(raw_conf, correct, strict=False) if not cor]
    print(f"\n  Correct predictions:   {len(correct_confs)} "
          f"(mean conf={sum(correct_confs)/max(1,len(correct_confs)):.4f})")
    print(f"  Incorrect predictions: {len(incorrect_confs)}")
    if incorrect_confs:
        print(f"    Confidence of incorrect: {[f'{c:.4f}' for c in incorrect_confs]}")
    else:
        print("    No incorrect predictions!")

    return raw_results, raw_brier, cal_brier


# ======================================================================
# PHASE 6: Abstention audit
# ======================================================================

def _abstention_audit():
    """Test abstention at multiple thresholds."""
    print("\n" + "=" * 70)
    print("PHASE 6: ABSTENTION AUDIT")
    print("=" * 70)

    thresholds = [0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9]
    train = _build_train()
    feedback = _build_feedback()
    test_data = _build_held_out_test()

    print(f"\n  {'Threshold':>10} {'Coverage':>10} {'Accuracy':>10} "
          f"{'AbstRate':>10} {'Brier':>10} {'IncorrNonAbst':>15}")
    print(f"  {'-'*70}")

    for threshold in thresholds:
        learner = _make_learner(abstention_threshold=threshold)
        _train_learner(learner, train, feedback)

        confidences = []
        correct = []
        abstentions = 0

        for query, expected in test_data:
            r = learner.predict(query)
            confidences.append(r.confidence)
            correct.append(r.output == expected)
            if r.abstained:
                abstentions += 1

        n = len(test_data)
        coverage = (n - abstentions) / n
        accuracy = sum(correct) / n if n > 0 else 0.0
        abst_rate = abstentions / n if n > 0 else 0.0
        brier = independent_brier(confidences, correct)

        # Incorrect among non-abstained
        [c for c, a in zip(correct, [r["abstained"] for r in [{"abstained": False}] * n],
                           strict=False) if not a]
        incorr_non_abst = n - abstentions - sum(correct)

        print(f"  {threshold:>10.1f} {coverage:>10.4f} {accuracy:>10.4f} "
              f"{abst_rate:>10.4f} {brier:>10.4f} {incorr_non_abst:>15d}")


# ======================================================================
# PHASE 7: Independence test
# ======================================================================

def _independence_test():
    """Test that duplicates don't inflate confidence like independent evidence."""
    print("\n" + "=" * 70)
    print("PHASE 7: ADVERSARIAL INDEPENDENCE TEST")
    print("=" * 70)

    # Baseline: 1 memory
    scenarios = [
        ("1 memory", 1),
        ("3 duplicates", 3),
        ("10 duplicates", 10),
        ("30 duplicates", 30),
    ]

    print(f"\n  {'Scenario':<20} {'Confidence':>12} {'Indep.Evidence':>15}")
    print(f"  {'-'*50}")

    for name, n_dupes in scenarios:
        learner = _make_learner()
        for _ in range(n_dupes):
            learner.learn(LearningInput(
                observation={"input": "sort a list", "output": "sorted(x)"}))
        for _ in range(5):
            learner.feedback("sort a list", "sorted(x)", correct=True)

        r = learner.predict("sort a list")
        indep = (r.confidence_components.get("independent_evidence_count", 0)
                 if r.confidence_result else 0)
        print(f"  {name:<20} {r.confidence:>12.4f} {indep:>15d}")

    # Now test genuine independent evidence
    print("\n  Genuine independent memories:")
    print(f"  {'Scenario':<20} {'Confidence':>12} {'Indep.Evidence':>15}")
    print(f"  {'-'*50}")

    for n_ind in [1, 3, 5, 10]:
        learner = _make_learner()
        for i in range(n_ind):
            learner.learn(LearningInput(
                observation={"input": f"sort task {i}", "output": "sorted(x)"}))
        for i in range(n_ind):
            learner.feedback(f"sort task {i}", "sorted(x)", correct=True)

        # Query one of them
        r = learner.predict("sort task 0")
        indep = (r.confidence_components.get("independent_evidence_count", 0)
                 if r.confidence_result else 0)
        print(f"  {n_ind} independent{'':<14} {r.confidence:>12.4f} {indep:>15d}")


# ======================================================================
# PHASE 8: Calibration leakage test
# ======================================================================

def _calibration_leakage_test():
    """Compare calibration on independent data vs on evaluation data."""
    print("\n" + "=" * 70)
    print("PHASE 8: CALIBRATION LEAKAGE TEST")
    print("=" * 70)

    train = _build_train()
    feedback = _build_feedback()
    calibration_data = _build_calibration()
    test_data = _build_held_out_test()

    # Experiment A: Calibration on independent calibration data
    learner_a = _make_learner()
    _train_learner(learner_a, train, feedback)

    cal_conf_a = []
    cal_cor_a = []
    for query, expected in calibration_data:
        r = learner_a.predict(query)
        cal_conf_a.append(r.confidence)
        cal_cor_a.append(r.output == expected)
    cal_map_a = build_calibration_map(cal_conf_a, cal_cor_a, n_bins=5, min_samples_per_bin=2)

    test_conf_a = []
    test_cor_a = []
    for query, expected in test_data:
        r = learner_a.predict(query)
        raw = r.confidence
        cal = calibrate(raw, cal_map_a)
        test_conf_a.append(cal)
        test_cor_a.append(r.output == expected)

    brier_a = independent_brier(test_conf_a, test_cor_a)
    ece_a = independent_ece(test_conf_a, test_cor_a, n_bins=5)

    # Experiment B: Calibration on the evaluation data itself (LEAKAGE)
    test_conf_raw = []
    test_cor_raw = []
    for query, expected in test_data:
        r = learner_a.predict(query)
        test_conf_raw.append(r.confidence)
        test_cor_raw.append(r.output == expected)

    cal_map_b = build_calibration_map(test_conf_raw, test_cor_raw, n_bins=5, min_samples_per_bin=2)
    test_conf_b = [calibrate(c, cal_map_b) for c in test_conf_raw]

    brier_b = independent_brier(test_conf_b, test_cor_raw)
    ece_b = independent_ece(test_conf_b, test_cor_raw, n_bins=5)

    print("\n  Experiment A (calibration on INDEPENDENT data):")
    print(f"    Brier: {brier_a:.6f}")
    print(f"    ECE:   {ece_a:.6f}")

    print("\n  Experiment B (calibration on EVALUATION data = LEAKAGE):")
    print(f"    Brier: {brier_b:.6f}")
    print(f"    ECE:   {ece_b:.6f}")

    print("\n  Difference:")
    print(f"    Brier: {abs(brier_a - brier_b):.6f}")
    print(f"    ECE:   {abs(ece_a - ece_b):.6f}")

    if abs(ece_a - ece_b) > 0.05:
        print("\n  *** SIGNIFICANT LEAKAGE DETECTED: ECE difference > 0.05 ***")
    else:
        print("\n  Leakage difference is small (< 0.05).")


# ======================================================================
# PHASE 9: Randomization test
# ======================================================================

def _randomization_test():
    """Test stability across different orderings."""
    print("\n" + "=" * 70)
    print("PHASE 9: RANDOMIZATION TEST")
    print("=" * 70)

    train = _build_train()
    feedback = _build_feedback()
    test_data = _build_held_out_test()

    results = []
    for seed in [42, 123, 456, 789, 1000]:
        random.seed(seed)
        learner = _make_learner()

        # Shuffle training order
        shuffled_train = train.copy()
        random.shuffle(shuffled_train)
        _train_learner(learner, shuffled_train, feedback)

        # Shuffle test order
        shuffled_test = test_data.copy()
        random.shuffle(shuffled_test)

        confidences = []
        correct = []
        for query, expected in shuffled_test:
            r = learner.predict(query)
            confidences.append(r.confidence)
            correct.append(r.output == expected)

        brier = independent_brier(confidences, correct)
        ece = independent_ece(confidences, correct, n_bins=5)
        acc = sum(correct) / len(correct)
        results.append((seed, brier, ece, acc))

    print(f"\n  {'Seed':>6} {'Brier':>10} {'ECE':>10} {'Accuracy':>10}")
    print(f"  {'-'*38}")
    for seed, brier, ece, acc in results:
        print(f"  {seed:>6} {brier:>10.4f} {ece:>10.4f} {acc:>10.4f}")

    briers = [r[1] for r in results]
    eces = [r[2] for r in results]
    print(f"\n  Brier range: {min(briers):.4f} - {max(briers):.4f} (std={stdev(briers):.4f})")
    print(f"  ECE range:   {min(eces):.4f} - {max(eces):.4f} (std={stdev(eces):.4f})")

    if max(briers) - min(briers) > 0.1:
        print("\n  *** UNSTABLE: Brier varies by > 0.1 across seeds ***")
    else:
        print("\n  Results are stable across seeds.")


def stdev(values):
    """Simple standard deviation."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / (n - 1)
    return math.sqrt(variance)


# ======================================================================
# MAIN
# ======================================================================

def main():
    print("=" * 70)
    print("V2.3.3 INDEPENDENT CALIBRATION AUDIT")
    print("=" * 70)

    # Phase 4: Metric verification
    brier_match, ece_match = _verify_metrics()

    # Phase 5: Why Brier=0.000?
    existing_brier = _investigate_brier()

    # Phase 2+3: Independent audit
    raw_results, ind_brier, ind_cal_brier = _run_independent_audit()

    # Phase 6: Abstention audit
    _abstention_audit()

    # Phase 7: Independence test
    _independence_test()

    # Phase 8: Calibration leakage
    _calibration_leakage_test()

    # Phase 9: Randomization
    _randomization_test()

    # Summary
    print("\n" + "=" * 70)
    print("AUDIT SUMMARY")
    print("=" * 70)
    print(f"\n  Metrics match production: Brier={'YES' if brier_match else 'NO'}, "
          f"ECE={'YES' if ece_match else 'NO'}")
    print(f"  Existing benchmark Brier (Dataset A): {existing_brier:.6f}")
    print(f"  Independent audit Brier (raw):        {ind_brier:.6f}")
    print(f"  Independent audit Brier (calibrated): {ind_cal_brier:.6f}")

    correct = [r["predicted"] == r["expected"] for r in raw_results]
    abstentions = sum(1 for r in raw_results if r["abstained"])
    print(f"  Accuracy: {sum(correct)/len(correct):.4f}")
    print(f"  Abstention rate: {abstentions/len(raw_results):.4f}")

    print("\nDone.")


if __name__ == "__main__":
    main()
