import json
import re

import httpx

from owaw.knowledge import OpenWebUIKnowledgeClient


def _client(handler, **kw):
    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport, base_url="http://owui:8080")
    return OpenWebUIKnowledgeClient(
        base_url="http://owui:8080", collection="ai-wiki", token="T",
        http=http, sleep=lambda _s: None, **kw,
    )


def _uploaded_metadata(request: httpx.Request) -> dict:
    """Extract the file_metadata JSON part from a multipart upload request body."""
    body = request.content.decode("utf-8", "ignore")
    m = re.search(r'name="file_metadata".*?\r?\n\r?\n(.*?)\r?\n--', body, re.DOTALL)
    assert m, "upload is missing the file_metadata part"
    return json.loads(m.group(1))


def test_add_single_call_uploads_with_metadata_and_knowledge_id():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        p = request.url.path
        if request.method == "GET" and p == "/api/v1/knowledge/":
            return httpx.Response(200, json=[{"id": "cid", "name": "ai-wiki"}])
        if request.method == "POST" and p == "/api/v1/files/":
            assert request.headers["authorization"] == "Bearer T"
            assert _uploaded_metadata(request) == {
                "domain": "infra", "page_id": "p", "kind": "summary",
                "file_hash": "abc123", "knowledge_id": "cid",
            }
            assert 'filename="abc123.md"' in request.content.decode("utf-8", "ignore")
            return httpx.Response(200, json={"id": "file-1"})
        raise AssertionError(f"unexpected {request.method} {p}")

    client = _client(handler)
    entry_id = client.add("abc123", "embed text",
                          {"domain": "infra", "page_id": "p", "kind": "summary"})
    assert entry_id == "file-1"
    # single-call path: no separate /file/add request is made
    assert ("POST", "/api/v1/knowledge/cid/file/add") not in seen


def test_add_creates_collection_when_missing():
    def handler(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if request.method == "GET" and p == "/api/v1/knowledge/":
            return httpx.Response(200, json=[])          # none exist yet
        if request.method == "POST" and p == "/api/v1/knowledge/create":
            return httpx.Response(200, json={"id": "newcid", "name": "ai-wiki"})
        if request.method == "POST" and p == "/api/v1/files/":
            assert _uploaded_metadata(request)["knowledge_id"] == "newcid"
            return httpx.Response(200, json={"id": "file-9"})
        raise AssertionError(f"unexpected {request.method} {p}")

    assert _client(handler).add("h", "t", {}) == "file-9"


def test_delete_removes_from_collection_then_deletes_file():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        seen.append((request.method, p))
        if request.method == "GET" and p == "/api/v1/knowledge/":
            return httpx.Response(200, json=[{"id": "cid", "name": "ai-wiki"}])
        if request.method == "POST" and p == "/api/v1/knowledge/cid/file/remove":
            return httpx.Response(200, json={"id": "cid"})
        if request.method == "DELETE" and p == "/api/v1/files/file-1":
            return httpx.Response(200, json={"ok": True})
        raise AssertionError(f"unexpected {request.method} {p}")

    _client(handler).delete("file-1")
    assert ("POST", "/api/v1/knowledge/cid/file/remove") in seen
    assert ("DELETE", "/api/v1/files/file-1") in seen


def test_list_entries_recovers_hash_from_meta_file_hash():
    def handler(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if request.method == "GET" and p == "/api/v1/knowledge/":
            return httpx.Response(200, json=[{"id": "cid", "name": "ai-wiki"}])
        if request.method == "GET" and p == "/api/v1/knowledge/cid":
            return httpx.Response(200, json={"id": "cid", "files": [
                {"id": "file-1", "meta": {"file_hash": "h1", "name": "h1.md"}},
                {"id": "file-2", "meta": {"file_hash": "h2", "name": "h2.md"}},
            ]})
        raise AssertionError(f"unexpected {request.method} {p}")

    assert sorted(_client(handler).list_entries()) == [("file-1", "h1"), ("file-2", "h2")]


def test_add_retries_on_transient_5xx_then_succeeds():
    calls = {"files": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if request.method == "GET" and p == "/api/v1/knowledge/":
            return httpx.Response(200, json=[{"id": "cid", "name": "ai-wiki"}])
        if request.method == "POST" and p == "/api/v1/files/":
            calls["files"] += 1
            if calls["files"] == 1:
                return httpx.Response(503, json={"err": "warming up"})
            return httpx.Response(200, json={"id": "file-1"})
        raise AssertionError(f"unexpected {request.method} {p}")

    client = _client(handler, retries=3)
    assert client.add("h", "t", {}) == "file-1"
    assert calls["files"] == 2  # one 503, one success
