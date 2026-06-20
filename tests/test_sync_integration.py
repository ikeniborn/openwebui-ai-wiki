import json
import re

import httpx

from owaw.knowledge import OpenWebUIKnowledgeClient
from owaw.sync import SyncEngine
from owaw.syncstate import SyncState


def _write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
        encoding="utf-8",
    )


def _rec(h, embed, kind="section"):
    return {"page_id": "p1", "domain": "infra", "kind": kind, "embed_text": embed, "hash": h}


class FakeOpenWebUI:
    """In-memory OpenWebUI for the single-call upload-with-metadata contract.

    On upload it parses file_metadata, stores it per file_id, and (because the
    metadata carries knowledge_id) auto-links the file to the collection. The
    collection GET echoes each file's meta, so metadata round-trips end to end.
    """

    def __init__(self):
        self.meta: dict[str, dict] = {}    # file_id -> stored file_metadata
        self.collection: set[str] = set()  # attached file_ids
        self._seq = 0

    @staticmethod
    def _file_metadata(request: httpx.Request) -> dict:
        body = request.content.decode("utf-8", "ignore")
        m = re.search(r'name="file_metadata".*?\r?\n\r?\n(.*?)\r?\n--', body, re.DOTALL)
        return json.loads(m.group(1)) if m else {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if request.method == "GET" and p == "/api/v1/knowledge/":
            return httpx.Response(200, json=[{"id": "cid", "name": "ai-wiki"}])
        if request.method == "POST" and p == "/api/v1/files/":
            self._seq += 1
            fid = f"file-{self._seq}"
            meta = self._file_metadata(request)
            self.meta[fid] = meta
            if meta.get("knowledge_id") == "cid":   # single-call auto-link
                self.collection.add(fid)
            return httpx.Response(200, json={"id": fid})
        if request.method == "POST" and p == "/api/v1/knowledge/cid/file/remove":
            body = json.loads(request.content)
            self.collection.discard(body["file_id"])
            return httpx.Response(200, json={"id": "cid"})
        if request.method == "DELETE" and p.startswith("/api/v1/files/"):
            self.meta.pop(p.rsplit("/", 1)[1], None)
            return httpx.Response(200, json={"ok": True})
        if request.method == "GET" and p == "/api/v1/knowledge/cid":
            files = [{"id": fid, "meta": self.meta[fid]} for fid in self.collection]
            return httpx.Response(200, json={"id": "cid", "files": files})
        raise AssertionError(f"unexpected {request.method} {p}")


def _make_client(fake):
    http = httpx.Client(transport=httpx.MockTransport(fake.handler), base_url="http://owui:8080")
    return OpenWebUIKnowledgeClient(
        base_url="http://owui:8080", collection="ai-wiki", token="T",
        http=http, sleep=lambda _s: None,
    )


def test_add_then_delete_converges_with_metadata_roundtrip(tmp_path):
    fake = FakeOpenWebUI()
    client = _make_client(fake)
    statepath = tmp_path / "state" / "sync_ai-wiki.json"
    chunks = tmp_path / "chunks" / "infra.jsonl"

    _write_jsonl(chunks, [_rec("h1", "alpha", kind="summary"), _rec("h2", "beta")])
    res = SyncEngine(client, SyncState.load(statepath), tmp_path / "chunks").reconcile()
    assert (res.added, res.deleted) == (2, 0)

    listed = {h: fid for fid, h in client.list_entries()}
    assert set(listed) == {"h1", "h2"}
    # metadata round-trips through OpenWebUI (spec metadata requirement + integration test)
    meta_h1 = fake.meta[listed["h1"]]
    assert meta_h1["domain"] == "infra"
    assert meta_h1["page_id"] == "p1"
    assert meta_h1["kind"] == "summary"
    assert meta_h1["file_hash"] == "h1"

    # remove h2 from source -> next reconcile deletes it from the collection
    _write_jsonl(chunks, [_rec("h1", "alpha", kind="summary")])
    res2 = SyncEngine(client, SyncState.load(statepath), tmp_path / "chunks").reconcile()
    assert (res2.added, res2.deleted) == (0, 1)
    assert {h for _, h in client.list_entries()} == {"h1"}
