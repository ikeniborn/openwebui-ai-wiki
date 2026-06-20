"""Persisted sync state: maps each pushed chunk hash to its OpenWebUI entry id.

Mirrors manifest.py. Stored at state/sync_<collection>.json so diffs are O(changed).
"""
from __future__ import annotations

import json
from pathlib import Path


class SyncState:
    def __init__(self, path: Path, entries: dict[str, str]):
        self._path = path
        self._entries = entries

    @classmethod
    def load(cls, path: Path) -> "SyncState":
        entries: dict[str, str] = {}
        if path.exists():
            entries = json.loads(path.read_text(encoding="utf-8"))
        return cls(path, entries)

    def synced_hashes(self) -> set[str]:
        return set(self._entries)

    def entry_id(self, h: str) -> str | None:
        return self._entries.get(h)

    def mark(self, h: str, entry_id: str) -> None:
        self._entries[h] = entry_id

    def forget(self, h: str) -> None:
        self._entries.pop(h, None)

    def replace(self, mapping: dict[str, str]) -> None:
        self._entries = dict(mapping)

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._entries, indent=2), encoding="utf-8")
