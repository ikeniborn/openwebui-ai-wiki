"""In-memory KnowledgeClient for engine tests. Records text + meta for round-trip asserts."""
from __future__ import annotations


class FakeKnowledgeClient:
    def __init__(self, fail_on: set[str] | None = None):
        self.entries: dict[str, dict] = {}  # entry_id -> {hash, text, meta}
        self._seq = 0
        self.fail_on = fail_on or set()
        self.add_calls = 0
        self.delete_calls = 0

    def add(self, hash: str, text: str, meta: dict) -> str:
        if hash in self.fail_on:
            raise RuntimeError(f"add failed for {hash}")
        self.add_calls += 1
        self._seq += 1
        eid = f"e{self._seq}"
        self.entries[eid] = {"hash": hash, "text": text, "meta": dict(meta)}
        return eid

    def delete(self, entry_id: str) -> None:
        self.delete_calls += 1
        self.entries.pop(entry_id, None)

    def list_entries(self) -> list[tuple[str, str]]:
        return [(eid, v["hash"]) for eid, v in self.entries.items()]
