"""S2 Task 1: DCP coexistence state, detection, and view mode."""

from __future__ import annotations

import json

import pytest

from core.context.coexist import (
    DCP_TOKEN,
    OFFER_TEXT,
    clear_cache,
    ctx_enabled,
    detect_dcp,
    detect_dcp_cached,
    load_state,
    save_state,
    state_path,
    view_mode,
)


@pytest.fixture(autouse=True)
def _fresh_cache():
    clear_cache()
    yield
    clear_cache()


def test_ctx_enabled_kill_switch(monkeypatch) -> None:
    monkeypatch.delenv("SCHOOL_CTX", raising=False)
    assert ctx_enabled() is True
    monkeypatch.setenv("SCHOOL_CTX", "0")
    assert ctx_enabled() is False


def test_view_mode_off_when_compress_disabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SCHOOL_COMPRESS", "0")
    assert view_mode(str(tmp_path), home=tmp_path / "home") == "off"
    monkeypatch.delenv("SCHOOL_COMPRESS", raising=False)
    assert view_mode(str(tmp_path), home=tmp_path / "home") == "school"


def test_state_defaults_and_roundtrip(tmp_path) -> None:
    wt = str(tmp_path)
    assert load_state(wt) == {
        "version": 1,
        "dcp_seen": False,
        "offer_shown": False,
        "decision": "",
    }
    save_state(wt, {"offer_shown": True, "dcp_seen": True})
    state = load_state(wt)
    assert state["offer_shown"] is True
    assert state["dcp_seen"] is True
    save_state(wt, {"decision": "switch"})
    assert load_state(wt)["decision"] == "switch"
    expected = tmp_path / ".school" / "context" / "coexistence.json"
    assert state_path(wt) == expected


def test_state_rejects_unknown_decision(tmp_path) -> None:
    save_state(str(tmp_path), {"decision": "destroy"})
    assert load_state(str(tmp_path))["decision"] == ""


def test_corrupt_state_fails_open(tmp_path) -> None:
    path = state_path(str(tmp_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    state = load_state(str(tmp_path))
    assert state["decision"] == ""
    assert state["offer_shown"] is False


def test_detect_dcp_project_config(tmp_path) -> None:
    (tmp_path / "opencode.json").write_text(
        json.dumps({"plugin": ["@tarquinen/opencode-dcp"]}), encoding="utf-8"
    )
    assert detect_dcp(str(tmp_path), home=tmp_path / "home") is True


def test_detect_dcp_absent(tmp_path) -> None:
    (tmp_path / "opencode.json").write_text(
        json.dumps({"plugin": []}), encoding="utf-8"
    )
    assert detect_dcp(str(tmp_path), home=tmp_path / "home") is False


def test_detect_dcp_jsonc_and_tuple_entry(tmp_path) -> None:
    (tmp_path / "opencode.jsonc").write_text(
        '// comment\n{"plugin": [["@tarquinen/opencode-dcp", {"depth": 3}]]}',
        encoding="utf-8",
    )
    assert detect_dcp(str(tmp_path), home=tmp_path / "home") is True


def test_detect_dcp_project_subdir_config(tmp_path) -> None:
    sub = tmp_path / ".opencode"
    sub.mkdir()
    (sub / "opencode.json").write_text(
        '{"plugin": ["@tarquinen/opencode-dcp"]}', encoding="utf-8"
    )
    assert detect_dcp(str(tmp_path), home=tmp_path / "home") is True


def test_detect_dcp_global_config_uses_home_param(tmp_path) -> None:
    home = tmp_path / "home"
    cfg = home / ".config" / "opencode"
    cfg.mkdir(parents=True)
    (cfg / "opencode.json").write_text(
        '{"plugin": ["@tarquinen/opencode-dcp"]}', encoding="utf-8"
    )
    assert detect_dcp(str(tmp_path / "empty"), home=home) is True


def test_detect_dcp_plugin_dir_by_name(tmp_path) -> None:
    plug = tmp_path / ".opencode" / "plugins"
    plug.mkdir(parents=True)
    (plug / "dcp.ts").write_text("// nothing", encoding="utf-8")
    assert detect_dcp(str(tmp_path), home=tmp_path / "home") is True


def test_detect_dcp_plugin_dir_by_token(tmp_path) -> None:
    plug = tmp_path / ".opencode" / "plugins"
    plug.mkdir(parents=True)
    (plug / "other.ts").write_text(f'import "{DCP_TOKEN}"', encoding="utf-8")
    assert detect_dcp(str(tmp_path), home=tmp_path / "home") is True


def test_detect_dcp_bounded_read(tmp_path) -> None:
    pad = "x" * 1_200_000
    (tmp_path / "opencode.json").write_text(
        f'{{"plugin": ["{DCP_TOKEN}"], "pad": "{pad}"}}', encoding="utf-8"
    )
    assert detect_dcp(str(tmp_path), home=tmp_path / "home") is True
    from core.context.coexist import _read_bounded

    big = tmp_path / "big.json"
    big.write_text("x" * (2_000_000) + DCP_TOKEN, encoding="utf-8")
    assert len(_read_bounded(big)) <= 2_000_000
    assert DCP_TOKEN not in _read_bounded(big)

def test_detect_dcp_cached(tmp_path) -> None:
    wt = str(tmp_path)
    home = tmp_path / "home"
    assert detect_dcp_cached(wt, home=home) is False
    (tmp_path / "opencode.json").write_text(
        json.dumps({"plugin": [DCP_TOKEN]}), encoding="utf-8"
    )
    assert detect_dcp_cached(wt, home=home) is False  # negative answer is cached
    clear_cache()
    assert detect_dcp_cached(wt, home=home) is True


def test_view_mode_switch_overrides_dcp(tmp_path) -> None:
    wt = str(tmp_path)
    home = tmp_path / "home"
    (tmp_path / "opencode.json").write_text(
        json.dumps({"plugin": [DCP_TOKEN]}), encoding="utf-8"
    )
    assert view_mode(wt, home=home) == "dcp"
    save_state(wt, {"decision": "switch"})
    assert view_mode(wt, home=home) == "school"


def test_view_mode_keep_and_dcp_hint(tmp_path, monkeypatch) -> None:
    wt = str(tmp_path)
    home = tmp_path / "home"
    assert view_mode(wt, home=home) == "school"
    assert view_mode(wt, dcp_hint=True, home=home) == "dcp"
    save_state(wt, {"decision": "keep"})
    assert view_mode(wt, home=home) == "dcp"
    monkeypatch.setenv("SCHOOL_CTX", "0")
    assert view_mode(wt, home=home) == "off"


def test_offer_text_matches_spec() -> None:
    assert OFFER_TEXT.startswith(
        "School can now handle compression — with restore, budgets, and status."
    )
    assert "school context switch" in OFFER_TEXT
    assert "school context keep" in OFFER_TEXT
