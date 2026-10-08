from __future__ import annotations

import copy

from core.context import ContextEngine, build_chip
from core.context.chip import build_chip as chip_fn


def msg(role: str, content: str) -> dict:
    return {"role": role, "content": content}


def big_msgs(n: int = 8) -> list[dict]:
    return [
        msg("user" if i % 2 == 0 else "assistant", chr(97 + i) * 300)
        for i in range(n)
    ]


def test_full_ladder_end_to_end(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SCHOOL_COMPRESS_WINDOW_TOKENS", "200")
    monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
    engine = ContextEngine(str(tmp_path), "integration", judge=None)
    msgs = big_msgs()
    snapshot = copy.deepcopy(msgs)

    assert engine.should_compress(msgs)
    report = engine.compress(msgs)
    assert report.triggered
    assert report.layer_used in {0, 1, 2}
    assert report.blocks_added >= 1
    assert report.tokens_after <= report.tokens_before
    assert msgs == snapshot  # originals never mutated

    view = engine.view(msgs)
    assert view.mutated is False
    assert len(view.messages) <= len(msgs)
    markers = [m for m in view.messages if m.get("school_block")]
    assert markers

    chip = chip_fn(blocks_added=report.blocks_added)
    assert chip.startswith("[school] compacted")


def test_fail_open_matrix(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SCHOOL_COMPRESS_WINDOW_TOKENS", "200")
    monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")

    # 1. judge=None -> ladder still works (L0/L2)
    e1 = ContextEngine(str(tmp_path), "m1", judge=None)
    r1 = e1.compress(big_msgs())
    assert r1.messages is not None

    # 2. broken judge (raises) -> fail to L2, never raises
    class Boom:
        def __call__(self, prompt: str) -> tuple[str, str]:
            raise RuntimeError("no")

    e2 = ContextEngine(str(tmp_path), "m2", judge=Boom())
    r2 = e2.compress(big_msgs())
    assert r2.triggered or r2.skipped in {"fail_open"}
    assert r2.messages is not None

    # 3. non-list / empty inputs
    r3 = e1.compress([])  # type: ignore[arg-type]
    assert r3.skipped in {"empty", "below_threshold"}
    r4 = e1.compress(None)  # type: ignore[arg-type]
    assert r4.skipped in {"empty", "fail_open"}
    assert e1.view([]).messages == []

    # 4. kill switch still wins over everything
    monkeypatch.setenv("SCHOOL_COMPRESS", "0")
    r5 = e1.compress(big_msgs())
    assert r5.skipped == "kill_switch"


def test_view_of_restored_session_matches_block_payload(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SCHOOL_COMPRESS_WINDOW_TOKENS", "200")
    monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
    engine = ContextEngine(str(tmp_path), "rt", judge=None)
    msgs = big_msgs()
    engine.compress(msgs)
    restored = engine.restore()
    assert restored["ok"] is True
    # restored originals are exactly the stored verbatim copies
    block = engine.store.get(restored["id"])
    assert block is not None
    assert restored["messages"] == block.messages


def test_public_exports() -> None:
    import core.context as pkg

    for name in ("ContextEngine", "Block", "CompressionReport", "build_chip"):
        assert hasattr(pkg, name), name
    assert build_chip is chip_fn
