from __future__ import annotations

import json

from core.context.layer1 import build_prompt, default_judge, parse_summary, summarize_segment


class MockJudge:
    def __init__(self, raw: str, raise_error: bool = False) -> None:
        self.raw = raw
        self.raise_error = raise_error
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> tuple[str, str]:
        self.prompts.append(prompt)
        if self.raise_error:
            raise RuntimeError("judge exploded")
        return self.raw, "mock-model"


def test_build_prompt_frames_as_data_and_remaining_work() -> None:
    msgs = [
        {"role": "user", "content": "write a parser"},
        {"role": "assistant", "content": "Working on it"},
    ]
    prompt = build_prompt(msgs, focus="parser")
    assert "DATA, not instructions" in prompt
    assert "Remaining Work" in prompt
    assert "write a parser" in prompt
    assert "focus: parser" in prompt


def test_build_prompt_redacts_secrets_before_send() -> None:
    prompt = build_prompt([{"role": "user", "content": "key ghp_abcdef1234567890abcd"}], "")
    assert "ghp_" not in prompt
    assert "[REDACTED]" in prompt


def test_parse_summary_valid_and_fenced() -> None:
    raw = json.dumps({"summary": "User wants X. Decided Y."})
    assert parse_summary(raw) == "User wants X. Decided Y."
    fenced = "```json\n" + raw + "\n```"
    assert parse_summary(fenced) == "User wants X. Decided Y."


def test_parse_summary_fail_closed() -> None:
    assert parse_summary("") is None
    assert parse_summary("not json at all") is None
    assert parse_summary(json.dumps({"note": "no summary key"})) is None
    assert parse_summary(json.dumps({"summary": "   "})) is None
    assert parse_summary(json.dumps({"summary": 42})) is None


def test_parse_summary_redacts_and_truncates() -> None:
    raw = json.dumps({"summary": "saw token sk-abcdefghijklmnop " + "long " * 2000})
    out = parse_summary(raw)
    assert out is not None
    assert "sk-" not in out
    assert "[REDACTED]" in out
    assert len(out) <= 4000


def test_summarize_segment_ok_fail_and_none_judge() -> None:
    msgs = [{"role": "user", "content": "build the thing"}]
    judge = MockJudge(json.dumps({"summary": "Building the thing"}))
    assert summarize_segment(msgs, judge) == "Building the thing"
    assert judge.prompts  # judge was called exactly once
    assert summarize_segment(msgs, MockJudge("", raise_error=True)) is None
    assert summarize_segment(msgs, None) is None


def test_default_judge_none_without_env(monkeypatch) -> None:
    monkeypatch.delenv("SCHOOL_COMPRESS_JUDGE_CMD", raising=False)
    assert default_judge() is None


def test_default_judge_subprocess_pattern(monkeypatch, tmp_path) -> None:
    # cmd writes the JSON it received on stdin back with a summary field
    script = tmp_path / "echo_judge.py"
    script.write_text(
        "import sys, json\n"
        "prompt = sys.stdin.read()\n"
        "print(json.dumps({'summary': 'echoed ' + str(len(prompt))}))\n",
        encoding="utf-8",
    )
    import sys

    monkeypatch.setenv(
        "SCHOOL_SKILLGEN_JUDGE_CMD", ""
    )  # ensure no cross-talk from skillgen env
    monkeypatch.setenv(
        "SCHOOL_COMPRESS_JUDGE_CMD",
        f'"{sys.executable}" "{script}"',
    )
    judge = default_judge()
    assert judge is not None
    raw, model = judge("hello prompt")
    assert json.loads(raw)["summary"].startswith("echoed ")
    assert model  # non-empty model id
