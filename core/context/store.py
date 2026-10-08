# core/context/store.py
from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any

from core.context.types import Block
from school.config import resolve_memory_dir

_LOCK = threading.RLock()
_MAX_BLOCKS_DEFAULT = 200
_MAX_BYTES_DEFAULT = 5 * 1024 * 1024


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def context_dir(worktree: str) -> Path:
    return resolve_memory_dir(worktree).parent / "context"


def session_file(worktree: str, session_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", session_id or "default")
    safe = re.sub(r"\.{2,}", "_", safe)
    safe = safe[:80].rstrip(". ")
    return context_dir(worktree) / f"{safe}.blocks.json"


class BlockStore:
    """Per-session block file: atomic writes, bounded size, fail-open load."""

    def __init__(self, worktree: str, session_id: str) -> None:
        self.path = session_file(worktree, session_id)

    def load(self) -> list[Block]:
        try:
            raw = self.path.read_text(encoding="utf-8")
            data = json.loads(raw)
            items = data.get("blocks") if isinstance(data, dict) else None
            if not isinstance(items, list):
                return []
            out: list[Block] = []
            for item in items:
                if isinstance(item, dict):
                    try:
                        block = Block.from_dict(item)
                    except (IndexError, KeyError, ValueError, TypeError):
                        continue
                    if block.id:
                        out.append(block)
            return out
        except (OSError, json.JSONDecodeError, ValueError, TypeError, IndexError, KeyError):
            return []

    def save(self, blocks: list[Block]) -> None:
        max_blocks = _env_int("SCHOOL_COMPRESS_MAX_BLOCKS", _MAX_BLOCKS_DEFAULT)
        max_bytes = _env_int("SCHOOL_COMPRESS_MAX_BYTES", _MAX_BYTES_DEFAULT)
        kept = blocks[-max_blocks:] if max_blocks > 0 else []
        payload: dict[str, Any] = {
            "version": 1,
            "blocks": [b.to_dict() for b in kept],
        }
        text = json.dumps(payload, ensure_ascii=False, indent=1)
        # hard byte bound: drop oldest blocks until under limit
        while len(text.encode("utf-8")) > max_bytes and kept:
            kept = kept[1:]
            payload["blocks"] = [b.to_dict() for b in kept]
            text = json.dumps(payload, ensure_ascii=False, indent=1)
        with _LOCK:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(
                dir=str(self.path.parent), suffix=".tmp", prefix="blocks-"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(text)
                os.replace(tmp, self.path)
            except OSError:
                with contextlib.suppress(OSError):
                    os.unlink(tmp)
                raise

    def add(self, block: Block) -> None:
        with _LOCK:
            blocks = self.load()
            blocks.append(block)
            self.save(blocks)

    def update(self, block: Block) -> None:
        with _LOCK:
            blocks = self.load()
            for i, existing in enumerate(blocks):
                if existing.id == block.id:
                    blocks[i] = block
                    break
            else:
                blocks.append(block)
            self.save(blocks)

    def get(self, block_id: str) -> Block | None:
        return next((b for b in self.load() if b.id == block_id), None)
