"""Track processed source files by content hash for idempotent ingest."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Manifest:
    def __init__(self, path: Path, hashes: dict[str, str]):
        self._path = path
        self._hashes = hashes

    @classmethod
    def load(cls, path: Path) -> "Manifest":
        hashes: dict[str, str] = {}
        if path.exists():
            hashes = json.loads(path.read_text(encoding="utf-8"))
        return cls(path, hashes)

    def is_changed(self, src: Path) -> bool:
        return self._hashes.get(str(src)) != _hash_file(src)

    def mark(self, src: Path) -> None:
        self._hashes[str(src)] = _hash_file(src)

    def forget(self, src: Path) -> None:
        self._hashes.pop(str(src), None)

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._hashes, indent=2), encoding="utf-8")
