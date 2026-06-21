"""Provision the OpenWebUI Doc Agent: upsert the Doc Tool + Workspace Model.

This is the ONLY SP3 OpenWebUI API egress. Endpoint paths, body shapes, and the
access-control representation are confirmed by the SP3 validation spike against the
deployed OpenWebUI 0.9.6 (docs/superpowers/specs/2026-06-20-sp3-openwebui-api-findings.md).
The retry/backoff pattern mirrors owaw.knowledge.OpenWebUIKnowledgeClient.
"""
from __future__ import annotations

import os
import time
from importlib.resources import files

import httpx

from owaw.config import AgentConfig, OpenWebUIConfig


def _public_grants() -> list[dict]:
    """Public read for all users (OpenWebUI 0.9.6 access_grants list). See the Task 4 findings."""
    return [{"principal_type": "user", "principal_id": "*", "permission": "read"}]


def doc_tool_source() -> str:
    return files("owaw.owui").joinpath("doc_tool.py").read_text(encoding="utf-8")


def agent_system_prompt() -> str:
    return files("owaw.prompts").joinpath("agent_query.md").read_text(encoding="utf-8")


class OpenWebUIProvisioner:
    def __init__(self, base_url: str, token: str, *,
                 http: httpx.Client | None = None, sleep=time.sleep, retries: int = 3):
        self._token = token
        self._sleep = sleep
        self._retries = retries
        self._http = http or httpx.Client(base_url=base_url, timeout=30.0)

    def _request(self, method: str, path: str, **kw) -> httpx.Response:
        headers = kw.pop("headers", {})
        headers = {"Authorization": f"Bearer {self._token}", **headers}
        last: Exception | None = None
        for attempt in range(self._retries):
            try:
                resp = self._http.request(method, path, headers=headers, **kw)
            except httpx.TransportError as e:
                last = e
                self._sleep(0.5 * (2 ** attempt))
                continue
            if resp.status_code >= 500:
                last = httpx.HTTPStatusError("server error", request=resp.request, response=resp)
                self._sleep(0.5 * (2 ** attempt))
                continue
            resp.raise_for_status()   # 4xx -> raises immediately, NOT retried
            return resp
        raise RuntimeError(f"OpenWebUI request failed after {self._retries} tries: {last}")

    def _exists(self, get_path: str) -> bool:
        """True if the resource exists; False on 404. GET-based existence check (Task 4 delta)."""
        try:
            self._request("GET", get_path)
            return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return False
            raise

    def upsert_tool(self, tool_id: str, name: str, content: str, description: str,
                    public: bool = True) -> str:
        body = {
            "id": tool_id,
            "name": name,
            "content": content,
            "meta": {"description": description},
            "access_grants": _public_grants() if public else [],
        }
        if self._exists(f"/api/v1/tools/id/{tool_id}"):
            self._request("POST", f"/api/v1/tools/id/{tool_id}/update", json=body)
        else:
            self._request("POST", "/api/v1/tools/create", json=body)
        return tool_id

    def set_tool_valves(self, tool_id: str, valves: dict) -> None:
        self._request("POST", f"/api/v1/tools/id/{tool_id}/valves/update", json=valves)

    def resolve_collection_id(self, name: str) -> str | None:
        for c in self._request("GET", "/api/v1/knowledge/").json():
            if c.get("name") == name:
                return c["id"]
        return None

    def upsert_model(self, *, model_id: str, name: str, base_model: str, system_prompt: str,
                     collection_id: str | None, collection_name: str, tool_id: str,
                     public: bool = True) -> str:
        meta = {
            "description": "AI wiki documentation agent",
            "toolIds": [tool_id],
            "knowledge": [],
            "capabilities": {"builtin_tools": True, "file_context": True},
        }
        if collection_id:
            meta["knowledge"] = [
                {"id": collection_id, "name": collection_name, "type": "collection"}
            ]
        body = {
            "id": model_id,
            "base_model_id": base_model,
            "name": name,
            "meta": meta,
            # No params.function_calling: "native" disables knowledge auto-injection (Task 4 findings).
            "params": {"system": system_prompt},
            "access_grants": _public_grants() if public else [],
            "is_active": True,
        }
        if self._exists(f"/api/v1/models/model?id={model_id}"):
            self._request("POST", "/api/v1/models/model/update", json=body)
        else:
            self._request("POST", "/api/v1/models/create", json=body)
        return model_id

    @classmethod
    def from_config(cls, ow: OpenWebUIConfig) -> "OpenWebUIProvisioner":
        token = os.environ.get(ow.api_token_env, "")
        return cls(base_url=ow.base_url, token=token)


def provision_agent(ow: OpenWebUIConfig, agent: AgentConfig, *,
                    provisioner: OpenWebUIProvisioner | None = None) -> dict:
    p = provisioner or OpenWebUIProvisioner.from_config(ow)
    p.upsert_tool(
        agent.tool_id, agent.tool_name, doc_tool_source(),
        "Read-only jailed access to the AI wiki and sources", public=agent.public,
    )
    p.set_tool_valves(agent.tool_id, {
        "roots": ",".join(agent.doc_roots),
        "max_read_bytes": agent.max_read_bytes,
        "max_results": agent.max_results,
    })
    cid = p.resolve_collection_id(ow.collection)
    p.upsert_model(
        model_id=agent.model_id, name=agent.model_name, base_model=agent.base_model,
        system_prompt=agent_system_prompt(), collection_id=cid,
        collection_name=ow.collection, tool_id=agent.tool_id, public=agent.public,
    )
    return {"tool_id": agent.tool_id, "model_id": agent.model_id, "collection_id": cid}
