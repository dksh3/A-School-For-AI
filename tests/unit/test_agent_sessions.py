"""S7 tests: school_session."""

from __future__ import annotations

from pathlib import Path

from core.agent.sessions import session


class TestSession:
    def test_session_create(self, tmp_path: Path) -> None:
        r = session(str(tmp_path), "create", focus="test focus")
        assert r.ok is True
        assert r.session_id.startswith("s")
        assert r.focus == "test focus"

    def test_session_resume(self, tmp_path: Path) -> None:
        session(str(tmp_path), "create", session_id="s1", focus="abc")
        r = session(str(tmp_path), "resume", session_id="s1")
        assert r.ok is True
        assert r.session_id == "s1"

    def test_session_summarize(self, tmp_path: Path) -> None:
        session(str(tmp_path), "create", session_id="s1", focus="xyz")
        r = session(str(tmp_path), "summarize", session_id="s1")
        assert r.ok is True
        assert "s1" in r.summary

    def test_session_export(self, tmp_path: Path) -> None:
        session(str(tmp_path), "create", session_id="s1", focus="data")
        r = session(str(tmp_path), "export", session_id="s1")
        assert r.ok is True
        assert "s1" in r.data

    def test_session_list(self, tmp_path: Path) -> None:
        session(str(tmp_path), "create", session_id="s1")
        session(str(tmp_path), "create", session_id="s2")
        r = session(str(tmp_path), "list")
        assert r.ok is True
        assert len(r.sessions) == 2

    def test_session_not_found(self, tmp_path: Path) -> None:
        r = session(str(tmp_path), "resume", session_id="missing")
        assert r.ok is False

    def test_session_unknown_action(self, tmp_path: Path) -> None:
        r = session(str(tmp_path), "invalid")
        assert r.ok is False

    def test_session_kill_switch(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("SCHOOL_SESSION", "0")
        r = session(str(tmp_path), "create")
        assert r.ok is True
        assert r.session_id == ""
