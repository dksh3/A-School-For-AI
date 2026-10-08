"""S7 tests: school_explore."""

from __future__ import annotations

from pathlib import Path

from core.agent.explorer import explore


class TestExplore:
    def test_explore_structure(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text("print('hi')", encoding="utf-8")
        (tmp_path / "utils.py").write_text("x=1", encoding="utf-8")
        r = explore(str(tmp_path), ".")
        assert r.ok is True
        assert "2 files" in r.structure

    def test_explore_patterns(self, tmp_path: Path) -> None:
        for i in range(3):
            (tmp_path / f"f{i}.py").write_text("x", encoding="utf-8")
        (tmp_path / "doc.md").write_text("# doc", encoding="utf-8")
        r = explore(str(tmp_path), ".")
        assert r.ok is True
        assert any(".py" in p for p in r.patterns)

    def test_explore_conventions(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text("x", encoding="utf-8")
        (tmp_path / "pyproject.toml").write_text("[project]", encoding="utf-8")
        r = explore(str(tmp_path), ".")
        assert "Python packaging" in r.conventions

    def test_explore_kill_switch(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("SCHOOL_EXPLORE", "0")
        r = explore(str(tmp_path), ".")
        assert r.ok is True
        assert r.structure == ""

    def test_explore_not_found(self, tmp_path: Path) -> None:
        r = explore(str(tmp_path), "nonexistent_dir")
        assert r.ok is False
