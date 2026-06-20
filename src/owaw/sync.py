"""Sync core: read SP1 chunk records into a desired set, diff against sync-state.

The engine (SyncEngine) is added later in this module; this layer is pure and
fully unit-testable without any OpenWebUI client.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DesiredEntry:
    hash: str
    embed_text: str
    domain: str
    page_id: str
    kind: str


def build_desired(chunks_dir: Path) -> dict[str, DesiredEntry]:
    """Load every chunks/*.jsonl record into a hash-keyed desired set (dedup by hash)."""
    out: dict[str, DesiredEntry] = {}
    if not chunks_dir.exists():
        return out
    for f in sorted(chunks_dir.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            out.setdefault(
                r["hash"],
                DesiredEntry(
                    hash=r["hash"],
                    embed_text=r["embed_text"],
                    domain=r["domain"],
                    page_id=r["page_id"],
                    kind=r["kind"],
                ),
            )
    return out


def diff(desired_hashes: set[str], synced_hashes: set[str]) -> tuple[set[str], set[str]]:
    """Return (to_add, to_delete): new hashes to push, stale hashes to remove."""
    return desired_hashes - synced_hashes, synced_hashes - desired_hashes
