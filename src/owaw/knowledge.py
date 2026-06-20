"""OpenWebUI Knowledge client: protocol + HTTP implementation.

The protocol decouples the sync engine from OpenWebUI's API surface so the
engine is testable against a fake, and so the single highest-risk unknown
(the exact Knowledge endpoints) is isolated to one concrete class.
"""
from __future__ import annotations

import json
import os
import time
from typing import Protocol

import httpx


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


class OpenWebUIKnowledgeClient:
    """Knowledge client over OpenWebUI's REST API (single-call upload-with-metadata).

    add(): upload embed_text as a file named <hash>.md whose `file_metadata` carries
    {domain, page_id, kind, file_hash, knowledge_id}. With knowledge_id set, OpenWebUI
    auto-links the file to the collection and embeds it (bge-m3 via LiteLLM) server-side
    — so the spec metadata is stored and there is no premature-attach race. The hash is
    recovered from meta.file_hash in list_entries(), so a full reconcile needs no extra
    bookkeeping. Endpoints + the file_metadata field name are validated by the Task 7 spike.
    """

    def __init__(self, base_url: str, collection: str, token: str, model: str = "bge-m3",
                 *, http: httpx.Client | None = None, sleep=time.sleep, retries: int = 3):
        self._collection = collection
        self._model = model
        self._token = token
        self._sleep = sleep
        self._retries = retries
        self._cid: str | None = None
        self._http = http or httpx.Client(
            base_url=base_url, timeout=30.0,
        )

    # --- HTTP with bounded retry/backoff on transport errors + 5xx ---
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

    def _collection_id(self) -> str:
        if self._cid is not None:
            return self._cid
        existing = self._request("GET", "/api/v1/knowledge/").json()
        for c in existing:
            if c.get("name") == self._collection:
                self._cid = c["id"]
                return self._cid
        created = self._request(
            "POST", "/api/v1/knowledge/create",
            json={"name": self._collection, "description": "openwebui-ai-wiki chunks"},
        ).json()
        self._cid = created["id"]
        return self._cid

    def add(self, hash: str, text: str, meta: dict) -> str:
        cid = self._collection_id()
        files = {"file": (f"{hash}.md", text.encode("utf-8"), "text/markdown")}
        file_metadata = json.dumps({
            "domain": meta.get("domain"),
            "page_id": meta.get("page_id"),
            "kind": meta.get("kind"),
            "file_hash": hash,
            "knowledge_id": cid,
        })
        resp = self._request(
            "POST", "/api/v1/files/", files=files, data={"file_metadata": file_metadata}
        )
        return resp.json()["id"]

    def delete(self, entry_id: str) -> None:
        cid = self._collection_id()
        self._request("POST", f"/api/v1/knowledge/{cid}/file/remove", json={"file_id": entry_id})
        self._request("DELETE", f"/api/v1/files/{entry_id}")

    def list_entries(self) -> list[tuple[str, str]]:
        cid = self._collection_id()
        body = self._request("GET", f"/api/v1/knowledge/{cid}").json()
        out: list[tuple[str, str]] = []
        for f in body.get("files", []):
            m = f.get("meta") or {}
            h = m.get("file_hash")
            if not h:
                name = f.get("filename") or m.get("name", "")
                h = name[:-3] if name.endswith(".md") else name
            if h:
                out.append((f["id"], h))
        return out

    @classmethod
    def from_config(cls, ow, model: str) -> "OpenWebUIKnowledgeClient":
        token = os.environ.get(ow.api_token_env, "")
        return cls(base_url=ow.base_url, collection=ow.collection, token=token, model=model)
