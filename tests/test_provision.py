import json

import httpx

from owaw.config import AgentConfig, OpenWebUIConfig
from owaw.owui.provision import OpenWebUIProvisioner, provision_agent


def _provisioner(handler):
    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport, base_url="http://owui:8080")
    return OpenWebUIProvisioner(base_url="http://owui:8080", token="T",
                                http=http, sleep=lambda _s: None)


def test_upsert_tool_creates_when_absent():
    seen = []

    def handler(request):
        p = request.url.path
        seen.append((request.method, p))
        if request.method == "GET" and p == "/api/v1/tools/id/wiki_docs":
            return httpx.Response(404, json={"detail": "not found"})
        if p == "/api/v1/tools/create":
            body = json.loads(request.content)
            assert body["id"] == "wiki_docs"
            assert "class Tools" in body["content"]
            assert "specs" not in body
            assert body["access_grants"] == [
                {"principal_type": "user", "principal_id": "*", "permission": "read"}
            ]
            return httpx.Response(200, json={"id": "wiki_docs"})
        raise AssertionError(f"unexpected {request.method} {p}")

    tid = _provisioner(handler).upsert_tool("wiki_docs", "Wiki Docs", "class Tools: pass", "d")
    assert tid == "wiki_docs"
    assert ("POST", "/api/v1/tools/create") in seen


def test_upsert_tool_updates_when_exists():
    seen = []

    def handler(request):
        p = request.url.path
        seen.append((request.method, p))
        if request.method == "GET" and p == "/api/v1/tools/id/wiki_docs":
            return httpx.Response(200, json={"id": "wiki_docs"})
        if p == "/api/v1/tools/id/wiki_docs/update":
            return httpx.Response(200, json={"id": "wiki_docs"})
        raise AssertionError(f"unexpected {request.method} {p}")

    _provisioner(handler).upsert_tool("wiki_docs", "Wiki Docs", "class Tools: pass", "d")
    assert ("POST", "/api/v1/tools/id/wiki_docs/update") in seen
    assert ("POST", "/api/v1/tools/create") not in seen


def test_resolve_collection_id():
    def handler(request):
        if request.url.path == "/api/v1/knowledge/":
            return httpx.Response(200, json=[{"id": "cid", "name": "ai-wiki"}])
        raise AssertionError

    assert _provisioner(handler).resolve_collection_id("ai-wiki") == "cid"
    assert _provisioner(handler).resolve_collection_id("absent") is None


def test_upsert_model_attaches_knowledge_tool_and_prompt():
    def handler(request):
        p = request.url.path
        if request.method == "GET" and p == "/api/v1/models/model":
            return httpx.Response(404, json={"detail": "not found"})
        if p == "/api/v1/models/create":
            body = json.loads(request.content)
            assert body["base_model_id"] == "gpt-4o"
            assert body["meta"]["toolIds"] == ["wiki_docs"]
            assert body["meta"]["knowledge"] == [
                {"id": "cid", "name": "ai-wiki", "type": "collection"}
            ]
            assert "Doc Agent" in body["params"]["system"]
            assert "function_calling" not in body["params"]   # native disables auto-RAG (Task 4)
            assert body["access_grants"][0]["principal_id"] == "*"
            return httpx.Response(200, json={"id": "ai-wiki-agent"})
        raise AssertionError(f"unexpected {request.method} {p}")

    mid = _provisioner(handler).upsert_model(
        model_id="ai-wiki-agent", name="Doc Agent", base_model="gpt-4o",
        system_prompt="You are the Doc Agent.", collection_id="cid",
        collection_name="ai-wiki", tool_id="wiki_docs",
    )
    assert mid == "ai-wiki-agent"


def test_provision_agent_end_to_end():
    seen = []

    def handler(request):
        p = request.url.path
        seen.append((request.method, p))
        if request.method == "GET" and p == "/api/v1/tools/id/wiki_docs":
            return httpx.Response(404, json={})
        if p == "/api/v1/tools/create":
            return httpx.Response(200, json={"id": "wiki_docs"})
        if p == "/api/v1/tools/id/wiki_docs/valves/update":
            assert json.loads(request.content)["roots"] == "/data/wiki,/data/sources"
            return httpx.Response(200, json={})
        if p == "/api/v1/knowledge/":
            return httpx.Response(200, json=[{"id": "cid", "name": "ai-wiki"}])
        if request.method == "GET" and p == "/api/v1/models/model":
            return httpx.Response(404, json={})
        if p == "/api/v1/models/create":
            return httpx.Response(200, json={"id": "ai-wiki-agent"})
        raise AssertionError(f"unexpected {request.method} {p}")

    ow = OpenWebUIConfig(base_url="http://owui:8080", collection="ai-wiki")
    agent = AgentConfig(base_model="gpt-4o")
    res = provision_agent(ow, agent, provisioner=_provisioner(handler))
    assert res == {"tool_id": "wiki_docs", "model_id": "ai-wiki-agent", "collection_id": "cid"}
    assert ("POST", "/api/v1/tools/create") in seen
    assert ("POST", "/api/v1/models/create") in seen
