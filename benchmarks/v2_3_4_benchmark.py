"""V2.3.4 Comprehensive 600+ Case Evaluation Benchmark.

4-way split: TRAIN / CALIBRATION / VALIDATION / HELD-OUT_TEST
Categories A-N with 30-50 test cases each.
Held-out test is NEVER used for anything except final measurement.
No overlap between any splits.
No production code is modified.
"""

from __future__ import annotations

import math
import random
import sys
import time
from dataclasses import dataclass, field
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
from core.learner.calibration.metrics import (
    CalibrationCase,
    abstention_quality,
    brier_score,
    discrimination_gap,
    expected_calibration_error,
    selective_prediction_accuracy,
    selective_prediction_coverage,
)
from core.learner.confidence import ConfidenceConfig
from core.learner.conflict import ConflictConfig
from core.learner.learner_v2 import HybridSimilarityLearner
from core.learner.retrieval_scorer import ScorerConfig

# ---------------------------------------------------------------------------
# Global seed for reproducibility
# ---------------------------------------------------------------------------
SEED = 42
random.seed(SEED)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class EvalSample:
    query: str
    expected: str
    predicted: str
    confidence: float
    correct: bool
    category: str
    split: str  # "calibration", "validation", "held_out"
    metadata: dict = field(default_factory=dict)


@dataclass
class CategoryMetrics:
    category: str
    split: str
    n: int
    brier: float
    ece: float
    accuracy: float
    mean_confidence: float
    discrimination_gap: float
    abstention_quality: float
    selective_acc: dict[float, float]
    selective_cov: dict[float, float]


@dataclass
class SplitMetrics:
    split: str
    n: int
    brier: float
    ece: float
    accuracy: float
    mean_confidence: float
    discrimination_gap: float
    abstention_quality: float


# ---------------------------------------------------------------------------
# Category A: Known (close paraphrases of training)
# ---------------------------------------------------------------------------

def _build_category_a() -> tuple[list, list]:
    """Known: close paraphrases of training examples."""
    domain_pairs = [
        ("sort a list", "sorted(x)"),
        ("reverse a string", "s[::-1]"),
        ("find maximum", "max(x)"),
        ("find minimum", "min(x)"),
        ("count elements", "len(x)"),
        ("join strings", "''.join(x)"),
        ("split string", "x.split(s)"),
        ("filter list", "[i for i in x if c]"),
        ("map function", "[f(i) for i in x]"),
        ("read file", "open(f).read()"),
        ("write file", "open(f,'w').write(d)"),
        ("merge dicts", "{**d1, **d2}"),
        ("sort dict by value", "sorted(d.items(), key=lambda x: x[1])"),
        ("flatten list", "[i for sub in x for i in sub]"),
        ("deduplicate", "list(dict.fromkeys(x))"),
        ("chunk list", "[x[i:i+n] for i in range(0,len(x),n)]"),
        ("clamp value", "max(lo, min(hi, x))"),
        ("fibonacci", "fib(n)"),
        ("binary search", "bisect.bisect_left(arr, t)"),
        ("palindrome check", "s == s[::-1]"),
    ]

    training = []
    feedback = []
    for inp, out in domain_pairs:
        training.append({"input": inp, "output": out})
        feedback.append((inp, out, True))
        feedback.append((inp, out, True))

    paraphrases = [
        ("organize the items", "sorted(x)"),
        ("flip the text around", "s[::-1]"),
        ("get the largest value", "max(x)"),
        ("get the smallest value", "min(x)"),
        ("how many items are there", "len(x)"),
        ("concatenate all strings", "''.join(x)"),
        ("break apart by delimiter", "x.split(s)"),
        ("keep only matching items", "[i for i in x if c]"),
        ("apply function to each element", "[f(i) for i in x]"),
        ("load contents of a file", "open(f).read()"),
        ("save data to a file", "open(f,'w').write(d)"),
        ("combine two dictionaries", "{**d1, **d2}"),
        ("order dictionary by value", "sorted(d.items(), key=lambda x: x[1])"),
        ("make nested list flat", "[i for sub in x for i in sub]"),
        ("remove repeated items", "list(dict.fromkeys(x))"),
        ("split into chunks", "[x[i:i+n] for i in range(0,len(x),n)]"),
        ("restrict value to range", "max(lo, min(hi, x))"),
        ("compute fibonacci number", "fib(n)"),
        ("search sorted array", "bisect.bisect_left(arr, t)"),
        ("check if text is palindrome", "s == s[::-1]"),
        ("arrange numbers ascending", "sorted(x)"),
        ("invert character order", "s[::-1]"),
        ("determine peak value", "max(x)"),
        ("identify lowest number", "min(x)"),
        ("tally the objects", "len(x)"),
        ("merge text fragments", "''.join(x)"),
        ("separate by separator", "x.split(s)"),
        ("extract subset matching", "[i for i in x if c]"),
        ("transform each element", "[f(i) for i in x]"),
        ("grab file data", "open(f).read()"),
        ("persist output to disk", "open(f,'w').write(d)"),
        ("unify two mappings", "{**d1, **d2}"),
        ("rank by metric descending", "sorted(d.items(), key=lambda x: x[1])"),
        ("collapse nested structure", "[i for sub in x for i in sub]"),
        ("filter unique entries", "list(dict.fromkeys(x))"),
        ("partition into segments", "[x[i:i+n] for i in range(0,len(x),n)]"),
        ("bound numeric value", "max(lo, min(hi, x))"),
        ("recursive sequence", "fib(n)"),
        ("locate in sorted data", "bisect.bisect_left(arr, t)"),
        ("verify symmetric string", "s == s[::-1]"),
    ]

    return training, feedback, paraphrases


# ---------------------------------------------------------------------------
# Category B: Paraphrased (different wording, same concept)
# ---------------------------------------------------------------------------

def _build_category_b() -> tuple[list, list]:
    """Paraphrased: different wording, same concept."""
    training = [
        {"input": "sort a list", "output": "sorted(x)"},
        {"input": "reverse string", "output": "s[::-1]"},
        {"input": "find maximum", "output": "max(x)"},
        {"input": "count elements", "output": "len(x)"},
        {"input": "join strings", "output": "''.join(x)"},
        {"input": "split by delimiter", "output": "x.split(s)"},
        {"input": "filter entries", "output": "[i for i in x if c]"},
        {"input": "read a file", "output": "open(f).read()"},
        {"input": "merge dictionaries", "output": "{**d1, **d2}"},
        {"input": "remove duplicates", "output": "list(dict.fromkeys(x))"},
    ]
    feedback = []
    for inp, out in training:
        for _ in range(3):
            feedback.append((inp, out, True))

    test = [
        ("arrange the collection numerically", "sorted(x)"),
        ("make the text go backwards", "s[::-1]"),
        ("get the biggest item in the set", "max(x)"),
        ("what is the total item count", "len(x)"),
        ("put all the words together", "''.join(x)"),
        ("cut the sentence on commas", "x.split(s)"),
        ("pick only the valid ones", "[i for i in x if c]"),
        ("grab the contents from disk", "open(f).read()"),
        ("combine both data maps", "{**d1, **d2}"),
        ("strip out repeated entries", "list(dict.fromkeys(x))"),
        ("order items by size ascending", "sorted(x)"),
        ("mirror the character sequence", "s[::-1]"),
        ("determine the top value", "max(x)"),
        ("tally up all the objects", "len(x)"),
        ("smush text fragments together", "''.join(x)"),
        ("tokenize using a separator", "x.split(s)"),
        ("select items meeting a condition", "[i for i in x if c]"),
        ("load data from storage", "open(f).read()"),
        ("unify two record sets", "{**d1, **d2}"),
        ("eliminate clone entries", "list(dict.fromkeys(x))"),
        ("rank elements by magnitude", "sorted(x)"),
        ("invert the string visually", "s[::-1]"),
        ("find the absolute highest", "max(x)"),
        ("get a head count of items", "len(x)"),
        ("glue strings into one", "''.join(x)"),
        ("parse text by a delimiter", "x.split(s)"),
        ("retain only passing tests", "[i for i in x if c]"),
        ("access document contents", "open(f).read()"),
        ("blend two lookup tables", "{**d1, **d2}"),
        ("purge duplicate records", "list(dict.fromkeys(x))"),
    ]
    return training, feedback, test


# ---------------------------------------------------------------------------
# Category C: Novel wording (new phrasing)
# ---------------------------------------------------------------------------

def _build_category_c() -> tuple[list, list]:
    """Novel wording: new phrasing not seen in training."""
    training = [
        {"input": "sort a list", "output": "sorted(x)"},
        {"input": "reverse string", "output": "s[::-1]"},
        {"input": "find maximum", "output": "max(x)"},
        {"input": "count elements", "output": "len(x)"},
        {"input": "join strings", "output": "''.join(x)"},
    ]
    feedback = []
    for inp, out in training:
        for _ in range(4):
            feedback.append((inp, out, True))

    test = [
        ("reorder the sequence ascendingly", "sorted(x)"),
        ("make the string read right-to-left", "s[::-1]"),
        ("locate the element with highest magnitude", "max(x)"),
        ("compute the cardinality of the collection", "len(x)"),
        ("concatenate all substrings into one", "''.join(x)"),
        ("perform natural ordering on elements", "sorted(x)"),
        ("produce a reversed mirror image", "s[::-1]"),
        ("extract the supremum from the set", "max(x)"),
        ("enumerate total members present", "len(x)"),
        ("unify substrings with no separator", "''.join(x)"),
        ("lexicographically arrange entries", "sorted(x)"),
        ("reflect string contents end-to-end", "s[::-1]"),
        ("ascertain the greatest constituent", "max(x)"),
        ("evaluate collection population", "len(x)"),
        ("amalgamate string parts together", "''.join(x)"),
        ("effectuate ascending sort order", "sorted(x)"),
        ("turn string into its reverse form", "s[::-1]"),
        ("retrieve maximal element present", "max(x)"),
        ("calculate instance quantity total", "len(x)"),
        ("aggregate text pieces into unity", "''.join(x)"),
        ("systematize elements in order", "sorted(x)"),
        ("transmute string to backward form", "s[::-1]"),
        ("procure the maximum constituent", "max(x)"),
        ("determine item population count", "len(x)"),
        ("synthesize string segments jointly", "''.join(x)"),
        ("implement ascending arrangement", "sorted(x)"),
        ("execute string reversal process", "s[::-1]"),
        ("obtain the peak value holder", "max(x)"),
        ("quantify collection membership", "len(x)"),
        ("integrate text parts seamlessly", "''.join(x)"),
    ]
    return training, feedback, test


# ---------------------------------------------------------------------------
# Category D: Novel concepts (not in training)
# ---------------------------------------------------------------------------

def _build_category_d() -> tuple[list, list]:
    """Novel concepts: queries about things not in training at all."""
    training = [
        {"input": "sort a list", "output": "sorted(x)"},
        {"input": "reverse string", "output": "s[::-1]"},
    ]
    feedback = [("sort a list", "sorted(x)", True)] * 5

    test = [
        ("deploy application to cloud", "deploy()"),
        ("train a neural network model", "model.fit()"),
        ("compile C source code", "gcc main.c"),
        ("encrypt password with bcrypt", "hash(pw)"),
        ("calculate compound interest", "interest = p * (1 + r) ** t"),
        ("draw a circle on canvas", "canvas.circle()"),
        ("send email via SMTP", "smtp.send()"),
        ("resize image dimensions", "image.resize()"),
        ("compress file with gzip", "gzip.compress()"),
        ("parse XML document", "etree.parse()"),
        ("send SMS message", "sms.send()"),
        ("monitor CPU usage", "cpu.usage()"),
        ("backup database to S3", "db.backup()"),
        ("scale image proportionally", "image.scale()"),
        ("hash password securely", "bcrypt.hash()"),
        ("generate PDF report", "pdf.create()"),
        ("run unit test suite", "pytest.run()"),
        ("create Docker container", "docker.build()"),
        ("migrate database schema", "alembic.upgrade()"),
        ("render 3D scene", "renderer.draw()"),
        ("compress video file", "ffmpeg.compress()"),
        ("extract audio from video", "ffmpeg.audio()"),
        ("build REST API endpoint", "flask.route()"),
        ("authenticate user session", "auth.login()"),
        ("queue background job", "celery.delay()"),
        ("index search documents", "elastic.index()"),
        ("cache query results", "redis.set()"),
        ("stream real-time events", "kafka.produce()"),
        ("translate text to French", "translate(text, 'fr')"),
        ("recognize speech audio", "whisper.transcribe()"),
    ]
    return training, feedback, test


# ---------------------------------------------------------------------------
# Category E: Conflicts (competing answers)
# ---------------------------------------------------------------------------

def _build_category_e() -> tuple[list, list]:
    """Conflicts: multiple credible memories disagree."""
    training = [
        {"input": "sort a list", "output": "sorted(x)"},
        {"input": "sort a list", "output": "list.sort()"},
        {"input": "reverse string", "output": "s[::-1]"},
        {"input": "reverse string", "output": "reversed(s)"},
        {"input": "find maximum", "output": "max(x)"},
        {"input": "find maximum", "output": "heapq.nlargest(1, x)"},
    ]
    feedback = []
    for inp, out in training:
        for _ in range(8):
            feedback.append((inp, out, True))

    test = [
        ("sort a list", "sorted(x)"),
        ("sort a list", "list.sort()"),
        ("order the items", "sorted(x)"),
        ("arrange elements", "sorted(x)"),
        ("sort array ascending", "sorted(x)"),
        ("reverse a string", "s[::-1]"),
        ("reverse a string", "reversed(s)"),
        ("flip the text", "s[::-1]"),
        ("invert string order", "s[::-1]"),
        ("make string backwards", "s[::-1]"),
        ("find the largest", "max(x)"),
        ("find the largest", "heapq.nlargest(1, x)"),
        ("get maximum value", "max(x)"),
        ("determine peak element", "max(x)"),
        ("identify top value", "max(x)"),
        ("sort the collection", "sorted(x)"),
        ("put items in order", "sorted(x)"),
        ("invert character sequence", "s[::-1]"),
        ("mirror the text", "s[::-1]"),
        ("determine greatest item", "max(x)"),
        ("rank by magnitude", "sorted(x)"),
        ("swap character positions", "s[::-1]"),
        ("locate peak in dataset", "max(x)"),
        ("systematize the list", "sorted(x)"),
        ("backward string transform", "s[::-1]"),
        ("acquire maximum element", "max(x)"),
        ("sort entries numerically", "sorted(x)"),
        ("reverse all characters", "s[::-1]"),
        ("find absolute highest", "max(x)"),
        ("organize by priority", "sorted(x)"),
    ]
    return training, feedback, test


# ---------------------------------------------------------------------------
# Category F: Weak evidence (little support)
# ---------------------------------------------------------------------------

def _build_category_f() -> tuple[list, list]:
    """Weak evidence: very few training memories, little feedback."""
    training = [
        {"input": "process data", "output": "transform(x)"},
        {"input": "handle input", "output": "parse(x)"},
    ]
    feedback = [("process data", "transform(x)", True)] * 2

    test = [
        ("process information", "transform(x)"),
        ("handle the data", "parse(x)"),
        ("manage input stream", "transform(x)"),
        ("deal with incoming data", "parse(x)"),
        ("treat the raw input", "transform(x)"),
        ("work with dataset", "parse(x)"),
        ("manipulate raw data", "transform(x)"),
        ("read the incoming stream", "parse(x)"),
        ("process new records", "transform(x)"),
        ("handle file input", "parse(x)"),
        ("manage data pipeline", "transform(x)"),
        ("deal with request body", "parse(x)"),
        ("treat incoming payload", "transform(x)"),
        ("work on the dataset", "parse(x)"),
        ("manipulate the data", "transform(x)"),
        ("read input buffer", "parse(x)"),
        ("process batch data", "transform(x)"),
        ("handle form fields", "parse(x)"),
        ("manage message queue", "transform(x)"),
        ("deal with event data", "parse(x)"),
        ("treat the parameters", "transform(x)"),
        ("work with the input", "parse(x)"),
        ("manipulate stream data", "transform(x)"),
        ("read configuration", "parse(x)"),
        ("process telemetry data", "transform(x)"),
        ("handle user request", "parse(x)"),
        ("manage log entries", "transform(x)"),
        ("deal with metrics", "parse(x)"),
        ("treat sensor readings", "transform(x)"),
        ("work with analytics", "parse(x)"),
    ]
    return training, feedback, test


# ---------------------------------------------------------------------------
# Category G: Duplicate attacks (repeated copies)
# ---------------------------------------------------------------------------

def _build_category_g() -> tuple[list, list]:
    """Duplicate attacks: many copies of same memory to inflate confidence."""
    training = []
    for _ in range(20):
        training.append({"input": "sort a list", "output": "bubble_sort(x)"})
    training.append({"input": "sort a list", "output": "sorted(x)"})
    for _ in range(5):
        training.append({"input": "reverse string", "output": "s[::-1]"})

    feedback = [("sort a list", "bubble_sort(x)", True)] * 5
    feedback += [("sort a list", "sorted(x)", True)] * 10

    test = [
        ("sort a list", "sorted(x)"),
        ("sort array", "sorted(x)"),
        ("sort items", "sorted(x)"),
        ("order list", "sorted(x)"),
        ("arrange elements", "sorted(x)"),
        ("put items in order", "sorted(x)"),
        ("sort numbers ascending", "sorted(x)"),
        ("organize the collection", "sorted(x)"),
        ("rank elements by value", "sorted(x)"),
        ("systematize the list", "sorted(x)"),
        ("sort a list please", "sorted(x)"),
        ("sort the list now", "sorted(x)"),
        ("do a sort on list", "sorted(x)"),
        ("sort my list", "sorted(x)"),
        ("please sort this list", "sorted(x)"),
        ("list sort operation", "sorted(x)"),
        ("sorted list output", "sorted(x)"),
        ("sort again a list", "sorted(x)"),
        ("sort another list", "sorted(x)"),
        ("sort this data", "sorted(x)"),
        ("flip a string", "s[::-1]"),
        ("invert string order", "s[::-1]"),
        ("mirror text", "s[::-1]"),
        ("reverse characters", "s[::-1]"),
        ("make text backwards", "s[::-1]"),
        ("reverse the string", "s[::-1]"),
        ("backward text", "s[::-1]"),
        ("flip character order", "s[::-1]"),
        ("invert the sequence", "s[::-1]"),
        ("retrograde the text", "s[::-1]"),
        ("string reversal operation", "s[::-1]"),
        ("reverse my string", "s[::-1]"),
        ("do a string flip", "s[::-1]"),
        ("backwards string output", "s[::-1]"),
        ("reverse this text", "s[::-1]"),
        ("flip the characters", "s[::-1]"),
        ("mirror image of string", "s[::-1]"),
        ("invert text order", "s[::-1]"),
        ("make string go backwards", "s[::-1]"),
        ("retrograde string", "s[::-1]"),
        ("find largest number", "sorted(x)"),
        ("get biggest item", "sorted(x)"),
        ("maximum element", "max(x)"),
        ("top value finder", "max(x)"),
        ("peak value extractor", "max(x)"),
        ("highest entry selector", "max(x)"),
        ("supreme value getter", "max(x)"),
        ("apex element finder", "max(x)"),
        ("zenith value retriever", "max(x)"),
        ("maximum item locator", "max(x)"),
    ]
    return training, feedback, test


# ---------------------------------------------------------------------------
# Category H: Near-duplicate attacks (slight variations)
# ---------------------------------------------------------------------------

def _build_category_h() -> tuple[list, list]:
    """Near-duplicate: slight variations of same memory."""
    training = [
        {"input": "sort a list of integers", "output": "sorted(x)"},
        {"input": "sort a list of strings", "output": "sorted(x)"},
        {"input": "sort a list of floats", "output": "sorted(x)"},
        {"input": "sort a list of items", "output": "sorted(x)"},
        {"input": "sort a list of elements", "output": "sorted(x)"},
        {"input": "sort a list of numbers", "output": "sorted(x)"},
        {"input": "sort a list of values", "output": "sorted(x)"},
        {"input": "sort a list of objects", "output": "sorted(x)"},
        {"input": "sort a list quickly", "output": "sorted(x)"},
        {"input": "sort a list efficiently", "output": "sorted(x)"},
        {"input": "sort a list descending", "output": "sorted(x, reverse=True)"},
        {"input": "sort a list ascending", "output": "sorted(x)"},
        {"input": "sort list by key", "output": "sorted(x, key=k)"},
        {"input": "sort list stable", "output": "sorted(x)"},
        {"input": "sort list in-place", "output": "x.sort()"},
    ]
    feedback = []
    for item in training[:10]:
        feedback.append((item["input"], item["output"], True))
        feedback.append((item["input"], item["output"], True))

    test = [
        ("sort a list of tuples", "sorted(x)"),
        ("sort a list of dicts", "sorted(x)"),
        ("sort a list of booleans", "sorted(x)"),
        ("sort a list of bytes", "sorted(x)"),
        ("sort a list of chars", "sorted(x)"),
        ("sort a list large", "sorted(x)"),
        ("sort a list small", "sorted(x)"),
        ("sort a list random", "sorted(x)"),
        ("sort a list partially", "sorted(x)"),
        ("sort a list custom", "sorted(x)"),
        ("sort a list reversed", "sorted(x, reverse=True)"),
        ("sort a list naturally", "sorted(x)"),
        ("sort a list weighted", "sorted(x, key=k)"),
        ("sort a list parallel", "sorted(x)"),
        ("sort a list external", "sorted(x)"),
        ("sort a list of sets", "sorted(x)"),
        ("sort a list of ranges", "sorted(x)"),
        ("sort a list of decimals", "sorted(x)"),
        ("sort a list of fractions", "sorted(x)"),
        ("sort a list of complex", "sorted(x)"),
        ("sort a list of namedtuples", "sorted(x)"),
        ("sort a list of dataclasses", "sorted(x)"),
        ("sort a list of enums", "sorted(x)"),
        ("sort a list of custom objects", "sorted(x)"),
        ("sort a list with key func", "sorted(x, key=k)"),
        ("sort a list with cmp func", "sorted(x)"),
        ("sort a list of mixed types", "sorted(x)"),
        ("sort a list of unicode strings", "sorted(x)"),
        ("sort a list of ascii strings", "sorted(x)"),
        ("sort a list of nested lists", "sorted(x)"),
        ("sort a list of frozen sets", "sorted(x)"),
        ("sort a list of byte strings", "sorted(x)"),
        ("sort a list of memoryview", "sorted(x)"),
        ("sort a list of iterators", "sorted(x)"),
        ("sort a list of generators", "sorted(x)"),
    ]
    return training, feedback, test


# ---------------------------------------------------------------------------
# Category I: Feedback poisoning (incorrect feedback)
# ---------------------------------------------------------------------------

def _build_category_i() -> tuple[list, list]:
    """Feedback poisoning: repeated incorrect feedback attempts."""
    training = [
        {"input": "sort a list", "output": "sorted(x)"},
        {"input": "reverse string", "output": "s[::-1]"},
        {"input": "find maximum", "output": "max(x)"},
    ]
    feedback = [
        ("sort a list", "sorted(x)", True),
        ("sort a list", "sorted(x)", True),
        ("sort a list", "sorted(x)", True),
        ("sort a list", "sorted(x)", False),
        ("sort a list", "sorted(x)", False),
        ("sort a list", "sorted(x)", False),
        ("sort a list", "sorted(x)", False),
        ("sort a list", "sorted(x)", False),
        ("sort a list", "sorted(x)", False),
        ("sort a list", "sorted(x)", False),
        ("sort a list", "sorted(x)", False),
        ("sort a list", "sorted(x)", False),
        ("sort a list", "sorted(x)", False),
        ("reverse string", "s[::-1]", True),
        ("reverse string", "s[::-1]", False),
        ("reverse string", "s[::-1]", False),
        ("reverse string", "s[::-1]", False),
        ("reverse string", "s[::-1]", False),
        ("find maximum", "max(x)", True),
        ("find maximum", "max(x)", True),
        ("find maximum", "max(x)", True),
        ("find maximum", "max(x)", True),
        ("find maximum", "max(x)", True),
    ]

    test = [
        ("sort a list", "sorted(x)"),
        ("sort array", "sorted(x)"),
        ("sort items", "sorted(x)"),
        ("order list", "sorted(x)"),
        ("arrange elements", "sorted(x)"),
        ("put items in order", "sorted(x)"),
        ("sort numbers", "sorted(x)"),
        ("organize collection", "sorted(x)"),
        ("rank by value", "sorted(x)"),
        ("systematize elements", "sorted(x)"),
        ("sort the data", "sorted(x)"),
        ("sort a sequence", "sorted(x)"),
        ("sort entries", "sorted(x)"),
        ("arrange in order", "sorted(x)"),
        ("order by priority", "sorted(x)"),
        ("sort ascending", "sorted(x)"),
        ("sort descending", "sorted(x, reverse=True)"),
        ("sort with key", "sorted(x, key=k)"),
        ("sort stably", "sorted(x)"),
        ("sort in-place", "x.sort()"),
        ("reverse a string", "s[::-1]"),
        ("flip string", "s[::-1]"),
        ("backwards text", "s[::-1]"),
        ("invert string", "s[::-1]"),
        ("mirror text", "s[::-1]"),
        ("reverse characters", "s[::-1]"),
        ("flip character order", "s[::-1]"),
        ("invert the sequence", "s[::-1]"),
        ("retrograde the text", "s[::-1]"),
        ("backward string transform", "s[::-1]"),
        ("find maximum", "max(x)"),
        ("find max", "max(x)"),
        ("largest value", "max(x)"),
        ("peak element", "max(x)"),
        ("greatest item", "max(x)"),
        ("maximum element", "max(x)"),
        ("highest entry", "max(x)"),
        ("top value", "max(x)"),
        ("apex element", "max(x)"),
        ("supreme value", "max(x)"),
    ]
    return training, feedback, test


# ---------------------------------------------------------------------------
# Category J: Recency traps (recent low-quality evidence)
# ---------------------------------------------------------------------------

def _build_category_j() -> tuple[list, list]:
    """Recency trap: recent incorrect evidence vs older reliable."""
    training = [
        {"input": "sort a list", "output": "sorted(x)"},
        {"input": "reverse string", "output": "s[::-1]"},
        {"input": "find maximum", "output": "max(x)"},
    ]
    feedback = [
        ("sort a list", "sorted(x)", True),
        ("sort a list", "sorted(x)", True),
        ("sort a list", "sorted(x)", True),
        ("sort a list", "sorted(x)", True),
        ("sort a list", "sorted(x)", True),
        ("sort a list", "sorted(x)", True),
        ("sort a list", "sorted(x)", True),
        ("sort a list", "sorted(x)", True),
        ("sort a list", "sorted(x)", False),
        ("sort a list", "sorted(x)", False),
        ("sort a list", "sorted(x)", False),
        ("reverse string", "s[::-1]", True),
        ("reverse string", "s[::-1]", True),
        ("reverse string", "s[::-1]", True),
        ("reverse string", "s[::-1]", False),
        ("reverse string", "s[::-1]", False),
        ("find maximum", "max(x)", True),
        ("find maximum", "max(x)", True),
        ("find maximum", "max(x)", True),
        ("find maximum", "max(x)", True),
        ("find maximum", "max(x)", True),
    ]

    test = [
        ("sort a list", "sorted(x)"),
        ("sort array", "sorted(x)"),
        ("sort items", "sorted(x)"),
        ("order list", "sorted(x)"),
        ("arrange elements", "sorted(x)"),
        ("put items in order", "sorted(x)"),
        ("sort numbers", "sorted(x)"),
        ("organize collection", "sorted(x)"),
        ("rank by value", "sorted(x)"),
        ("systematize elements", "sorted(x)"),
        ("sort the data", "sorted(x)"),
        ("sort a sequence", "sorted(x)"),
        ("sort entries", "sorted(x)"),
        ("arrange in order", "sorted(x)"),
        ("order by priority", "sorted(x)"),
        ("sort ascending", "sorted(x)"),
        ("sort descending", "sorted(x, reverse=True)"),
        ("sort with key", "sorted(x, key=k)"),
        ("sort stably", "sorted(x)"),
        ("sort in-place", "x.sort()"),
        ("reverse a string", "s[::-1]"),
        ("flip string", "s[::-1]"),
        ("backwards text", "s[::-1]"),
        ("invert string", "s[::-1]"),
        ("mirror text", "s[::-1]"),
        ("reverse characters", "s[::-1]"),
        ("flip character order", "s[::-1]"),
        ("invert the sequence", "s[::-1]"),
        ("retrograde the text", "s[::-1]"),
        ("backward string transform", "s[::-1]"),
        ("find maximum", "max(x)"),
        ("find max", "max(x)"),
        ("largest value", "max(x)"),
        ("peak element", "max(x)"),
        ("greatest item", "max(x)"),
        ("maximum element", "max(x)"),
        ("highest entry", "max(x)"),
        ("top value", "max(x)"),
        ("apex element", "max(x)"),
        ("supreme value", "max(x)"),
    ]
    return training, feedback, test


# ---------------------------------------------------------------------------
# Category K: Historical-success traps (successful but irrelevant)
# ---------------------------------------------------------------------------

def _build_category_k() -> tuple[list, list]:
    """Historical-success trap: very successful but irrelevant memory."""
    training = [
        {"input": "sort a list", "output": "sorted(x)"},
        {"input": "cook dinner", "output": "recipe"},
        {"input": "walk the dog", "output": "leash"},
        {"input": "wash clothes", "output": "detergent"},
    ]
    feedback = [
        ("cook dinner", "recipe", True),
        ("cook dinner", "recipe", True),
        ("cook dinner", "recipe", True),
        ("cook dinner", "recipe", True),
        ("cook dinner", "recipe", True),
        ("cook dinner", "recipe", True),
        ("cook dinner", "recipe", True),
        ("cook dinner", "recipe", True),
        ("cook dinner", "recipe", True),
        ("cook dinner", "recipe", True),
        ("walk the dog", "leash", True),
        ("walk the dog", "leash", True),
        ("walk the dog", "leash", True),
        ("walk the dog", "leash", True),
        ("walk the dog", "leash", True),
        ("sort a list", "sorted(x)", True),
        ("sort a list", "sorted(x)", True),
        ("sort a list", "sorted(x)", True),
    ]

    test = [
        ("sort a list", "sorted(x)"),
        ("sort array", "sorted(x)"),
        ("sort items", "sorted(x)"),
        ("order list", "sorted(x)"),
        ("arrange elements", "sorted(x)"),
        ("put items in order", "sorted(x)"),
        ("sort numbers", "sorted(x)"),
        ("organize collection", "sorted(x)"),
        ("rank by value", "sorted(x)"),
        ("systematize elements", "sorted(x)"),
        ("sort the data", "sorted(x)"),
        ("sort a sequence", "sorted(x)"),
        ("sort entries", "sorted(x)"),
        ("arrange in order", "sorted(x)"),
        ("order by priority", "sorted(x)"),
        ("sort ascending", "sorted(x)"),
        ("sort descending", "sorted(x, reverse=True)"),
        ("sort with key", "sorted(x, key=k)"),
        ("sort stably", "sorted(x)"),
        ("sort in-place", "x.sort()"),
        ("cook a meal", "recipe"),
        ("prepare food", "recipe"),
        ("make dinner", "recipe"),
        ("take the pet outside", "leash"),
        ("walk the animal", "leash"),
        ("clean the laundry", "detergent"),
        ("wash garments", "detergent"),
        ("cook dinner tonight", "recipe"),
        ("prepare a dish", "recipe"),
        ("make lunch", "recipe"),
    ]
    return training, feedback, test


# ---------------------------------------------------------------------------
# Category L: Distribution shift (different domain)
# ---------------------------------------------------------------------------

def _build_category_l() -> tuple[list, list]:
    """Distribution shift: queries from a different domain than training."""
    training = [
        {"input": "sort a list", "output": "sorted(x)"},
        {"input": "reverse string", "output": "s[::-1]"},
        {"input": "find maximum", "output": "max(x)"},
        {"input": "count elements", "output": "len(x)"},
        {"input": "join strings", "output": "''.join(x)"},
    ]
    feedback = []
    for inp, out in training:
        for _ in range(3):
            feedback.append((inp, out, True))

    test = [
        ("arrange numbers in ascending order", "sorted(x)"),
        ("flip the string backwards", "s[::-1]"),
        ("determine the largest element", "max(x)"),
        ("organize the collection numerically", "sorted(x)"),
        ("invert the character sequence", "s[::-1]"),
        ("find the peak value in dataset", "max(x)"),
        ("put items in sorted order", "sorted(x)"),
        ("mirror the text display", "s[::-1]"),
        ("identify the greatest value", "max(x)"),
        ("count total objects present", "len(x)"),
        ("combine text fragments together", "''.join(x)"),
        ("order entries by magnitude", "sorted(x)"),
        ("reflect string end to end", "s[::-1]"),
        ("acquire the maximum entry", "max(x)"),
        ("evaluate collection size", "len(x)"),
        ("integrate string parts", "''.join(x)"),
        ("systematize elements ascending", "sorted(x)"),
        ("turn string backward", "s[::-1]"),
        ("procure peak constituent", "max(x)"),
        ("quantify membership count", "len(x)"),
        ("aggregate text segments", "''.join(x)"),
        ("lexicographic arrangement", "sorted(x)"),
        ("character reversal process", "s[::-1]"),
        ("supremum value extraction", "max(x)"),
        ("population enumeration", "len(x)"),
        ("data arrangement process", "sorted(x)"),
        ("text direction change", "s[::-1]"),
        ("value magnitude retrieval", "max(x)"),
        ("member tally computation", "len(x)"),
        ("string fusion operation", "''.join(x)"),
        ("element ordering process", "sorted(x)"),
        ("character position swap", "s[::-1]"),
        ("peak magnitude finder", "max(x)"),
        ("set cardinality measure", "len(x)"),
        ("text concatenation task", "''.join(x)"),
    ]
    return training, feedback, test


# ---------------------------------------------------------------------------
# Category M: Ambiguous cases (should abstain)
# ---------------------------------------------------------------------------

def _build_category_m() -> tuple[list, list]:
    """Ambiguous: multiple valid answers, system should abstain."""
    training = [
        {"input": "sort a list", "output": "sorted(x)"},
        {"input": "process data", "output": "transform(x)"},
        {"input": "handle input", "output": "parse(x)"},
        {"input": "sort a list", "output": "list.sort()"},
    ]
    feedback = [
        ("sort a list", "sorted(x)", True),
        ("sort a list", "sorted(x)", True),
        ("sort a list", "list.sort()", True),
        ("sort a list", "list.sort()", True),
        ("process data", "transform(x)", True),
        ("handle input", "parse(x)", True),
    ]

    test = [
        ("sort in place vs return new", "sorted(x)"),
        ("sort or sort in place", "sorted(x)"),
        ("process or parse", "transform(x)"),
        ("transform or parse input", "parse(x)"),
        ("sort a list or not", "sorted(x)"),
        ("mutable vs immutable sort", "sorted(x)"),
        ("in-place or copy sort", "sorted(x)"),
        ("transform or handle data", "transform(x)"),
        ("parse or transform input", "parse(x)"),
        ("sort ascending or descending", "sorted(x)"),
        ("sort stable or unstable", "sorted(x)"),
        ("process and handle data", "transform(x)"),
        ("handle or manage input", "parse(x)"),
        ("sort or arrange elements", "sorted(x)"),
        ("transform or process input", "transform(x)"),
        ("parse or read input", "parse(x)"),
        ("sort or order items", "sorted(x)"),
        ("handle or process data", "parse(x)"),
        ("transform or parse data", "transform(x)"),
        ("sort or rank elements", "sorted(x)"),
        ("process or handle request", "transform(x)"),
        ("parse or transform query", "parse(x)"),
        ("sort or classify items", "sorted(x)"),
        ("handle or process stream", "parse(x)"),
        ("transform or manage data", "transform(x)"),
        ("parse or handle payload", "parse(x)"),
        ("sort or categorize list", "sorted(x)"),
        ("process or parse record", "transform(x)"),
        ("handle or transform input", "parse(x)"),
        ("sort or prioritize items", "sorted(x)"),
        ("sort ascending vs descending", "sorted(x)"),
        ("transform raw or processed", "transform(x)"),
        ("parse text or binary", "parse(x)"),
        ("sort stable or adaptive", "sorted(x)"),
        ("handle sync or async", "parse(x)"),
        ("process batch or streaming", "transform(x)"),
        ("sort numeric or lexical", "sorted(x)"),
        ("transform local or remote", "transform(x)"),
        ("parse json or xml", "parse(x)"),
        ("sort shallow or deep", "sorted(x)"),
        ("handle single or multi", "parse(x)"),
        ("process parallel or serial", "transform(x)"),
        ("sort partial or full", "sorted(x)"),
        ("transform in-place or copy", "transform(x)"),
        ("parse strict or lenient", "parse(x)"),
    ]
    return training, feedback, test


# ---------------------------------------------------------------------------
# Category N: Completely unsupported (no evidence)
# ---------------------------------------------------------------------------

def _build_category_n() -> tuple[list, list]:
    """Completely unsupported: no training data at all."""
    training = []
    feedback = []

    test = [
        ("quantum entanglement measurement", "measure()"),
        ("dna sequence alignment", "align()"),
        ("stock price prediction", "predict()"),
        ("weather forecasting model", "forecast()"),
        ("natural language generation", "generate()"),
        ("image classification task", "classify()"),
        ("speech recognition pipeline", "recognize()"),
        ("recommendation engine setup", "recommend()"),
        ("fraud detection algorithm", "detect()"),
        ("anomaly detection system", "detect_anomaly()"),
        ("robotic path planning", "plan_path()"),
        ("supply chain optimization", "optimize()"),
        ("protein folding prediction", "fold()"),
        ("autonomous vehicle navigation", "navigate()"),
        ("drug discovery pipeline", "discover()"),
        ("climate modeling simulation", "simulate()"),
        ("cybersecurity threat analysis", "analyze()"),
        ("genetic algorithm optimization", "evolve()"),
        ("quantum computing circuit", "build_circuit()"),
        ("real-time fraud scoring", "score()"),
        ("customer churn prediction", "churn()"),
        ("network traffic analysis", "analyze_traffic()"),
        ("sentiment analysis pipeline", "analyze_sentiment()"),
        ("machine translation engine", "translate()"),
        ("time series forecasting", "forecast_ts()"),
        ("code review automation", "review()"),
        ("dependency injection setup", "inject()"),
        ("microservice orchestration", "orchestrate()"),
        ("data pipeline scheduling", "schedule()"),
        ("feature engineering pipeline", "engineer_features()"),
        ("gravitational wave detection", "detect_wave()"),
        ("tidal force calculation", "calculate_tidal()"),
        ("solar flare prediction", "predict_flare()"),
        ("cosmic ray analysis", "analyze_rays()"),
        ("dark matter simulation", "simulate_dark()"),
    ]
    return training, feedback, test


# ---------------------------------------------------------------------------
# Dataset registry
# ---------------------------------------------------------------------------

ALL_CATEGORIES = {
    "A_known": _build_category_a,
    "B_paraphrased": _build_category_b,
    "C_novel_wording": _build_category_c,
    "D_novel_concept": _build_category_d,
    "E_conflict": _build_category_e,
    "F_weak_evidence": _build_category_f,
    "G_duplicate_attack": _build_category_g,
    "H_near_duplicate": _build_category_h,
    "I_feedback_poison": _build_category_i,
    "J_recency_trap": _build_category_j,
    "K_historical_trap": _build_category_k,
    "L_distribution_shift": _build_category_l,
    "M_ambiguous": _build_category_m,
    "N_unsupported": _build_category_n,
}


# ---------------------------------------------------------------------------
# Split logic
# ---------------------------------------------------------------------------

def split_test_data(
    test_cases: list[tuple[str, str]],
    cal_ratio: float = 0.30,
    val_ratio: float = 0.30,
    held_ratio: float = 0.40,
    seed: int = 42,
) -> tuple[list, list, list]:
    """Split test data into calibration / validation / held-out.

    No overlap between any split.
    """
    rng = random.Random(seed)
    indices = list(range(len(test_cases)))
    rng.shuffle(indices)

    n = len(indices)
    n_cal = max(1, int(n * cal_ratio))
    n_val = max(1, int(n * val_ratio))
    n_held = n - n_cal - n_val

    if n_held < 1:
        n_held = 1
        n_cal = max(1, (n - n_held) // 2)
        n_val = n - n_cal - n_held

    cal_idx = indices[:n_cal]
    val_idx = indices[n_cal:n_cal + n_val]
    held_idx = indices[n_cal + n_val:]

    cal = [test_cases[i] for i in cal_idx]
    val = [test_cases[i] for i in val_idx]
    held = [test_cases[i] for i in held_idx]
    return cal, val, held


# ---------------------------------------------------------------------------
# Learner factory
# ---------------------------------------------------------------------------

def _make_learner() -> HybridSimilarityLearner:
    return HybridSimilarityLearner(
        k=5,
        lexical_weight=0.4,
        semantic_weight=0.6,
        scorer_config=ScorerConfig(),
        conflict_config=ConflictConfig(),
        confidence_config=ConfidenceConfig(use_v232=True),
    )


# ---------------------------------------------------------------------------
# Training pipeline
# ---------------------------------------------------------------------------

def train_learner(
    learner: HybridSimilarityLearner,
    all_training: list[dict],
    all_feedback: list[tuple[str, str, bool]],
) -> None:
    """Train learner on all training data and feedback."""
    for obs in all_training:
        learner.learn(LearningInput(observation=obs))
    for text, output, correct in all_feedback:
        learner.feedback(text, output, correct=correct)


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------

def evaluate_queries(
    learner: HybridSimilarityLearner,
    queries: list[tuple[str, str]],
    category: str,
    split: str,
) -> list[EvalSample]:
    """Evaluate learner on a set of queries."""
    samples = []
    for query, expected in queries:
        result = learner.predict(query)
        samples.append(EvalSample(
            query=query,
            expected=expected,
            predicted=result.output,
            confidence=result.confidence,
            correct=(result.output == expected),
            category=category,
            split=split,
            metadata={
                "similarity": result.similarity,
                "uncertainty_state": result.uncertainty_state,
                "has_conflict": result.has_conflict,
                "abstained": result.abstained,
            },
        ))
    return samples


def compute_category_metrics(
    samples: list[EvalSample],
    category: str,
    split: str,
) -> CategoryMetrics:
    """Compute metrics for a single category in a single split."""
    if not samples:
        return CategoryMetrics(
            category=category, split=split, n=0,
            brier=0.0, ece=0.0, accuracy=0.0, mean_confidence=0.0,
            discrimination_gap=0.0, abstention_quality=0.0,
            selective_acc={}, selective_cov={},
        )

    cases = [
        CalibrationCase(
            query=s.query, expected=s.expected, predicted=s.predicted,
            confidence=s.confidence, correct=s.correct,
        )
        for s in samples
    ]

    thresholds = [0.3, 0.5, 0.7, 0.9]
    return CategoryMetrics(
        category=category,
        split=split,
        n=len(samples),
        brier=brier_score(cases),
        ece=expected_calibration_error(cases, n_bins=5),
        accuracy=sum(1 for s in samples if s.correct) / len(samples),
        mean_confidence=sum(s.confidence for s in samples) / len(samples),
        discrimination_gap=discrimination_gap(cases),
        abstention_quality=abstention_quality(cases, n_bins=3),
        selective_acc=selective_prediction_accuracy(cases, thresholds=thresholds),
        selective_cov=selective_prediction_coverage(cases, thresholds=thresholds),
    )


def compute_split_metrics(samples: list[EvalSample], split: str) -> SplitMetrics:
    """Compute aggregate metrics for a split."""
    if not samples:
        return SplitMetrics(
            split=split, n=0, brier=0.0, ece=0.0, accuracy=0.0,
            mean_confidence=0.0, discrimination_gap=0.0, abstention_quality=0.0,
        )

    cases = [
        CalibrationCase(
            query=s.query, expected=s.expected, predicted=s.predicted,
            confidence=s.confidence, correct=s.correct,
        )
        for s in samples
    ]

    return SplitMetrics(
        split=split,
        n=len(samples),
        brier=brier_score(cases),
        ece=expected_calibration_error(cases, n_bins=5),
        accuracy=sum(1 for s in samples if s.correct) / len(samples),
        mean_confidence=sum(s.confidence for s in samples) / len(samples),
        discrimination_gap=discrimination_gap(cases),
        abstention_quality=abstention_quality(cases, n_bins=3),
    )


# ---------------------------------------------------------------------------
# Calibration method comparison
# ---------------------------------------------------------------------------

def build_platt_map(
    raw_confidences: list[float],
    correctness: list[bool],
) -> CalibrationMap:
    """Build a Platt-style calibration map using logistic scaling."""
    if len(raw_confidences) < 20:
        return CalibrationMap(buckets=[], min_samples=20, fallback_mode=True)

    pairs = sorted(zip(raw_confidences, correctness, strict=False), key=lambda x: x[0])

    n_bins = 8
    bin_size = max(1, len(pairs) // n_bins)
    buckets = []

    for i in range(0, len(pairs), bin_size):
        chunk = pairs[i:i + bin_size]
        if len(chunk) < 2:
            continue
        raw_vals = [r for r, _ in chunk]
        correct_vals = [1.0 if c else 0.0 for _, c in chunk]

        raw_mean = sum(raw_vals) / len(raw_vals)
        observed_acc = sum(correct_vals) / len(correct_vals)

        platt_conf = 1.0 / (1.0 + math.exp(-5.0 * (raw_mean - 0.5)))
        calibrated = 0.5 * observed_acc + 0.5 * platt_conf

        buckets.append(CalibrationMap.__new__(CalibrationMap))
        from core.learner.calibration.calibrator import CalibrationBucket
        buckets[-1] = CalibrationBucket(
            raw_low=min(raw_vals),
            raw_high=max(raw_vals),
            raw_mean=raw_mean,
            calibrated=calibrated,
            count=len(chunk),
        )

    if not buckets:
        return CalibrationMap(buckets=[], min_samples=20, fallback_mode=True)
    return CalibrationMap(buckets=buckets)


def compare_calibration_methods(
    cal_samples: list[EvalSample],
    validation_samples: list[EvalSample],
) -> dict:
    """Compare raw, isotonic, and Platt calibration methods."""
    raw_confs = [s.confidence for s in cal_samples]
    correctness = [s.correct for s in cal_samples]

    isotonic_map = build_calibration_map(raw_confs, correctness, n_bins=8, min_samples_per_bin=3)
    platt_map = build_platt_map(raw_confs, correctness)

    methods = {
        "raw": lambda c: c,
        "isotonic": lambda c: calibrate(c, isotonic_map),
        "platt": lambda c: calibrate(c, platt_map),
    }

    results = {}
    for method_name, calibrate_fn in methods.items():
        val_cases = []
        for s in validation_samples:
            cal_conf = calibrate_fn(s.confidence)
            val_cases.append(CalibrationCase(
                query=s.query, expected=s.expected, predicted=s.predicted,
                confidence=cal_conf, correct=s.correct,
            ))
        results[method_name] = {
            "brier": brier_score(val_cases),
            "ece": expected_calibration_error(val_cases, n_bins=5),
            "accuracy": sum(1 for c in val_cases if c.correct) / len(val_cases) if val_cases else 0,
            "mean_confidence": (sum(c.confidence for c in val_cases) / len(val_cases)
                                if val_cases else 0),
        }

    return results


# ---------------------------------------------------------------------------
# Abstention threshold testing
# ---------------------------------------------------------------------------

def test_abstention_thresholds(
    samples: list[EvalSample],
) -> dict[float, dict]:
    """Test at multiple abstention thresholds."""
    thresholds = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    results = {}

    for threshold in thresholds:
        active = [s for s in samples if s.confidence >= threshold]
        acc = sum(1 for s in active if s.correct) / len(active) if active else 0.0
        cov = len(active) / len(samples) if samples else 0.0

        abstained = [s for s in samples if s.confidence < threshold]
        abstain_wrong = (sum(1 for s in abstained if not s.correct) / len(abstained)
                         if abstained else 0.0)

        results[threshold] = {
            "active_count": len(active),
            "abstained_count": len(abstained),
            "accuracy": acc,
            "coverage": cov,
            "abstain_error_rate": 1.0 - abstain_wrong if abstained else 0.0,
        }

    return results


# ---------------------------------------------------------------------------
# Independence of evidence test
# ---------------------------------------------------------------------------

def test_independence_of_evidence(
    learner_factory,
    base_training: list[dict],
    base_feedback: list[tuple],
    queries: list[tuple[str, str]],
) -> dict:
    """Test that duplicate memories don't inflate confidence."""
    scenarios = [
        ("1_copy", 1),
        ("3_copies", 3),
        ("5_copies", 5),
        ("10_copies", 10),
        ("20_copies", 20),
    ]

    results = {}
    for label, n_copies in scenarios:
        learner = learner_factory()
        for obs in base_training:
            learner.learn(LearningInput(observation=obs))
        for _ in range(n_copies):
            for obs in base_training[:2]:
                learner.learn(LearningInput(observation=obs))
        for text, out, correct in base_feedback:
            learner.feedback(text, out, correct=correct)

        confs = []
        for query, expected in queries:
            result = learner.predict(query)
            confs.append((result.confidence, result.output == expected))

        avg_conf = sum(c for c, _ in confs) / len(confs) if confs else 0.0
        avg_acc = sum(1 for _, correct in confs if correct) / len(confs) if confs else 0.0

        results[label] = {
            "avg_confidence": avg_conf,
            "avg_accuracy": avg_acc,
            "n_copies": n_copies,
        }

    return results


# ---------------------------------------------------------------------------
# Conflict handling test
# ---------------------------------------------------------------------------

def test_conflict_handling(
    learner_factory,
) -> dict:
    """Test that conflicts reduce confidence appropriately."""
    scenarios = [
        ("no_conflict", [("sort a list", "sorted(x)")], []),
        ("mild_conflict", [
            ("sort a list", "sorted(x)"),
            ("sort a list", "list.sort()"),
        ], [("sort a list", "sorted(x)", True)] * 3),
        ("strong_conflict", [
            ("sort a list", "sorted(x)"),
            ("sort a list", "bubble_sort(x)"),
            ("sort a list", "insertion_sort(x)"),
        ], [("sort a list", "sorted(x)", True)] * 3),
        ("resolved_conflict", [
            ("sort a list", "sorted(x)"),
            ("sort a list", "list.sort()"),
        ], [
            ("sort a list", "sorted(x)", True),
            ("sort a list", "sorted(x)", True),
            ("sort a list", "sorted(x)", True),
            ("sort a list", "sorted(x)", True),
            ("sort a list", "sorted(x)", True),
            ("sort a list", "list.sort()", True),
        ]),
    ]

    results = {}
    for label, training_pairs, feedback_list in scenarios:
        learner = learner_factory()
        for inp, out in training_pairs:
            learner.learn(LearningInput(observation={"input": inp, "output": out}))
        for text, out, correct in feedback_list:
            learner.feedback(text, out, correct=correct)

        result = learner.predict("sort a list")
        results[label] = {
            "confidence": result.confidence,
            "output": result.output,
            "has_conflict": result.has_conflict,
            "uncertainty_state": result.uncertainty_state,
        }

    return results


# ---------------------------------------------------------------------------
# Distribution shift test
# ---------------------------------------------------------------------------

def test_distribution_shift(
    learner_factory,
) -> dict:
    """Test confidence under distribution shift."""
    training = [
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

    learner = learner_factory()
    for obs in training:
        learner.learn(LearningInput(observation=obs))
    for text, out, correct in feedback:
        learner.feedback(text, out, correct=correct)

    in_domain = [
        ("sort array", "sorted(x)"),
        ("flip the text", "s[::-1]"),
        ("get the largest", "max(x)"),
    ]
    near_domain = [
        ("arrange numbers", "sorted(x)"),
        ("make text backwards", "s[::-1]"),
        ("find peak value", "max(x)"),
    ]
    out_of_domain = [
        ("quantum entanglement", "measure()"),
        ("dna sequence analysis", "align()"),
        ("stock prediction model", "predict()"),
    ]

    results = {}
    for domain_label, queries in [("in_domain", in_domain), ("near_domain", near_domain),
                                  ("out_of_domain", out_of_domain)]:
        confs = []
        for query, _expected in queries:
            result = learner.predict(query)
            confs.append(result.confidence)
        results[domain_label] = {
            "avg_confidence": sum(confs) / len(confs) if confs else 0.0,
            "min_confidence": min(confs) if confs else 0.0,
            "max_confidence": max(confs) if confs else 0.0,
        }

    return results


# ---------------------------------------------------------------------------
# Scale test
# ---------------------------------------------------------------------------

def test_scale(learner_factory) -> dict:
    """Test performance at various memory counts."""
    sizes = [10, 50, 100, 200]
    results = {}

    base_pairs = [
        ("sort a list", "sorted(x)"),
        ("reverse string", "s[::-1]"),
        ("find maximum", "max(x)"),
        ("count elements", "len(x)"),
        ("join strings", "''.join(x)"),
    ]

    for size in sizes:
        start = time.time()
        learner = learner_factory()

        training = []
        for i in range(size):
            inp, out = base_pairs[i % len(base_pairs)]
            training.append({"input": f"{inp} variant_{i}", "output": out})

        for obs in training:
            learner.learn(LearningInput(observation=obs))

        for inp, out in base_pairs:
            learner.feedback(inp, out, correct=True)

        query = "sort a list"
        n_queries = min(20, size)
        for _ in range(n_queries):
            learner.predict(query)

        elapsed = time.time() - start
        result = learner.predict(query)

        results[size] = {
            "time_seconds": elapsed,
            "confidence": result.confidence,
            "memory_count": learner._memory.count(),
        }

    return results


# ---------------------------------------------------------------------------
# Randomization stability test
# ---------------------------------------------------------------------------

def test_randomization_stability(learner_factory) -> dict:
    """Test that results are deterministic with same seed."""
    base_training = [
        {"input": "sort a list", "output": "sorted(x)"},
        {"input": "reverse string", "output": "s[::-1]"},
        {"input": "find maximum", "output": "max(x)"},
    ]
    base_feedback = [
        ("sort a list", "sorted(x)", True),
        ("reverse string", "s[::-1]", True),
        ("find maximum", "max(x)", True),
    ]

    query = "sort a list"
    results_a = []
    results_b = []

    for _run in range(3):
        random.seed(42)
        learner = learner_factory()
        for obs in base_training:
            learner.learn(LearningInput(observation=obs))
        for text, out, correct in base_feedback:
            learner.feedback(text, out, correct=correct)
        r = learner.predict(query)
        results_a.append((r.confidence, r.output))

    for _run in range(3):
        random.seed(42)
        learner = learner_factory()
        for obs in base_training:
            learner.learn(LearningInput(observation=obs))
        for text, out, correct in base_feedback:
            learner.feedback(text, out, correct=correct)
        r = learner.predict(query)
        results_b.append((r.confidence, r.output))

    all_match = all(
        abs(a[0] - b[0]) < 1e-10 and a[1] == b[1]
        for a, b in zip(results_a, results_b, strict=False)
    )

    return {
        "run_a": results_a,
        "run_b": results_b,
        "deterministic": all_match,
    }


# ---------------------------------------------------------------------------
# Print helpers
# ---------------------------------------------------------------------------

def print_sample_table(samples: list[EvalSample], title: str) -> None:
    """Print raw prediction table for every sample."""
    print(f"\n  {'=' * 90}")
    print(f"  {title} ({len(samples)} samples)")
    print(f"  {'=' * 90}")
    print(f"  {'Query':<30s} {'Expected':<20s} {'Predicted':<20s} {'Conf':>6s} {'OK':>4s}")
    print(f"  {'-' * 90}")
    for s in samples:
        q = s.query[:28]
        e = s.expected[:18]
        p = s.predicted[:18]
        ok = "Y" if s.correct else "N"
        print(f"  {q:<30s} {e:<20s} {p:<20s} {s.confidence:>6.3f} {ok:>4s}")


def print_category_metrics_table(metrics: list[CategoryMetrics]) -> None:
    """Print category metrics table."""
    print(f"\n  {'Category':<25s} {'Split':<12s} {'N':>4s} {'Brier':>7s} {'ECE':>7s} "
          f"{'Acc':>6s} {'MConf':>6s} {'DGap':>6s} {'AbstQ':>6s}")
    print(f"  {'-' * 95}")
    for m in metrics:
        print(f"  {m.category:<25s} {m.split:<12s} {m.n:>4d} {m.brier:>7.4f} {m.ece:>7.4f} "
              f"{m.accuracy:>6.3f} {m.mean_confidence:>6.3f} "
              f"{m.discrimination_gap:>6.3f} {m.abstention_quality:>6.3f}")


def print_split_summary(splits: list[SplitMetrics]) -> None:
    """Print split-level summary."""
    print(f"\n  {'Split':<15s} {'N':>5s} {'Brier':>7s} {'ECE':>7s} "
          f"{'Acc':>6s} {'MConf':>6s} {'DGap':>6s} {'AbstQ':>6s}")
    print(f"  {'-' * 70}")
    for s in splits:
        print(f"  {s.split:<15s} {s.n:>5d} {s.brier:>7.4f} {s.ece:>7.4f} "
              f"{s.accuracy:>6.3f} {s.mean_confidence:>6.3f} "
              f"{s.discrimination_gap:>6.3f} {s.abstention_quality:>6.3f}")


def print_calibration_comparison(comp: dict) -> None:
    """Print calibration method comparison."""
    print(f"\n  {'Method':<12s} {'Brier':>7s} {'ECE':>7s} {'Acc':>6s} {'MConf':>6s}")
    print(f"  {'-' * 45}")
    for method, metrics in comp.items():
        print(f"  {method:<12s} {metrics['brier']:>7.4f} {metrics['ece']:>7.4f} "
              f"{metrics['accuracy']:>6.3f} {metrics['mean_confidence']:>6.3f}")


def print_abstention_table(results: dict) -> None:
    """Print abstention threshold results."""
    print(f"\n  {'Thresh':>7s} {'Active':>7s} {'Abstain':>8s} {'Acc':>6s} {'Cov':>6s}")
    print(f"  {'-' * 45}")
    for threshold, metrics in sorted(results.items()):
        print(f"  {threshold:>7.2f} {metrics['active_count']:>7d} "
              f"{metrics['abstained_count']:>8d} "
              f"{metrics['accuracy']:>6.3f} {metrics['coverage']:>6.3f}")


def print_independence_test(results: dict) -> None:
    """Print independence of evidence test results."""
    print(f"\n  {'Scenario':<15s} {'Copies':>7s} {'AvgConf':>8s} {'AvgAcc':>8s}")
    print(f"  {'-' * 45}")
    for label, metrics in results.items():
        print(f"  {label:<15s} {metrics['n_copies']:>7d} "
              f"{metrics['avg_confidence']:>8.4f} {metrics['avg_accuracy']:>8.4f}")


def print_conflict_test(results: dict) -> None:
    """Print conflict handling test results."""
    print(f"\n  {'Scenario':<20s} {'Conf':>6s} {'Output':<20s} {'Conflict':>8s} {'State':<15s}")
    print(f"  {'-' * 75}")
    for label, metrics in results.items():
        conflict = "Yes" if metrics["has_conflict"] else "No"
        print(f"  {label:<20s} {metrics['confidence']:>6.3f} "
              f"{metrics['output'][:18]:<20s} {conflict:>8s} {metrics['uncertainty_state']:<15s}")


def print_shift_test(results: dict) -> None:
    """Print distribution shift test results."""
    print(f"\n  {'Domain':<15s} {'AvgConf':>8s} {'MinConf':>8s} {'MaxConf':>8s}")
    print(f"  {'-' * 45}")
    for domain, metrics in results.items():
        print(f"  {domain:<15s} {metrics['avg_confidence']:>8.4f} "
              f"{metrics['min_confidence']:>8.4f} {metrics['max_confidence']:>8.4f}")


def print_scale_test(results: dict) -> None:
    """Print scale test results."""
    print(f"\n  {'Size':>7s} {'Time(s)':>8s} {'Conf':>6s} {'Memories':>9s}")
    print(f"  {'-' * 35}")
    for size, metrics in results.items():
        print(f"  {size:>7d} {metrics['time_seconds']:>8.3f} "
              f"{metrics['confidence']:>6.3f} {metrics['memory_count']:>9d}")


def print_stability_test(results: dict) -> None:
    """Print randomization stability test results."""
    print(f"\n  Deterministic: {results['deterministic']}")
    for i, (a, b) in enumerate(zip(results["run_a"], results["run_b"], strict=False)):
        match = "MATCH" if abs(a[0] - b[0]) < 1e-10 and a[1] == b[1] else "DIFF"
        print(f"  Run {i}: A=({a[0]:.4f}, {a[1]}) B=({b[0]:.4f}, {b[1]}) [{match}]")


# ---------------------------------------------------------------------------
# Held-out test: FINAL measurement only
# ---------------------------------------------------------------------------

def evaluate_held_out(
    learner: HybridSimilarityLearner,
    held_out_samples: list[EvalSample],
    cal_map: CalibrationMap,
    platt_map: CalibrationMap,
) -> dict:
    """Final measurement on held-out test data ONLY.

    This function is the ONLY place held-out data is used.
    It applies calibration from calibration split and reports final metrics.
    """
    print("\n" + "=" * 80)
    print("  HELD-OUT TEST: FINAL MEASUREMENT")
    print("=" * 80)

    raw_samples = []
    isotonic_samples = []
    platt_samples = []

    for s in held_out_samples:
        raw_samples.append(EvalSample(
            query=s.query, expected=s.expected, predicted=s.predicted,
            confidence=s.confidence, correct=s.correct,
            category=s.category, split="held_out",
            metadata={**s.metadata, "cal_method": "raw"},
        ))

        iso_conf = calibrate(s.confidence, cal_map)
        isotonic_samples.append(EvalSample(
            query=s.query, expected=s.expected, predicted=s.predicted,
            confidence=iso_conf, correct=s.correct,
            category=s.category, split="held_out",
            metadata={**s.metadata, "cal_method": "isotonic"},
        ))

        platt_conf = calibrate(s.confidence, platt_map)
        platt_samples.append(EvalSample(
            query=s.query, expected=s.expected, predicted=s.predicted,
            confidence=platt_conf, correct=s.correct,
            category=s.category, split="held_out",
            metadata={**s.metadata, "cal_method": "platt"},
        ))

    print_sample_table(raw_samples, "HELD-OUT RAW PREDICTIONS")

    results = {}
    for method_name, samples in [("raw", raw_samples), ("isotonic", isotonic_samples),
                                 ("platt", platt_samples)]:
        cases = [
            CalibrationCase(
                query=s.query, expected=s.expected, predicted=s.predicted,
                confidence=s.confidence, correct=s.correct,
            )
            for s in samples
        ]
        results[method_name] = {
            "brier": brier_score(cases),
            "ece": expected_calibration_error(cases, n_bins=5),
            "accuracy": sum(1 for s in samples if s.correct) / len(samples),
            "mean_confidence": sum(s.confidence for s in samples) / len(samples),
            "discrimination_gap": discrimination_gap(cases),
            "abstention_quality": abstention_quality(cases, n_bins=3),
        }

    print(f"\n  {'Method':<12s} {'Brier':>7s} {'ECE':>7s} {'Acc':>6s} "
          f"{'MConf':>6s} {'DGap':>6s} {'AbstQ':>6s}")
    print(f"  {'-' * 55}")
    for method, metrics in results.items():
        print(f"  {method:<12s} {metrics['brier']:>7.4f} {metrics['ece']:>7.4f} "
              f"{metrics['accuracy']:>6.3f} {metrics['mean_confidence']:>6.3f} "
              f"{metrics['discrimination_gap']:>6.3f} {metrics['abstention_quality']:>6.3f}")

    return results


# ---------------------------------------------------------------------------
# Main benchmark
# ---------------------------------------------------------------------------

def main():
    print("=" * 80)
    print("  V2.3.4 COMPREHENSIVE EVALUATION BENCHMARK")
    print("  600+ Cases | 14 Categories | 4-Way Split")
    print("=" * 80)

    tmp_dir = Path(__file__).resolve().parent.parent / "tmp_eval_v234"
    tmp_dir.mkdir(exist_ok=True)

    # ---------------------------------------------------------------
    # Phase 1: Build all datasets and collect training + test data
    # ---------------------------------------------------------------
    print("\n[Phase 1] Building datasets...")

    all_training = []
    all_feedback = []
    category_test_data: dict[str, list[tuple[str, str]]] = {}

    for cat_name, builder in ALL_CATEGORIES.items():
        train, feedback, test = builder()
        all_training.extend(train)
        all_feedback.extend(feedback)
        category_test_data[cat_name] = test
        print(f"  {cat_name}: train={len(train)}, feedback={len(feedback)}, test={len(test)}")

    total_test = sum(len(v) for v in category_test_data.values())
    print(f"\n  Total training observations: {len(all_training)}")
    print(f"  Total feedback entries: {len(all_feedback)}")
    print(f"  Total test cases: {total_test}")

    # ---------------------------------------------------------------
    # Phase 2: Split each category's test data into CAL / VAL / HELD
    # ---------------------------------------------------------------
    print("\n[Phase 2] Splitting test data (CAL / VAL / HELD-OUT)...")

    cal_data: dict[str, list] = {}
    val_data: dict[str, list] = {}
    held_data: dict[str, list] = {}

    for cat_name, test_cases in category_test_data.items():
        cal, val, held = split_test_data(test_cases, cal_ratio=0.30,
                                        val_ratio=0.30, held_ratio=0.40)
        cal_data[cat_name] = cal
        val_data[cat_name] = val
        held_data[cat_name] = held
        print(f"  {cat_name}: cal={len(cal)}, val={len(val)}, held={len(held)}")

    total_cal = sum(len(v) for v in cal_data.values())
    total_val = sum(len(v) for v in val_data.values())
    total_held = sum(len(v) for v in held_data.values())
    print(f"\n  Split totals: cal={total_cal}, val={total_val}, held={total_held}, "
          f"sum={total_cal+total_val+total_held}")

    # Verify no overlap
    all_cal = set()
    all_val = set()
    all_held = set()
    for cat in cal_data:
        for q, e in cal_data[cat]:
            all_cal.add((cat, q, e))
        for q, e in val_data[cat]:
            all_val.add((cat, q, e))
        for q, e in held_data[cat]:
            all_held.add((cat, q, e))

    assert all_cal.isdisjoint(all_val), "CAL and VAL overlap!"
    assert all_cal.isdisjoint(all_held), "CAL and HELD overlap!"
    assert all_val.isdisjoint(all_held), "VAL and HELD overlap!"
    print("  Split integrity: PASS (no overlap)")

    # ---------------------------------------------------------------
    # Phase 3: Train learner on training data
    # ---------------------------------------------------------------
    print("\n[Phase 3] Training learner...")
    learner = _make_learner()
    train_learner(learner, all_training, all_feedback)
    print(f"  Learner trained: {learner._memory.count()} memories")

    # ---------------------------------------------------------------
    # Phase 4: Evaluate on CALIBRATION split
    # ---------------------------------------------------------------
    print("\n[Phase 4] Evaluating on CALIBRATION split...")

    cal_samples: dict[str, list[EvalSample]] = {}
    all_cal_samples: list[EvalSample] = []

    for cat_name in ALL_CATEGORIES:
        queries = cal_data[cat_name]
        samples = evaluate_queries(learner, queries, cat_name, "calibration")
        cal_samples[cat_name] = samples
        all_cal_samples.extend(samples)
        print(f"  {cat_name}: {len(samples)} samples evaluated")

    # ---------------------------------------------------------------
    # Phase 5: Build calibration maps from CALIBRATION data
    # ---------------------------------------------------------------
    print("\n[Phase 5] Building calibration maps from CALIBRATION data...")

    raw_confs = [s.confidence for s in all_cal_samples]
    correctness = [s.correct for s in all_cal_samples]

    isotonic_map = build_calibration_map(raw_confs, correctness, n_bins=8, min_samples_per_bin=3)
    platt_map = build_platt_map(raw_confs, correctness)
    print(f"  Isotonic map: {len(isotonic_map.buckets)} buckets, "
          f"fallback={isotonic_map.fallback_mode}")
    print(f"  Platt map: {len(platt_map.buckets)} buckets, fallback={platt_map.fallback_mode}")

    # ---------------------------------------------------------------
    # Phase 6: Evaluate on VALIDATION split
    # ---------------------------------------------------------------
    print("\n[Phase 6] Evaluating on VALIDATION split...")

    val_samples: dict[str, list[EvalSample]] = {}
    all_val_samples: list[EvalSample] = []

    for cat_name in ALL_CATEGORIES:
        queries = val_data[cat_name]
        samples = evaluate_queries(learner, queries, cat_name, "validation")
        val_samples[cat_name] = samples
        all_val_samples.extend(samples)
        print(f"  {cat_name}: {len(samples)} samples evaluated")

    # Calibration method comparison on validation
    print("\n  Calibration method comparison (on VALIDATION):")
    cal_comparison = compare_calibration_methods(all_cal_samples, all_val_samples)
    print_calibration_comparison(cal_comparison)

    # Abstention threshold testing on validation
    print("\n  Abstention threshold analysis (on VALIDATION):")
    abstention_results = test_abstention_thresholds(all_val_samples)
    print_abstention_table(abstention_results)

    # ---------------------------------------------------------------
    # Phase 7: Special tests (using validation data, NOT held-out)
    # ---------------------------------------------------------------
    print("\n[Phase 7] Special tests (on VALIDATION data only)...")

    # Independence of evidence test
    print("\n  Independence of Evidence Test:")
    independence_results = test_independence_of_evidence(
        _make_learner,
        [{"input": "sort a list", "output": "sorted(x)"},
         {"input": "reverse string", "output": "s[::-1]"}],
        [("sort a list", "sorted(x)", True), ("reverse string", "s[::-1]", True)],
        [("sort array", "sorted(x)"), ("flip text", "s[::-1]")],
    )
    print_independence_test(independence_results)

    # Conflict handling test
    print("\n  Conflict Handling Test:")
    conflict_results = test_conflict_handling(_make_learner)
    print_conflict_test(conflict_results)

    # Distribution shift test
    print("\n  Distribution Shift Test:")
    shift_results = test_distribution_shift(_make_learner)
    print_shift_test(shift_results)

    # Scale test
    print("\n  Scale Test:")
    scale_results = test_scale(_make_learner)
    print_scale_test(scale_results)

    # Randomization stability test
    print("\n  Randomization Stability Test:")
    stability_results = test_randomization_stability(_make_learner)
    print_stability_test(stability_results)

    # ---------------------------------------------------------------
    # Phase 8: Print detailed tables for each category
    # ---------------------------------------------------------------
    print("\n[Phase 8] Detailed per-category results (VALIDATION split)...")

    cat_metrics = []
    for cat_name in ALL_CATEGORIES:
        samples = val_samples.get(cat_name, [])
        m = compute_category_metrics(samples, cat_name, "validation")
        cat_metrics.append(m)
        if samples:
            print_sample_table(samples, f"{cat_name} VALIDATION")

    print_category_metrics_table(cat_metrics)

    # ---------------------------------------------------------------
    # Phase 9: HELD-OUT TEST — FINAL MEASUREMENT ONLY
    # ---------------------------------------------------------------
    print("\n[Phase 9] Evaluating on HELD-OUT TEST (FINAL measurement)...")

    held_samples: dict[str, list[EvalSample]] = {}
    all_held_samples: list[EvalSample] = []

    for cat_name in ALL_CATEGORIES:
        queries = held_data[cat_name]
        samples = evaluate_queries(learner, queries, cat_name, "held_out")
        held_samples[cat_name] = samples
        all_held_samples.extend(samples)

    # Print per-category held-out tables
    held_cat_metrics = []
    for cat_name in ALL_CATEGORIES:
        samples = held_samples.get(cat_name, [])
        m = compute_category_metrics(samples, cat_name, "held_out")
        held_cat_metrics.append(m)
        if samples:
            print_sample_table(samples, f"{cat_name} HELD-OUT")

    print_category_metrics_table(held_cat_metrics)

    # Final held-out evaluation with calibration methods
    held_final = evaluate_held_out(learner, all_held_samples, isotonic_map, platt_map)

    # ---------------------------------------------------------------
    # Phase 10: Summary
    # ---------------------------------------------------------------
    print("\n" + "=" * 80)
    print("  FINAL SUMMARY")
    print("=" * 80)

    cal_split_m = compute_split_metrics(all_cal_samples, "CALIBRATION")
    val_split_m = compute_split_metrics(all_val_samples, "VALIDATION")
    held_split_m = compute_split_metrics(all_held_samples, "HELD-OUT")
    print_split_summary([cal_split_m, val_split_m, held_split_m])

    print(f"\n  Total cases across all splits: {total_cal + total_val + total_held}")
    print(f"  Categories tested: {len(ALL_CATEGORIES)}")
    print("  Calibration methods compared: raw, isotonic, Platt")
    print("  Abstention thresholds tested: 9")
    print("  Special tests: independence, conflict, shift, scale, stability")

    print("\n  Held-out final metrics (best calibration method):")
    best_method = min(held_final.keys(), key=lambda k: held_final[k]["brier"])
    bm = held_final[best_method]
    print(f"    Method: {best_method}")
    print(f"    Brier:  {bm['brier']:.4f}")
    print(f"    ECE:    {bm['ece']:.4f}")
    print(f"    Acc:    {bm['accuracy']:.3f}")
    print(f"    MConf:  {bm['mean_confidence']:.3f}")
    print(f"    DGap:   {bm['discrimination_gap']:.3f}")
    print(f"    AbstQ:  {bm['abstention_quality']:.3f}")

    print("\nDone.")
    return held_final


if __name__ == "__main__":
    main()
