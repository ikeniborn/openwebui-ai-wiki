"""OpenWebUI Knowledge client: protocol + HTTP implementation.

The protocol decouples the sync engine from OpenWebUI's API surface so the
engine is testable against a fake, and so the single highest-risk unknown
(the exact Knowledge endpoints) is isolated to one concrete class.
"""
from __future__ import annotations

from typing import Protocol


class KnowledgeClient(Protocol):
    def add(self, hash: str, text: str, meta: dict) -> str:
        """Push one entry (text=embed_text, named by hash); return its entry id."""
        ...

    def delete(self, entry_id: str) -> None:
        """Remove the entry from the collection."""
        ...

    def list_entries(self) -> list[tuple[str, str]]:
        """List current collection entries as (entry_id, hash) pairs."""
        ...
