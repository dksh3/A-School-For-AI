"""Forge question bank — data.

Analytics, dashboards, pipelines, ML, experiments, data quality. Discovery is
about the question the data must answer and how trustworthy it must be.
"""

from __future__ import annotations

from typing import Any

from core.forge.models import Question, QuestionType


def _q(
    qid: str,
    dim: str,
    prompt: str,
    qtype: QuestionType = QuestionType.TEXT,
    options: tuple[str, ...] = (),
    required: bool = False,
    followups: tuple[Question, ...] = (),
    hint: str = "",
) -> Question:
    return Question(
        id=qid,
        dimension=dim,
        prompt=prompt,
        type=qtype,
        options=list(options),
        allow_custom=True,
        followups=list(followups),
        required=required,
        domain_hint=hint,
    )


def _fu(
    qid: str,
    dim: str,
    prompt: str,
    trigger: str,
    qtype: QuestionType = QuestionType.TEXT,
    options: tuple[str, ...] = (),
) -> Question:
    return _q(qid, dim, prompt, qtype, options, hint=f"when:{trigger}")


def QUESTIONS(domain: Any = None) -> list[Question]:
    return [
        _q(
            "dat_intent", "intent",
            "What question should the data answer?",
            required=True,
        ),
        _q(
            "dat_kind", "intent",
            "What kind of data work is this?",
            QuestionType.CHOICE,
            ("An analysis or report", "A dashboard or recurring metric",
             "A data pipeline or ETL", "A predictive or ML model",
             "An experiment or A/B test", "Data cleanup or quality work",
             "A data collection plan"),
            followups=(
                _fu("dat_kind_model", "intent",
                    "What will the model's output be used to decide?",
                    "A predictive or ML model"),
            ),
        ),
        _q(
            "dat_audience", "audience",
            "Who acts on the results?",
            QuestionType.CHOICE,
            ("Analysts or data scientists", "Product or business leaders",
             "Engineers or systems", "Customers (a data product)",
             "Regulators or auditors", "Me, to make a call"),
            followups=(
                _fu("dat_audience_leaders", "audience",
                    "What decisions will they make with it, and how fast?",
                    "Product or business leaders"),
            ),
        ),
        _q(
            "dat_scope", "scope",
            "What should the work cover?",
            QuestionType.MULTI,
            ("The core question or metric", "Data sourcing or collection",
             "Cleaning and validation", "Modeling or statistics",
             "Visualization or dashboard", "Documentation or data dictionary",
             "Automation or scheduling"),
        ),
        _q(
            "dat_constraints", "constraints",
            "What limits the work?",
            QuestionType.MULTI,
            ("Privacy or PII rules", "Data retention limits",
             "Compute or budget limits", "A deadline",
             "Tools or platforms required", "Data quality realities",
             "Statistical rigor required"),
            followups=(
                _fu("dat_constraints_pii", "constraints",
                    "Which data is sensitive, and what is allowed?",
                    "Privacy or PII rules"),
            ),
        ),
        _q(
            "dat_success", "success",
            "What does the answer is trustworthy look like - how is it validated?",
            required=True,
        ),
        _q(
            "dat_precision", "success",
            "How precise must the answer be?",
            QuestionType.SCALE,
            ("1 - directional only", "2", "3 - solid enough to act on", "4",
             "5 - rigorously validated"),
        ),
        _q(
            "dat_resources", "resources",
            "What do you have to work with?",
            QuestionType.MULTI,
            ("Existing datasets", "Compute or cloud budget",
             "Domain experts to sanity-check", "Notebooks or tooling", "Time",
             "Historical analyses to build on", "Nothing yet"),
        ),
        _q(
            "dat_risks", "risks",
            "What could sink the analysis?",
            QuestionType.MULTI,
            ("Data quality undermines the answer", "Sample bias or leakage",
             "Misleading visuals", "Overfitting or p-hacking", "Privacy breach",
             "Stale data or broken pipelines", "Nothing major"),
            followups=(
                _fu("dat_risks_bias", "risks",
                    "How should the validation split or control be designed?",
                    "Sample bias or leakage"),
            ),
        ),
        _q(
            "dat_sequence", "sequence",
            "Must steps happen in order (collect, clean, model, report)?",
            QuestionType.CONFIRM,
            followups=(
                _fu("dat_sequence_order", "sequence",
                    "What must happen before what?",
                    "Yes"),
            ),
        ),
        _q(
            "dat_style", "style",
            "How should results be presented?",
            QuestionType.CHOICE,
            ("Charts and visuals first", "Numbers and tables first",
             "A plain-language summary up top", "A notebook with full method",
             "A one-pager for decision makers", "Match an existing report style"),
            followups=(
                _fu("dat_style_match", "style",
                    "Which report should it match?",
                    "Match an existing report style"),
            ),
        ),
        _q("dat_edge", "edge_cases",
           "What could make the numbers lie - missing data, outliers, seasonality?"),
        _q("dat_glossary", "glossary",
           "Metric definitions and terms that must stay consistent?"),
        _q("dat_open", "open_questions",
           "What is still unknown or assumed? What should an agent ask if stuck?"),
    ]
