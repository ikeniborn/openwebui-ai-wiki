"""Sync core: read SP1 chunk records into a desired set, diff against sync-state.

The engine (SyncEngine) is added later in this module; this layer is pure and
fully unit-testable without any OpenWebUI client.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


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


@dataclass(frozen=True)
class SyncResult:
    added: int
    deleted: int
    unchanged: int


class SyncEngine:
    """Converge the OpenWebUI collection to the on-disk desired set, via a KnowledgeClient."""

    def __init__(self, client, state, chunks_dir: Path):
        self._client = client
        self._state = state
        self._chunks_dir = chunks_dir

    def sync(self) -> "SyncResult":
        desired = build_desired(self._chunks_dir)
        to_add, to_delete = diff(set(desired), self._state.synced_hashes())
        added = deleted = 0
        for h in sorted(to_add):
            e = desired[h]
            try:
                eid = self._client.add(
                    h, e.embed_text,
                    {"domain": e.domain, "page_id": e.page_id, "kind": e.kind},
                )
                self._state.mark(h, eid)
                added += 1
            except Exception:
                logger.exception("knowledge add failed for hash %s", h)
        for h in sorted(to_delete):
            try:
                self._client.delete(self._state.entry_id(h))
                self._state.forget(h)
                deleted += 1
            except Exception:
                logger.exception("knowledge delete failed for hash %s", h)
        self._state.save()
        unchanged = len(set(desired) & self._state.synced_hashes()) - added
        return SyncResult(added=added, deleted=deleted, unchanged=unchanged)

    def reconcile(self) -> "SyncResult":
        """Full reconcile: trust the live collection as state, then converge to desired.

        Rebuilds sync-state from the collection listing (handles stale state and
        orphan entries), persists it, then runs an ordinary sync().
        """
        present = self._client.list_entries()
        self._state.replace({h: eid for eid, h in present})
        self._state.save()
        return self.sync()
