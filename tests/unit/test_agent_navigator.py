"""S7 tests: school_navigate."""

from __future__ import annotations

from pathlib import Path

from core.agent.navigator import navigate


class TestNavigate:
    def test_navigate_read(self, tmp_path: Path) -> None:
        (tmp_path / "hello.txt").write_text("world", encoding="utf-8")
        r = navigate(str(tmp_path), "read", path="hello.txt")
        assert r.ok is True
        assert "world" in r.content

    def test_navigate_list(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("x", encoding="utf-8")
        (tmp_path / "b.txt").write_text("y", encoding="utf-8")
        r = navigate(str(tmp_path), "list", path=".")
        assert r.ok is True
        assert "a.txt" in r.entries
        assert "b.txt" in r.entries

    def test_navigate_search(self, tmp_path: Path) -> None:
        (tmp_path / "file.txt").write_text("hello world\nfoo bar\nhello again\n", encoding="utf-8")
        r = navigate(str(tmp_path), "search", path=".", pattern="hello")
        assert r.ok is True
        assert len(r.matches) == 2

    def test_navigate_map(self, tmp_path: Path) -> None:
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "inner.txt").write_text("data", encoding="utf-8")
        (tmp_path / "top.txt").write_text("x", encoding="utf-8")
        r = navigate(str(tmp_path), "map", path=".", depth=2)
        assert r.ok is True
        assert "top.txt" in r.tree

    def test_navigate_kill_switch(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("SCHOOL_NAVIGATE", "0")
        r = navigate(str(tmp_path), "read", path="missing.txt")
        assert r.ok is True

    def test_navigate_unknown_action(self, tmp_path: Path) -> None:
        r = navigate(str(tmp_path), "invalid")
        assert r.ok is False

    def test_navigate_read_not_file(self, tmp_path: Path) -> None:
        r = navigate(str(tmp_path), "read", path="missing.txt")
        assert r.ok is False
