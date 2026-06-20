"""JSONL chunk store. One record per line; replace/delete are filtered rewrites.

Record shape: {page_id, domain, kind, embed_text, hash}. Embedding-model-agnostic
— SP2 reads embed_text and produces vectors.
"""
from __future__ import annotations

import json
from pathlib import Path

from owaw.chunking import ChunkInput


class ChunkStore:
    def __init__(self, path: Path, domain: str):
        self._path = path
        self._domain = domain

    def read_all(self) -> list[dict]:
        if not self._path.exists():
            return []
        return [
            json.loads(line)
            for line in self._path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def _rewrite(self, rows: list[dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
        )

    def replace_page(self, page_id: str, chunks: list[ChunkInput]) -> None:
        rows = [r for r in self.read_all() if r["page_id"] != page_id]
        for c in chunks:
            rows.append({
                "page_id": page_id,
                "domain": self._domain,
                "kind": c.kind,
                "embed_text": c.embed_text,
                "hash": c.hash,
            })
        self._rewrite(rows)

    def delete_page(self, page_id: str) -> None:
        self._rewrite([r for r in self.read_all() if r["page_id"] != page_id])
