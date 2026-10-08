from __future__ import annotations

import json

from core.context.engine import ContextEngine


def msg(role: str, content: str) -> dict:
    return {"role": role, "content": content}


def compress_once(tmp_path, session: str = "s1") -> ContextEngine:
    engine = ContextEngine(str(tmp_path), session, judge=None)
    msgs = [msg("user", "q" * 400), msg("assistant", "a" * 400)]
    engine.compress(msgs)
    return engine


def test_blocks_survive_restart(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SCHOOL_COMPRESS_WINDOW_TOKENS", "100")
    monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
    engine = compress_once(tmp_path)
    before = [b.to_dict() for b in engine.store.load()]
    assert before  # something persisted

    fresh = ContextEngine(str(tmp_path), "s1", judge=None)  # simulated restart
    after = [b.to_dict() for b in fresh.store.load()]
    assert after == before


def test_restore_is_idempotent_and_counted(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SCHOOL_COMPRESS_WINDOW_TOKENS", "100")
    monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
    engine = compress_once(tmp_path)
    first = engine.restore()  # expand-last
    assert first["ok"] is True
    first_id = first["id"]
    second = engine.restore(first_id)
    assert second["ok"] is True
    assert second["messages"] == first["messages"]
    assert second["restores"] == 2  # counted each call, same payload

    # count persists across restart
    fresh = ContextEngine(str(tmp_path), "s1", judge=None)
    again = fresh.restore(first_id)
    assert again["restores"] == 3


def test_restore_errors_fail_closed(tmp_path) -> None:
    engine = ContextEngine(str(tmp_path), "empty", judge=None)
    assert engine.restore() == {"ok": False, "reason": "no_blocks"}
    assert engine.restore("b999") == {"ok": False, "reason": "no_blocks"}


def test_corrupt_block_file_recoverable(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SCHOOL_COMPRESS_WINDOW_TOKENS", "100")
    monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
    engine = compress_once(tmp_path)
    engine.store.path.write_text("{broken", encoding="utf-8")
    assert engine.store.load() == []
    # engine still functional after corruption (fails open, then re-saves)
    report = engine.compress([msg("user", "q" * 400), msg("assistant", "a" * 400)])
    assert report.skipped in {"", None} or report.triggered or report.skipped == "fail_open"
    data = json.loads(engine.store.path.read_text(encoding="utf-8"))
    assert data["version"] == 1


def test_sessions_are_isolated(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SCHOOL_COMPRESS_WINDOW_TOKENS", "100")
    monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
    e1 = ContextEngine(str(tmp_path), "alpha", judge=None)
    e1.compress([msg("user", "q" * 400), msg("assistant", "a" * 400)])
    e2 = ContextEngine(str(tmp_path), "beta", judge=None)
    assert e2.store.load() == []
    assert e1.store.path != e2.store.path


def test_restore_unknown_id_with_blocks_present(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SCHOOL_COMPRESS_WINDOW_TOKENS", "100")
    monkeypatch.setenv("SCHOOL_COMPRESS_TAIL_TOKENS", "0")
    engine = compress_once(tmp_path)
    assert engine.store.load()
    assert engine.restore("b999") == {"ok": False, "reason": "block_not_found"}
