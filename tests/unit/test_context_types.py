from __future__ import annotations

from core.context.types import Block, CircuitState, CompressionReport


def test_block_roundtrip_dict() -> None:
    b = Block(
        id="b1",
        start=3,
        end=6,
        messages=[{"role": "user", "content": "hi"}],
        summary="User asked for hi",
        layer=0,
        tokens_original=120,
        tokens_summary=24,
        created_at="2026-10-06T00:00:00+00:00",
    )
    data = b.to_dict()
    assert data["id"] == "b1"
    assert data["range"] == [3, 6]
    assert data["messages"][0]["role"] == "user"
    back = Block.from_dict(data)
    assert back.id == "b1"
    assert back.range == (3, 6)
    assert back.summary == "User asked for hi"


def test_block_defaults_and_next_id() -> None:
    assert Block.next_id([]) == "b1"
    existing = [Block(id="b1", start=0, end=1, messages=[], summary="")]
    assert Block.next_id(existing) == "b2"
    b = Block(id="b3", start=0, end=1, messages=[], summary="")
    assert b.layer == 0
    assert b.parent_id == ""
    assert b.restores == 0


def test_next_id_after_eviction_no_collision() -> None:
    blocks = [
        Block(id="b3", start=0, end=1, messages=[], summary=""),
        Block(id="b4", start=0, end=1, messages=[], summary=""),
        Block(id="b5", start=0, end=1, messages=[], summary=""),
    ]
    assert Block.next_id(blocks) == "b6"


def test_circuit_states() -> None:
    assert CircuitState.OK.value == "ok"
    assert {s.value for s in CircuitState} == {"ok", "warning", "error", "critical"}


def test_report_to_dict_shape() -> None:
    r = CompressionReport(
        triggered=True,
        layer_used=0,
        blocks_added=2,
        tokens_before=1000,
        tokens_after=400,
        skipped="",
        circuit=CircuitState.OK.value,
    )
    d = r.to_dict()
    assert d["blocks_added"] == 2
    assert d["tokens_saved"] == 600
    assert d["ratio_after"] == 0.4
    assert d["triggered"] is True
