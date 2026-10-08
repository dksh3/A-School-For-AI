from __future__ import annotations

import json

from core.context.store import BlockStore, context_dir, session_file
from core.context.types import Block


def _block(i: int) -> Block:
    return Block.make(f"b{i}", i, i + 1, [{"role": "user", "content": f"m{i}"}], f"sum {i}", 0)


def test_context_dir_is_sibling_of_memory(tmp_path) -> None:
    d = context_dir(str(tmp_path))
    assert d.name == "context"
    assert d.parent.name == ".school"


def test_session_file_sanitizes_id(tmp_path) -> None:
    f = session_file(str(tmp_path), "sess/../evil id")
    assert f.parent == context_dir(str(tmp_path))
    assert "/" not in f.name and ".." not in f.name
    assert f.name.endswith(".blocks.json")
    f2 = session_file(str(tmp_path), "x.")
    assert ".." not in f2.name
    assert f2.name.endswith(".blocks.json")


def test_roundtrip_and_get(tmp_path) -> None:
    store = BlockStore(str(tmp_path), "s1")
    assert store.load() == []
    store.add(_block(1))
    store.add(_block(2))
    assert [b.id for b in store.load()] == ["b1", "b2"]
    assert store.get("b2") is not None
    assert store.get("nope") is None


def test_save_is_atomic_valid_json(tmp_path) -> None:
    store = BlockStore(str(tmp_path), "s1")
    store.save([_block(1)])
    data = json.loads(store.path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["blocks"][0]["id"] == "b1"
    leftovers = [p.name for p in store.path.parent.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


def test_corrupt_file_fails_open_to_empty(tmp_path) -> None:
    store = BlockStore(str(tmp_path), "s1")
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{not json", encoding="utf-8")
    assert store.load() == []
    # and it recovers on next save
    store.add(_block(1))
    assert len(store.load()) == 1


def test_corrupt_block_record_is_skipped(tmp_path) -> None:
    store = BlockStore(str(tmp_path), "s1")
    store.path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "blocks": [
            _block(1).to_dict(),
            {"id": "bad", "range": [3], "messages": [], "summary": ""},
        ],
    }
    store.path.write_text(json.dumps(payload), encoding="utf-8")
    blocks = store.load()
    assert [b.id for b in blocks] == ["b1"]


def test_bounds_oldest_evicted(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SCHOOL_COMPRESS_MAX_BLOCKS", "3")
    store = BlockStore(str(tmp_path), "s1")
    for i in range(1, 6):
        store.add(_block(i))
    blocks = store.load()
    assert [b.id for b in blocks] == ["b3", "b4", "b5"]


def test_update_increments_restores(tmp_path) -> None:
    store = BlockStore(str(tmp_path), "s1")
    store.add(_block(1))
    b = store.get("b1")
    assert b is not None
    b.restores += 1
    store.update(b)
    assert store.get("b1").restores == 1
