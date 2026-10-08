from __future__ import annotations

import copy
import json

from core.context.engine import ContextEngine
from core.skillgen.budget import ModelCallBudget

ERR = "Traceback (most recent call last): boom " + "x" * 60


def msg(role: str, content: str) -> dict:
    return {"role": role, "content": content}


class MockJudge:
    def __init__(self, raw: str | None = None, fail: bool = False) -> None:
        self.raw = raw or json.dumps({"summary": "compressed by model"})
        self.fail = fail
        self.calls = 0

    def __call__(self, prompt: str) -> tuple[str, str]:
        self.calls += 1
        if self.fail:
            raise RuntimeError("judge down")
        return self.raw, "mock"


def over_threshold_msgs() -> list[dict]:
    return [msg("user", "y" * 200), msg("assistant", "a" * 200)]


def test_kill_switch_passthrough(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SCHOOL_COMPRESS", "0")
    engine = ContextEngine(str(tmp_path), "s1", judge=None)
    msgs = over_threshold_msgs()
    report = engine.compress(msgs)
    assert report.skipped == "kill_switch"
    assert report.triggered is False
    assert report.messages == msgs
    assert engine.should_compress(msgs) is False


def test_below_threshold_skipped(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SCHOOL_COMPRESS_WINDOW_TOKENS", "100000")
    engine = ContextEngine(str(tmp_path), "s1", judge=None)
    report = engine.compress([msg("user", "hi")])
    assert report.skipped == "below_threshold"
    assert report.blocks_added == 0


def test_layer0_creates_blocks_and_view(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SCHOOL_COMPRESS_WINDOW_TOKENS", "60")
    monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
    engine = ContextEngine(str(tmp_path), "s1", judge=None)
    msgs = [
        msg("user", "start"),
        msg("tool", ERR),
        msg("assistant", "ok"),
        msg("tool", ERR),
        msg("user", "tail"),
    ]
    before = copy.deepcopy(msgs)
    report = engine.compress(msgs)
    assert report.triggered is True
    assert report.layer_used == 0
    assert report.blocks_added >= 1
    assert msgs == before
    assert len(engine.store.load()) == report.blocks_added
    view = engine.view(msgs)
    assert any(m.get("school_block") for m in view.messages)


def test_layer1_used_when_no_layer0_spans(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SCHOOL_COMPRESS_WINDOW_TOKENS", "60")
    monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
    judge = MockJudge()
    engine = ContextEngine(str(tmp_path), "s1", judge=judge)
    report = engine.compress(over_threshold_msgs())
    assert report.layer_used == 1
    assert judge.calls == 1
    assert engine.circuit.state.value == "ok"
    stored = engine.store.load()
    assert stored and stored[0].layer == 1
    assert "compressed by model" in stored[0].summary


def test_judge_failure_falls_to_layer2_and_trips_circuit(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SCHOOL_COMPRESS_WINDOW_TOKENS", "60")
    monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
    judge = MockJudge(fail=True)
    engine = ContextEngine(str(tmp_path), "s1", judge=judge)
    report = engine.compress(over_threshold_msgs())
    assert report.layer_used == 2
    assert judge.calls == 1
    assert engine.circuit.state.value == "warning"
    stored = engine.store.load()
    assert stored and stored[0].layer == 2


def test_tripped_circuit_skips_layer1(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SCHOOL_COMPRESS_WINDOW_TOKENS", "60")
    monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
    judge = MockJudge()
    engine = ContextEngine(str(tmp_path), "s1", judge=judge)
    for _ in range(3):
        engine.circuit.record_failure()
    assert engine.circuit.allow() is False
    report = engine.compress(over_threshold_msgs())
    assert judge.calls == 0
    assert report.layer_used == 2


def test_budget_zero_skips_layer1(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SCHOOL_COMPRESS_WINDOW_TOKENS", "60")
    monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
    judge = MockJudge()
    budget = ModelCallBudget({}, max_per_task=0)
    engine = ContextEngine(str(tmp_path), "s1", judge=judge, budget=budget)
    report = engine.compress(over_threshold_msgs())
    assert judge.calls == 0
    assert report.layer_used == 2


def test_store_failure_fails_open(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SCHOOL_COMPRESS_WINDOW_TOKENS", "60")
    monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
    engine = ContextEngine(str(tmp_path), "s1", judge=None)
    msgs = over_threshold_msgs()

    def _boom(blocks):  # noqa: ANN001
        raise OSError("disk full")

    monkeypatch.setattr(engine.store, "save", _boom)
    report = engine.compress(msgs)
    assert report.skipped == "fail_open"
    assert report.messages == msgs


def test_should_compress_and_report_shape(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SCHOOL_COMPRESS_WINDOW_TOKENS", "40")
    monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
    engine = ContextEngine(str(tmp_path), "s1", judge=None)
    msgs = over_threshold_msgs()
    assert engine.should_compress(msgs) is True
    report = engine.compress(msgs)
    d = report.to_dict()
    assert {"triggered", "layer_used", "tokens_saved", "ratio_after", "circuit"} <= set(d)
