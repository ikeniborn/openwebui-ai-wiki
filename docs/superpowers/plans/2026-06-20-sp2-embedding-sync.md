---
review:
  plan_hash: d5e80bea25cf6ec3
  spec_hash: d32bd6eb200103a4
  last_run: 2026-06-20
  phases:
    structure:     { status: passed }
    coverage:      { status: passed }
    dependencies:  { status: passed }
    verifiability: { status: passed }
    consistency:   { status: passed }
  findings:
    - id: F-001
      phase: coverage
      severity: CRITICAL
      section: "Task 8: OpenWebUI knowledge client (httpx)"
      section_hash: 0cdc4d2d951f660d
      text: >-
        Spec §2 requires each entry to carry metadata {domain, page_id, kind} and §7
        requires an integration test that metadata round-trips. OpenWebUIKnowledgeClient.add
        accepts meta but discards it: neither the POST /api/v1/files/ upload nor the
        /knowledge/{cid}/file/add attach transmits meta, and Task 10's integration test
        asserts only the filename, never metadata survival. Only the in-memory fake records
        meta, so the §2 metadata requirement is effectively unimplemented and untested e2e.
        The self-review's "metadata (Tasks 5/8/10)" coverage claim does not hold for the real
        client. (Spec §8 open-question #1 already flags metadata echo as unvalidated; Task 7
        spike must determine the transport, and Task 8 + Task 10 must then send and assert it.)
      resolution: >-
        Resolved by the edited plan. Task 8 add() now builds file_metadata =
        {domain, page_id, kind, file_hash, knowledge_id} and sends it via
        data={"file_metadata": ...} on POST /api/v1/files/ (single-call auto-link);
        the design contract bullet states the same transport. Task 8's unit test
        test_add_single_call_uploads_with_metadata_and_knowledge_id parses the multipart
        body and asserts the exact metadata dict is sent. Task 10's integration test
        test_add_then_delete_converges_with_metadata_roundtrip drives the real client
        through FakeOpenWebUI, which stores file_metadata and echoes it in the collection
        GET, and asserts domain/page_id/kind/file_hash round-trip end to end. Task 7 spike
        pins the file_metadata field name and meta-echo location. The §2 metadata
        requirement is now implemented and tested e2e; the self-review claim now holds.
      verdict: fixed
      verdict_at: 2026-06-20
  chain:
    intent: null
    spec: docs/superpowers/specs/2026-06-20-sp2-embedding-sync-design.md
---

# SP2 — Embedding + Sync — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep one OpenWebUI Knowledge collection ("ai-wiki") in continuous sync with SP1's on-disk chunk records (`chunks/*.jsonl`) — add new chunks, delete removed ones — so RAG over the wiki is current within seconds of an SP1 ingest.

**Architecture:** A Python sync sidecar added to the existing `owaw` package. A pure core (read all chunk records → desired set keyed by content `hash`; diff vs a persisted `state/sync_<collection>.json` hash→entry-id map) drives a `KnowledgeClient` that adds/deletes entries in OpenWebUI. The concrete client uploads each chunk's `embed_text` as a file named `<hash>.md`, carrying its metadata `{domain, page_id, kind, file_hash, knowledge_id}` in the upload's `file_metadata` field so OpenWebUI auto-links it to the collection and embeds it with bge-m3 via LiteLLM. An inotify watcher (reusing SP1's `Debouncer`) triggers a sync on `chunks/` change; a full reconcile (list collection → converge to desired) runs on start.

**Tech Stack:** Python 3.12, `httpx` (OpenWebUI REST + `httpx.MockTransport` for offline tests), Typer (CLI), PyYAML (config), watchdog (inotify, already a dep), pytest + monkeypatch. Same `pyproject.toml` (hatchling) and flat-module layout as SP1.

**Spec:** [`../specs/2026-06-20-sp2-embedding-sync-design.md`](../specs/2026-06-20-sp2-embedding-sync-design.md)

**Depends on (SP1, already merged):** `src/owaw/chunkstore.py` (record shape `{page_id, domain, kind, embed_text, hash}`), `src/owaw/config.py`, `src/owaw/paths.py`, `src/owaw/daemon.py` (`Debouncer`), `src/owaw/manifest.py` (state-file pattern to mirror).

---

## Design contract (types used across tasks)

Keep these signatures identical everywhere they appear:

- `OpenWebUIConfig(base_url: str, collection: str, api_token_env: str = "OWAW_OPENWEBUI_TOKEN")` — frozen.
- `EmbeddingConfig(model: str = "bge-m3")` — frozen.
- `SyncConfig(debounce_ms: int = 1500)` — frozen.
- `Config` gains: `openwebui: OpenWebUIConfig | None = None`, `embedding: EmbeddingConfig = EmbeddingConfig()`, `sync: SyncConfig = SyncConfig()`.
- `paths.chunks_dir() -> Path` and `paths.sync_state_path(collection: str) -> Path`.
- `SyncState` (mirrors `Manifest`): `load(path) -> SyncState`, `synced_hashes() -> set[str]`, `entry_id(h: str) -> str | None`, `mark(h: str, entry_id: str) -> None`, `forget(h: str) -> None`, `replace(mapping: dict[str, str]) -> None`, `save() -> None`. Internal store: `dict[str, str]` (hash → entry_id).
- `DesiredEntry(hash: str, embed_text: str, domain: str, page_id: str, kind: str)` — frozen.
- `build_desired(chunks_dir: Path) -> dict[str, DesiredEntry]` (keyed by hash; dedups identical hashes across domains).
- `diff(desired_hashes: set[str], synced_hashes: set[str]) -> tuple[set[str], set[str]]` → `(to_add, to_delete)`.
- `KnowledgeClient` Protocol: `add(self, hash: str, text: str, meta: dict) -> str` (returns entry id), `delete(self, entry_id: str) -> None`, `list_entries(self) -> list[tuple[str, str]]` (returns `(entry_id, hash)` pairs).
- `SyncResult(added: int, deleted: int, unchanged: int)` — frozen.
- `SyncEngine(client: KnowledgeClient, state: SyncState, chunks_dir: Path)`: `sync() -> SyncResult`, `reconcile() -> SyncResult`.
- `OpenWebUIKnowledgeClient(base_url, collection, token, model="bge-m3", *, http=None, sleep=time.sleep, retries=3)` — implements `KnowledgeClient`. **Transmits `meta` to OpenWebUI** as a `file_metadata` JSON form field on the `/api/v1/files/` upload (carrying `{domain, page_id, kind, file_hash, knowledge_id}`); this single-call path also auto-links the file to the collection server-side (OpenWebUI ≥ 0.9.6), satisfying the spec §2 metadata requirement and avoiding the "extracted content not available" race of a premature separate `file/add`. `list_entries` recovers the hash from `meta.file_hash` (fallback: filename stem).
- `daemon.watch_paths(paths: list[str], debounce_ms: int, on_change) -> Observer`.

---

## File structure

| File | Status | Responsibility |
|---|---|---|
| `pyproject.toml` | modify | Add `httpx>=0.27` dependency |
| `src/owaw/paths.py` | modify | Add `chunks_dir()`, `sync_state_path(collection)` |
| `src/owaw/config.py` | modify | Add `OpenWebUIConfig`/`EmbeddingConfig`/`SyncConfig`; extend `Config` + `load_config` |
| `src/owaw/syncstate.py` | create | `SyncState` — `state/sync_<collection>.json` hash→entry-id map |
| `src/owaw/sync.py` | create | `DesiredEntry`, `build_desired`, `diff`, `SyncResult`, `SyncEngine` |
| `src/owaw/knowledge.py` | create | `KnowledgeClient` Protocol + `OpenWebUIKnowledgeClient` (httpx) |
| `src/owaw/daemon.py` | modify | Add generic `watch_paths(paths, debounce_ms, on_change)` |
| `src/owaw/cli.py` | modify | Add `sync` (one-shot) and `sync-watch` (daemon) commands |
| `tests/fakes.py` | create | `FakeKnowledgeClient` reused by engine tests |
| `tests/test_config.py` | modify | Cover new config sections |
| `tests/test_paths.py` | modify | Cover new path helpers |
| `tests/test_syncstate.py` | create | `SyncState` round-trip / mutate |
| `tests/test_sync.py` | create | `build_desired` + `diff` (pure) |
| `tests/test_sync_engine.py` | create | `SyncEngine` add/delete/idempotency/partial-failure/reconcile |
| `tests/test_knowledge.py` | create | `OpenWebUIKnowledgeClient` over `httpx.MockTransport` |
| `tests/test_sync_cli.py` | create | CLI `sync` wiring (Typer `CliRunner`) |
| `docs/deploy/config.sample.yaml` | modify | Add `openwebui` / `embedding` / `sync` sections |
| `docs/deploy/docker-compose.snippet.yml` | modify | Add `owaw-sync` sidecar service |
| `docs/superpowers/specs/2026-06-20-sp2-knowledge-api-findings.md` | create | Spike output: validated OpenWebUI API surface |

---

## Task 1: Dependency + config + paths scaffold

**Files:**
- Modify: `pyproject.toml:10-16`
- Modify: `src/owaw/paths.py`
- Modify: `src/owaw/config.py`
- Modify: `tests/test_paths.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write the failing path test**

Append to `tests/test_paths.py`:

```python
def test_chunks_dir_and_sync_state_path(monkeypatch, tmp_path):
    monkeypatch.setenv("OWAW_DATA_DIR", str(tmp_path))
    from owaw import paths
    assert paths.chunks_dir() == tmp_path / "chunks"
    assert paths.sync_state_path("ai-wiki") == tmp_path / "state" / "sync_ai-wiki.json"
```

- [ ] **Step 2: Write the failing config tests**

Append to `tests/test_config.py`:

```python
def test_load_config_parses_openwebui_embedding_sync(tmp_path):
    (tmp_path / "config.yaml").write_text(
        "generation:\n  model: m\n  base_url: u\n"
        "openwebui:\n"
        "  base_url: http://owui:8080\n"
        "  collection: ai-wiki\n"
        "  api_token_env: OWAW_OPENWEBUI_TOKEN\n"
        "embedding:\n  model: bge-m3\n"
        "sync:\n  debounce_ms: 2000\n",
        encoding="utf-8",
    )
    cfg = load_config(tmp_path / "config.yaml")
    assert cfg.openwebui.base_url == "http://owui:8080"
    assert cfg.openwebui.collection == "ai-wiki"
    assert cfg.openwebui.api_token_env == "OWAW_OPENWEBUI_TOKEN"
    assert cfg.embedding.model == "bge-m3"
    assert cfg.sync.debounce_ms == 2000


def test_load_config_sp2_sections_optional_with_defaults(tmp_path):
    (tmp_path / "config.yaml").write_text(
        "generation:\n  model: m\n  base_url: u\n", encoding="utf-8"
    )
    cfg = load_config(tmp_path / "config.yaml")
    assert cfg.openwebui is None
    assert cfg.embedding.model == "bge-m3"
    assert cfg.sync.debounce_ms == 1500
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest tests/test_paths.py::test_chunks_dir_and_sync_state_path tests/test_config.py -v`
Expected: FAIL — `AttributeError: module 'owaw.paths' has no attribute 'chunks_dir'` and `AttributeError: 'Config' object has no attribute 'openwebui'`.

- [ ] **Step 4: Add the path helpers**

Append to `src/owaw/paths.py`:

```python
def chunks_dir() -> Path:
    return data_dir() / "chunks"


def sync_state_path(collection: str) -> Path:
    return data_dir() / "state" / f"sync_{collection}.json"
```

- [ ] **Step 5: Extend `config.py`**

In `src/owaw/config.py`, add these dataclasses after `GenerationConfig` (before `Config`):

```python
@dataclass(frozen=True)
class OpenWebUIConfig:
    base_url: str
    collection: str
    api_token_env: str = "OWAW_OPENWEBUI_TOKEN"


@dataclass(frozen=True)
class EmbeddingConfig:
    model: str = "bge-m3"


@dataclass(frozen=True)
class SyncConfig:
    debounce_ms: int = 1500
```

Replace the `Config` dataclass with:

```python
@dataclass(frozen=True)
class Config:
    generation: GenerationConfig
    chunking: ChunkingConfig
    extraction_engine: str
    debounce_ms: int
    openwebui: OpenWebUIConfig | None = None
    embedding: EmbeddingConfig = EmbeddingConfig()
    sync: SyncConfig = SyncConfig()
```

In `load_config`, before the final `return`, add:

```python
    ow_raw = raw.get("openwebui")
    openwebui = None
    if ow_raw:
        openwebui = OpenWebUIConfig(
            base_url=ow_raw["base_url"],
            collection=ow_raw["collection"],
            api_token_env=ow_raw.get("api_token_env", "OWAW_OPENWEBUI_TOKEN"),
        )
    embedding = EmbeddingConfig(model=(raw.get("embedding") or {}).get("model", "bge-m3"))
    sync = SyncConfig(debounce_ms=(raw.get("sync") or {}).get("debounce_ms", 1500))
```

And replace the final `return Config(...)` with:

```python
    return Config(
        generation=generation,
        chunking=chunking,
        extraction_engine=extraction_engine,
        debounce_ms=debounce_ms,
        openwebui=openwebui,
        embedding=embedding,
        sync=sync,
    )
```

- [ ] **Step 6: Add the `httpx` dependency**

In `pyproject.toml`, add `"httpx>=0.27",` to the `dependencies` list (after `"watchdog>=4.0",`).

- [ ] **Step 7: Reinstall and run the full suite**

Run:
```bash
cd /home/ikeniborn/Documents/Project/openwebui-ai-wiki
. .venv/bin/activate
pip install -e ".[dev]"
pytest tests/test_paths.py tests/test_config.py -v
```
Expected: PASS, including the two new config tests and the new path test. The pre-existing `test_load_config_applies_defaults` still passes (new fields are optional).

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml src/owaw/paths.py src/owaw/config.py tests/test_paths.py tests/test_config.py
git commit -m "feat(sp2): config (openwebui/embedding/sync), path helpers, httpx dep"
```

---

## Task 2: Sync state (`state/sync_<collection>.json`)

**Files:**
- Create: `src/owaw/syncstate.py`
- Test: `tests/test_syncstate.py`

- [ ] **Step 1: Write the failing test**

`tests/test_syncstate.py`:

```python
from owaw.syncstate import SyncState


def test_mark_forget_and_query(tmp_path):
    st = SyncState.load(tmp_path / "sync_ai-wiki.json")
    assert st.synced_hashes() == set()
    st.mark("h1", "e1")
    st.mark("h2", "e2")
    assert st.synced_hashes() == {"h1", "h2"}
    assert st.entry_id("h1") == "e1"
    assert st.entry_id("missing") is None
    st.forget("h1")
    assert st.synced_hashes() == {"h2"}


def test_save_and_reload_roundtrip(tmp_path):
    p = tmp_path / "sync_ai-wiki.json"
    st = SyncState.load(p)
    st.mark("h1", "e1")
    st.save()
    again = SyncState.load(p)
    assert again.entry_id("h1") == "e1"


def test_replace_swaps_whole_map(tmp_path):
    st = SyncState.load(tmp_path / "sync_ai-wiki.json")
    st.mark("old", "eold")
    st.replace({"a": "ea", "b": "eb"})
    assert st.synced_hashes() == {"a", "b"}
    assert st.entry_id("old") is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_syncstate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'owaw.syncstate'`.

- [ ] **Step 3: Write the implementation**

`src/owaw/syncstate.py`:

```python
"""Persisted sync state: maps each pushed chunk hash to its OpenWebUI entry id.

Mirrors manifest.py. Stored at state/sync_<collection>.json so diffs are O(changed).
"""
from __future__ import annotations

import json
from pathlib import Path


class SyncState:
    def __init__(self, path: Path, entries: dict[str, str]):
        self._path = path
        self._entries = entries

    @classmethod
    def load(cls, path: Path) -> "SyncState":
        entries: dict[str, str] = {}
        if path.exists():
            entries = json.loads(path.read_text(encoding="utf-8"))
        return cls(path, entries)

    def synced_hashes(self) -> set[str]:
        return set(self._entries)

    def entry_id(self, h: str) -> str | None:
        return self._entries.get(h)

    def mark(self, h: str, entry_id: str) -> None:
        self._entries[h] = entry_id

    def forget(self, h: str) -> None:
        self._entries.pop(h, None)

    def replace(self, mapping: dict[str, str]) -> None:
        self._entries = dict(mapping)

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._entries, indent=2), encoding="utf-8")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_syncstate.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/owaw/syncstate.py tests/test_syncstate.py
git commit -m "feat(sp2): SyncState hash->entry-id persistence"
```

---

## Task 3: Desired set + diff (pure core)

**Files:**
- Create: `src/owaw/sync.py` (this task adds `DesiredEntry`, `build_desired`, `diff`; `SyncEngine` comes in Task 5)
- Test: `tests/test_sync.py`

- [ ] **Step 1: Write the failing test**

`tests/test_sync.py`:

```python
import json

from owaw.sync import DesiredEntry, build_desired, diff


def _write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
        encoding="utf-8",
    )


def test_build_desired_reads_all_domains_keyed_by_hash(tmp_path):
    cd = tmp_path / "chunks"
    _write_jsonl(cd / "infra.jsonl", [
        {"page_id": "p1", "domain": "infra", "kind": "summary", "embed_text": "s", "hash": "h1"},
        {"page_id": "p1", "domain": "infra", "kind": "section", "embed_text": "a", "hash": "h2"},
    ])
    _write_jsonl(cd / "apps.jsonl", [
        {"page_id": "p2", "domain": "apps", "kind": "summary", "embed_text": "t", "hash": "h3"},
    ])
    desired = build_desired(cd)
    assert set(desired) == {"h1", "h2", "h3"}
    assert desired["h2"] == DesiredEntry(
        hash="h2", embed_text="a", domain="infra", page_id="p1", kind="section"
    )


def test_build_desired_dedups_identical_hash_across_domains(tmp_path):
    cd = tmp_path / "chunks"
    rec = {"page_id": "p", "domain": "infra", "kind": "summary", "embed_text": "x", "hash": "dup"}
    _write_jsonl(cd / "infra.jsonl", [rec])
    _write_jsonl(cd / "apps.jsonl", [{**rec, "domain": "apps", "page_id": "q"}])
    desired = build_desired(cd)
    assert set(desired) == {"dup"}


def test_build_desired_missing_dir_is_empty(tmp_path):
    assert build_desired(tmp_path / "nope") == {}


def test_diff_add_delete_and_noop():
    desired = {"h1", "h2", "h3"}
    synced = {"h2", "h3", "old"}
    to_add, to_delete = diff(desired, synced)
    assert to_add == {"h1"}
    assert to_delete == {"old"}


def test_diff_identical_sets_is_empty():
    s = {"a", "b"}
    assert diff(s, set(s)) == (set(), set())
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_sync.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'owaw.sync'`.

- [ ] **Step 3: Write the implementation**

`src/owaw/sync.py`:

```python
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_sync.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/owaw/sync.py tests/test_sync.py
git commit -m "feat(sp2): desired-set reader + diff (pure core)"
```

---

## Task 4: Knowledge client Protocol + fake

**Files:**
- Create: `src/owaw/knowledge.py` (this task adds only the `KnowledgeClient` Protocol; the HTTP client comes in Task 7)
- Create: `tests/fakes.py`
- Create: `tests/__init__.py`
- Test: `tests/test_knowledge_protocol.py`

- [ ] **Step 1: Write the failing test**

`tests/test_knowledge_protocol.py`:

```python
import pytest

from owaw.knowledge import KnowledgeClient
from tests.fakes import FakeKnowledgeClient


def test_fake_satisfies_protocol_add_list_delete():
    client: KnowledgeClient = FakeKnowledgeClient()
    eid = client.add("h1", "text one", {"domain": "infra", "page_id": "p", "kind": "summary"})
    assert client.list_entries() == [(eid, "h1")]
    client.delete(eid)
    assert client.list_entries() == []


def test_fake_records_metadata_for_roundtrip():
    client = FakeKnowledgeClient()
    eid = client.add("h1", "t", {"domain": "infra", "page_id": "p", "kind": "section"})
    assert client.entries[eid]["meta"]["domain"] == "infra"
    assert client.entries[eid]["text"] == "t"


def test_fake_can_simulate_add_failure():
    client = FakeKnowledgeClient(fail_on={"bad"})
    with pytest.raises(RuntimeError):
        client.add("bad", "t", {})
    assert client.add_calls == 0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_knowledge_protocol.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'owaw.knowledge'`.

- [ ] **Step 3: Write the Protocol**

`src/owaw/knowledge.py`:

```python
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
```

- [ ] **Step 4: Write the fake client**

`tests/fakes.py`:

```python
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
```

- [ ] **Step 5: Make `tests` importable as a package**

Create empty file `tests/__init__.py` (so `from tests.fakes import ...` resolves):

```python
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `pytest tests/test_knowledge_protocol.py -v`
Expected: PASS (3 tests). Then run `pytest -q` to confirm the new `tests/__init__.py` did not break collection of existing tests.

- [ ] **Step 7: Commit**

```bash
git add src/owaw/knowledge.py tests/fakes.py tests/__init__.py tests/test_knowledge_protocol.py
git commit -m "feat(sp2): KnowledgeClient protocol + in-memory fake"
```

---

## Task 5: Sync engine (`sync()`)

**Files:**
- Modify: `src/owaw/sync.py` (add `SyncResult` + `SyncEngine.sync`)
- Test: `tests/test_sync_engine.py`

- [ ] **Step 1: Write the failing test**

`tests/test_sync_engine.py`:

```python
import json

from owaw.sync import SyncEngine
from owaw.syncstate import SyncState
from tests.fakes import FakeKnowledgeClient


def _write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
        encoding="utf-8",
    )


def _rec(h, embed="x", domain="infra", page="p", kind="section"):
    return {"page_id": page, "domain": domain, "kind": kind, "embed_text": embed, "hash": h}


def _engine(tmp_path, client):
    state = SyncState.load(tmp_path / "state" / "sync_ai-wiki.json")
    return SyncEngine(client, state, tmp_path / "chunks")


def test_sync_adds_new_chunks_and_records_state(tmp_path):
    _write_jsonl(tmp_path / "chunks" / "infra.jsonl", [_rec("h1"), _rec("h2")])
    client = FakeKnowledgeClient()
    eng = _engine(tmp_path, client)
    res = eng.sync()
    assert (res.added, res.deleted) == (2, 0)
    assert {h for _, h in client.list_entries()} == {"h1", "h2"}


def test_sync_passes_metadata_to_client(tmp_path):
    _write_jsonl(tmp_path / "chunks" / "infra.jsonl",
                 [_rec("h1", domain="infra", page="p1", kind="summary")])
    client = FakeKnowledgeClient()
    _engine(tmp_path, client).sync()
    (eid,) = client.entries
    assert client.entries[eid]["meta"] == {"domain": "infra", "page_id": "p1", "kind": "summary"}


def test_sync_deletes_chunks_removed_from_jsonl(tmp_path):
    chunks = tmp_path / "chunks" / "infra.jsonl"
    _write_jsonl(chunks, [_rec("h1"), _rec("h2")])
    client = FakeKnowledgeClient()
    SyncEngine(client, SyncState.load(tmp_path / "state" / "sync_ai-wiki.json"),
               tmp_path / "chunks").sync()
    # h2 removed from source
    _write_jsonl(chunks, [_rec("h1")])
    res = SyncEngine(client, SyncState.load(tmp_path / "state" / "sync_ai-wiki.json"),
                     tmp_path / "chunks").sync()
    assert (res.added, res.deleted) == (0, 1)
    assert {h for _, h in client.list_entries()} == {"h1"}


def test_sync_is_idempotent_no_api_calls_second_run(tmp_path):
    _write_jsonl(tmp_path / "chunks" / "infra.jsonl", [_rec("h1"), _rec("h2")])
    client = FakeKnowledgeClient()
    statepath = tmp_path / "state" / "sync_ai-wiki.json"
    SyncEngine(client, SyncState.load(statepath), tmp_path / "chunks").sync()
    calls_after_first = (client.add_calls, client.delete_calls)
    res = SyncEngine(client, SyncState.load(statepath), tmp_path / "chunks").sync()
    assert (client.add_calls, client.delete_calls) == calls_after_first  # zero new calls
    assert (res.added, res.deleted) == (0, 0)


def test_sync_partial_failure_keeps_unfailed_in_state(tmp_path):
    _write_jsonl(tmp_path / "chunks" / "infra.jsonl", [_rec("good"), _rec("bad")])
    client = FakeKnowledgeClient(fail_on={"bad"})
    statepath = tmp_path / "state" / "sync_ai-wiki.json"
    res = SyncEngine(client, SyncState.load(statepath), tmp_path / "chunks").sync()
    assert res.added == 1
    assert SyncState.load(statepath).synced_hashes() == {"good"}  # only confirmed call persisted
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_sync_engine.py -v`
Expected: FAIL with `ImportError: cannot import name 'SyncEngine' from 'owaw.sync'`.

- [ ] **Step 3: Extend `sync.py`**

Add at the top of `src/owaw/sync.py` (with the existing imports):

```python
import logging

logger = logging.getLogger(__name__)
```

Append to `src/owaw/sync.py`:

```python
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_sync_engine.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/owaw/sync.py tests/test_sync_engine.py
git commit -m "feat(sp2): SyncEngine.sync (add/delete, idempotent, per-entry resilient)"
```

---

## Task 6: Sync engine reconcile (`reconcile()`)

**Files:**
- Modify: `src/owaw/sync.py` (add `SyncEngine.reconcile`)
- Test: `tests/test_sync_engine.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_sync_engine.py`:

```python
def test_reconcile_rebuilds_state_from_collection_then_converges(tmp_path):
    # Collection already has h1 (entry e-existing) but local state file is empty/stale.
    _write_jsonl(tmp_path / "chunks" / "infra.jsonl", [_rec("h1"), _rec("h2")])
    client = FakeKnowledgeClient()
    client.add("h1", "x", {})            # pre-existing collection entry, not in our state
    statepath = tmp_path / "state" / "sync_ai-wiki.json"
    eng = SyncEngine(client, SyncState.load(statepath), tmp_path / "chunks")
    res = eng.reconcile()
    # h1 already present -> not re-added; h2 added; nothing deleted.
    assert (res.added, res.deleted) == (1, 0)
    assert {h for _, h in client.list_entries()} == {"h1", "h2"}


def test_reconcile_deletes_orphan_entries_not_in_desired(tmp_path):
    _write_jsonl(tmp_path / "chunks" / "infra.jsonl", [_rec("h1")])
    client = FakeKnowledgeClient()
    client.add("h1", "x", {})
    client.add("orphan", "y", {})        # in collection, no longer in any JSONL
    statepath = tmp_path / "state" / "sync_ai-wiki.json"
    res = SyncEngine(client, SyncState.load(statepath), tmp_path / "chunks").reconcile()
    assert (res.added, res.deleted) == (0, 1)
    assert {h for _, h in client.list_entries()} == {"h1"}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_sync_engine.py -k reconcile -v`
Expected: FAIL with `AttributeError: 'SyncEngine' object has no attribute 'reconcile'`.

- [ ] **Step 3: Add `reconcile` to `SyncEngine`**

Append this method inside the `SyncEngine` class in `src/owaw/sync.py`:

```python
    def reconcile(self) -> "SyncResult":
        """Full reconcile: trust the live collection as state, then converge to desired.

        Rebuilds sync-state from the collection listing (handles stale state and
        orphan entries), persists it, then runs an ordinary sync().
        """
        present = self._client.list_entries()
        self._state.replace({h: eid for eid, h in present})
        self._state.save()
        return self.sync()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_sync_engine.py -v`
Expected: PASS (7 tests total in the file).

- [ ] **Step 5: Commit**

```bash
git add src/owaw/sync.py tests/test_sync_engine.py
git commit -m "feat(sp2): SyncEngine.reconcile (rebuild state from collection, converge)"
```

---

## Task 7: Spike — validate OpenWebUI Knowledge API surface

> The spec's single highest-risk unknown (open question #1). The engine is already
> done and decoupled behind `KnowledgeClient`; this spike pins the concrete endpoints
> before Task 8 implements them. **This is a research task — no TDD.**

**Files:**
- Create: `docs/superpowers/specs/2026-06-20-sp2-knowledge-api-findings.md`

- [ ] **Step 1: Confirm the deployed OpenWebUI version**

Run (replace host/token with the deployment's values):
```bash
export OWUI=http://localhost:8080
export TOK=<openwebui-api-token>
curl -s "$OWUI/api/config" | python3 -m json.tool | grep -i version || true
```
Record the version in the findings doc.

- [ ] **Step 2: Probe the Knowledge + Files endpoints**

Run each and capture the JSON shape (status + body). The **primary** path is the single-call
upload-with-metadata (OpenWebUI ≥ 0.9.6: the server auto-links and processes the file into the
collection, and stores `file_metadata`); the **fallback** is a separate `file/add` attach.
```bash
# list collections
curl -s -H "Authorization: Bearer $TOK" "$OWUI/api/v1/knowledge/" | python3 -m json.tool
# create a throwaway collection (capture its id as COLLECTION_ID)
curl -s -X POST -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{"name":"sp2-spike","description":"spike"}' "$OWUI/api/v1/knowledge/create" | python3 -m json.tool
# PRIMARY: single-call upload with file_metadata (domain/page_id/kind + file_hash + knowledge_id)
printf 'hello world' > /tmp/spike.md
curl -s -X POST -H "Authorization: Bearer $TOK" \
  -F "file=@/tmp/spike.md;type=text/markdown" \
  -F 'file_metadata={"domain":"infra","page_id":"p","kind":"section","file_hash":"deadbeef","knowledge_id":"<COLLECTION_ID>"};type=application/json' \
  "$OWUI/api/v1/files/" | python3 -m json.tool        # note returned id as FILE_ID; confirm meta echoed
# extraction/embedding is async — poll until processed before relying on retrieval
curl -s -H "Authorization: Bearer $TOK" "$OWUI/api/v1/files/<FILE_ID>/process/status" | python3 -m json.tool
# read collection back: is FILE_ID linked? does each file's meta carry file_hash + domain/page_id/kind?
curl -s -H "Authorization: Bearer $TOK" "$OWUI/api/v1/knowledge/<COLLECTION_ID>" | python3 -m json.tool
# FALLBACK (only if single-call did NOT auto-link): explicit attach
curl -s -X POST -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{"file_id":"<FILE_ID>"}' "$OWUI/api/v1/knowledge/<COLLECTION_ID>/file/add" | python3 -m json.tool
# remove + delete
curl -s -X POST -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{"file_id":"<FILE_ID>"}' "$OWUI/api/v1/knowledge/<COLLECTION_ID>/file/remove" | python3 -m json.tool
curl -s -X DELETE -H "Authorization: Bearer $TOK" "$OWUI/api/v1/files/<FILE_ID>" | python3 -m json.tool
```

- [ ] **Step 3: Write the findings doc**

`docs/superpowers/specs/2026-06-20-sp2-knowledge-api-findings.md` must record, with the captured request/response for each:
- OpenWebUI version (and whether it is ≥ 0.9.6, which enables the single-call upload-with-`knowledge_id` auto-link).
- Exact paths + methods for: list collections, create collection, upload file, read collection, remove file from collection, delete file, and the per-file **process/status** endpoint.
- **Metadata transport (the F-001 resolution — must confirm):** the exact form-field name for upload metadata (assumed `file_metadata` as a JSON string), whether `knowledge_id` in that metadata auto-links the file to the collection, whether `file_hash` is accepted, and **where the metadata is echoed back** in the collection listing (assumed `files[].meta`, with `meta.file_hash` and `meta.name`).
- The JSON keys for: collection id, file id, the per-file name and the per-file meta in the collection listing.
- Whether a separate `POST /knowledge/{cid}/file/add` is still required (fallback path) and whether it errors when called before processing completes.
- **Verdict:** either "single-call upload-with-metadata contract as assumed in Task 8 — proceed" OR "single-call unsupported → Task 8 uses the two-call fallback (upload-with-`file_metadata`, poll process/status, then `file/add`)" with the exact field/path deltas, OR (worst case) "API cannot accept pre-chunked text → use the fallback in spec §8 (compute bge-m3 vectors via LiteLLM, write the vector store directly)". In every case the metadata field name and meta-echo location MUST be pinned, because Task 8/Task 10 send and assert them.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-06-20-sp2-knowledge-api-findings.md
git commit -m "docs(sp2): OpenWebUI Knowledge API spike findings"
```

---

## Task 8: OpenWebUI knowledge client (httpx)

> Implement `OpenWebUIKnowledgeClient` against the contract validated in Task 7.
> If the findings doc lists deltas, apply them to the paths/payloads below — the
> tests assert the **assumed** contract, so adjust both together.

**Files:**
- Modify: `src/owaw/knowledge.py` (add `OpenWebUIKnowledgeClient`)
- Test: `tests/test_knowledge.py`

- [ ] **Step 1: Write the failing test (happy path over MockTransport)**

`tests/test_knowledge.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_knowledge.py -v`
Expected: FAIL with `ImportError: cannot import name 'OpenWebUIKnowledgeClient' from 'owaw.knowledge'`.

- [ ] **Step 3: Implement the client**

Append to `src/owaw/knowledge.py` (add `import json`, `import os`, `import time`, `import httpx` at the top with the existing imports):

```python
import json
import os
import time

import httpx


class OpenWebUIKnowledgeClient:
    """Knowledge client over OpenWebUI's REST API (single-call upload-with-metadata).

    add(): upload embed_text as a file named <hash>.md whose `file_metadata` carries
    {domain, page_id, kind, file_hash, knowledge_id}. With knowledge_id set, OpenWebUI
    auto-links the file to the collection and embeds it (bge-m3 via LiteLLM) server-side
    — so the spec §2 metadata is stored and there is no premature-attach race. The hash
    is recovered from meta.file_hash in list_entries(), so a full reconcile needs no extra
    bookkeeping. The endpoints and the file_metadata field name are validated by the Task 7
    spike; if that version lacks single-call auto-link, add a follow-up
    POST /knowledge/{cid}/file/add (after polling /files/{id}/process/status) per the spike.
    """

    def __init__(self, base_url: str, collection: str, token: str, model: str = "bge-m3",
                 *, http: httpx.Client | None = None, sleep=time.sleep, retries: int = 3):
        self._collection = collection
        self._model = model
        self._sleep = sleep
        self._retries = retries
        self._cid: str | None = None
        self._http = http or httpx.Client(
            base_url=base_url, headers={"Authorization": f"Bearer {token}"}, timeout=30.0,
        )

    # --- HTTP with bounded retry/backoff on transport errors + 5xx ---
    def _request(self, method: str, path: str, **kw) -> httpx.Response:
        last: Exception | None = None
        for attempt in range(self._retries):
            try:
                resp = self._http.request(method, path, **kw)
                if resp.status_code >= 500:
                    raise httpx.HTTPStatusError("server error", request=resp.request, response=resp)
                resp.raise_for_status()
                return resp
            except (httpx.TransportError, httpx.HTTPStatusError) as e:
                last = e
                self._sleep(0.5 * (2 ** attempt))
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
                name = m.get("name", "")
                h = name[:-3] if name.endswith(".md") else name
            if h:
                out.append((f["id"], h))
        return out

    @classmethod
    def from_config(cls, ow, model: str) -> "OpenWebUIKnowledgeClient":
        token = os.environ.get(ow.api_token_env, "")
        return cls(base_url=ow.base_url, collection=ow.collection, token=token, model=model)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_knowledge.py -v`
Expected: PASS (5 tests). If the Task 7 findings listed deltas, the tests above and the client must reflect the corrected paths/payloads — they should still pass together.

- [ ] **Step 5: Commit**

```bash
git add src/owaw/knowledge.py tests/test_knowledge.py
git commit -m "feat(sp2): OpenWebUIKnowledgeClient (files+knowledge API, retry/backoff)"
```

---

## Task 9: Watcher + CLI commands

**Files:**
- Modify: `src/owaw/daemon.py` (add `watch_paths`)
- Modify: `src/owaw/cli.py` (add `sync`, `sync-watch`)
- Test: `tests/test_sync_cli.py`
- Test: `tests/test_daemon.py` (append)

- [ ] **Step 1: Write the failing CLI test**

`tests/test_sync_cli.py`:

```python
from typer.testing import CliRunner

import owaw.cli as cli_mod
from owaw.cli import app
from owaw.sync import SyncResult

runner = CliRunner()


def test_sync_command_runs_reconcile_and_prints_counts(monkeypatch, tmp_path):
    monkeypatch.setenv("OWAW_DATA_DIR", str(tmp_path))

    class FakeEngine:
        def reconcile(self):
            return SyncResult(added=3, deleted=1, unchanged=5)

    monkeypatch.setattr(cli_mod, "_sync_engine", lambda: FakeEngine())
    result = runner.invoke(app, ["sync"])
    assert result.exit_code == 0
    assert "+3" in result.stdout and "-1" in result.stdout and "=5" in result.stdout


def test_sync_command_errors_clearly_without_openwebui_config(monkeypatch, tmp_path):
    monkeypatch.setenv("OWAW_DATA_DIR", str(tmp_path))
    (tmp_path / "config.yaml").write_text(
        "generation:\n  model: m\n  base_url: u\n", encoding="utf-8"
    )
    result = runner.invoke(app, ["sync"])
    assert result.exit_code != 0
    assert "openwebui" in result.stdout.lower()
```

- [ ] **Step 2: Write the failing daemon test**

Append to `tests/test_daemon.py`:

```python
def test_watch_paths_is_callable_and_returns_observer(tmp_path):
    from owaw.daemon import watch_paths
    (tmp_path / "chunks").mkdir()
    obs = watch_paths([str(tmp_path / "chunks")], debounce_ms=10_000, on_change=lambda items: None)
    try:
        assert obs.is_alive()
    finally:
        obs.stop()
        obs.join()
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest tests/test_sync_cli.py tests/test_daemon.py::test_watch_paths_is_callable_and_returns_observer -v`
Expected: FAIL — `AttributeError: module 'owaw.cli' has no attribute '_sync_engine'` / no `sync` command; `ImportError: cannot import name 'watch_paths'`.

- [ ] **Step 4: Add `watch_paths` to `daemon.py`**

Append to `src/owaw/daemon.py`:

```python
def watch_paths(paths: list[str], debounce_ms: int, on_change: Callable[[set], None]) -> Observer:
    """Observe arbitrary directories (recursive). Returns a started Observer (caller stops/joins)."""
    debouncer = Debouncer(debounce_ms, on_change)
    observer = Observer()
    handler = _Handler(debouncer)
    for root in paths:
        observer.schedule(handler, root, recursive=True)
    observer.start()
    return observer
```

- [ ] **Step 5: Add the CLI commands**

In `src/owaw/cli.py`, add imports at the top (with the existing imports):

```python
from owaw.knowledge import OpenWebUIKnowledgeClient
from owaw.sync import SyncEngine
from owaw.syncstate import SyncState
```

Add this helper after `_llm()`:

```python
def _sync_engine() -> SyncEngine:
    cfg = load_config(paths.config_path())
    if cfg.openwebui is None:
        raise typer.BadParameter("no 'openwebui' section in config.yaml; required for sync")
    client = OpenWebUIKnowledgeClient.from_config(cfg.openwebui, model=cfg.embedding.model)
    state = SyncState.load(paths.sync_state_path(cfg.openwebui.collection))
    return SyncEngine(client, state, paths.chunks_dir())
```

Add these commands (after the `watch` command):

```python
@app.command()
def sync():
    """One-shot: full reconcile of the OpenWebUI collection against chunks/."""
    res = _sync_engine().reconcile()
    typer.echo(f"synced: +{res.added} -{res.deleted} ={res.unchanged}")


@app.command("sync-watch")
def sync_watch():
    """Daemon: reconcile on start, then sync on every chunks/ change (debounced)."""
    import time
    from owaw.daemon import watch_paths

    cfg = load_config(paths.config_path())
    engine = _sync_engine()
    res = engine.reconcile()
    typer.echo(f"[sync-watch] startup reconcile: +{res.added} -{res.deleted} ={res.unchanged}")

    cdir = paths.chunks_dir()
    cdir.mkdir(parents=True, exist_ok=True)

    def _on_change(_changed):
        r = engine.sync()
        typer.echo(f"[sync-watch] synced: +{r.added} -{r.deleted}")

    observer = watch_paths([str(cdir)], cfg.sync.debounce_ms, _on_change)
    typer.echo(f"[sync-watch] watching {cdir}; Ctrl-C to stop")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        observer.join()
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/test_sync_cli.py tests/test_daemon.py -v`
Expected: PASS. (The `sync` command test stubs `_sync_engine`; the config-missing test exercises the real guard.)

- [ ] **Step 7: Commit**

```bash
git add src/owaw/daemon.py src/owaw/cli.py tests/test_sync_cli.py tests/test_daemon.py
git commit -m "feat(sp2): owaw sync + sync-watch CLI, generic watch_paths"
```

---

## Task 10: End-to-end integration test

> Wire the real `OpenWebUIKnowledgeClient` (over `httpx.MockTransport` standing in for
> OpenWebUI) to the real `SyncEngine` + `SyncState` + chunk files: add, then delete,
> asserting the collection converges AND the chunk metadata `{domain, page_id, kind, file_hash}`
> round-trips through OpenWebUI (spec §2 + §7 — the F-001 resolution, verified end to end).

**Files:**
- Test: `tests/test_sync_integration.py`

- [ ] **Step 1: Write the integration test**

`tests/test_sync_integration.py`:

```python
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
            self.collection.discard(request.json()["file_id"])
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
    # metadata round-trips through OpenWebUI (spec §2 + §7)
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
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `pytest tests/test_sync_integration.py -v`
Expected: PASS. If it fails on the metadata assertion, `OpenWebUIKnowledgeClient.add` is not sending `file_metadata` (with `domain/page_id/kind/file_hash/knowledge_id`) on the `/api/v1/files/` upload — fix the `data={"file_metadata": ...}` payload in `knowledge.py` (Task 8 Step 3), then re-run.

- [ ] **Step 3: Run the entire suite**

Run: `pytest -q`
Expected: PASS — all SP1 tests plus every SP2 test added above.

- [ ] **Step 4: Commit**

```bash
git add tests/test_sync_integration.py
git commit -m "test(sp2): e2e add/delete convergence + metadata round-trip over mock OpenWebUI"
```

---

## Task 11: Deployment wiring

**Files:**
- Modify: `docs/deploy/config.sample.yaml`
- Modify: `docs/deploy/docker-compose.snippet.yml`

- [ ] **Step 1: Extend the sample config**

Append to `docs/deploy/config.sample.yaml`:

```yaml
openwebui:
  base_url: "http://minipc-traefik-openwebui:8080"   # internal, proxy-net; no public route
  collection: "ai-wiki"
  api_token_env: OWAW_OPENWEBUI_TOKEN                 # value injected from secrets, never committed
embedding:
  model: "bge-m3"                                     # OpenWebUI RAG engine must point at this (LiteLLM);
                                                      # bge-m3 is 1024-dim — changing it later forces a full re-index
sync:
  debounce_ms: 1500
```

- [ ] **Step 2: Add the sidecar service**

In `docs/deploy/docker-compose.snippet.yml`, add an `owaw-sync` service alongside `owaw` (same image, `command: ["sync-watch"]`):

```yaml
  owaw-sync:
    build: ../openwebui-ai-wiki        # same image as owaw
    container_name: minipc-traefik-owaw-sync
    restart: unless-stopped
    command: ["sync-watch"]            # reconcile on start, then inotify on chunks/
    env_file:
      - ./owaw.conf                    # adds OWAW_OPENWEBUI_TOKEN=... (chmod 600, not committed)
    volumes:
      - owaw_data:/data                # mounted rw: reads chunks/, writes only state/sync_*.json
    depends_on:
      - owaw
    networks:
      - proxy-net                      # reaches OpenWebUI internally; no Traefik router
```

> Note (resolves spec finding F-001): the volume is mounted **rw** because the sidecar
> writes `state/sync_<collection>.json`; `chunks/` is read-only by convention.

- [ ] **Step 3: Verify the compose snippet parses**

Run:
```bash
cd /home/ikeniborn/Documents/Project/openwebui-ai-wiki
python3 -c "import yaml; yaml.safe_load(open('docs/deploy/docker-compose.snippet.yml')); yaml.safe_load(open('docs/deploy/config.sample.yaml')); print('ok')"
```
Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add docs/deploy/config.sample.yaml docs/deploy/docker-compose.snippet.yml
git commit -m "docs(sp2): sample config + owaw-sync sidecar compose service"
```

---

## Task 12: Update the docs/wiki knowledge base (MANDATORY)

> Per the project's "Keep Docs Current" rule: regenerate the affected `docs/wiki/`
> pages via iwiki, then lint. SP2 introduces a new subsystem page and touches
> config/deployment/cli pages.

**Files:**
- Update (via iwiki): `docs/wiki/*` (new embedding-sync page + cross-links)

- [ ] **Step 1: Ingest the new SP2 sources**

Invoke the `iwiki:iwiki-ingest` skill on the SP2 modules:
`src/owaw/sync.py`, `src/owaw/syncstate.py`, `src/owaw/knowledge.py`, and the modified `src/owaw/config.py`, `src/owaw/cli.py`, `src/owaw/daemon.py`, `docs/deploy/*`.

This should produce/update a wiki page (e.g. `docs/wiki/embedding-and-sync.md`) describing: the desired-set/diff core, `SyncState`, the `KnowledgeClient` + `OpenWebUIKnowledgeClient`, reconcile, the `sync`/`sync-watch` CLI, and the sidecar deployment — with `[[refs]]` to `chunking-and-storage`, `domain-model`, `deployment`, and `cli-and-daemon`.

- [ ] **Step 2: Lint the wiki graph**

Invoke the `/iwiki-lint` skill.
Expected: no broken `[[refs]]`, no orphan or stale pages. Fix any issues it reports.

- [ ] **Step 3: Commit**

```bash
git add docs/wiki
git commit -m "docs(wiki): document SP2 embedding+sync subsystem (iwiki-ingest)"
```

---

## Self-review notes (verification of this plan against the spec)

- **bge-m3 enablement (spec §2 in-scope):** `EmbeddingConfig.model` (Task 1) + `config.sample.yaml` (Task 11) + the embedding model carried into `OpenWebUIKnowledgeClient` (Task 8). The actual OpenWebUI RAG-engine setting (point it at LiteLLM `bge-m3`) is an operator action documented in the sample-config comment — there is no API task for it because it is OpenWebUI admin UI configuration, called out explicitly here so it is not forgotten.
- **Sync service / one-entry-per-chunk / hash identity / metadata (spec §2):** Tasks 3–8. **Metadata** `{domain, page_id, kind}` (+`file_hash`) is transmitted via the `file_metadata` upload field in Task 8, asserted in Task 8's client unit test, and verified to round-trip end to end in Task 10 — this is the resolution of check-plan finding **F-001** (the earlier draft accepted `meta` but dropped it).
- **Autosync inotify + debounce + reconcile-on-start (spec §2, §4):** Task 9 (`sync-watch`).
- **Deletion handling (spec §2):** Task 5 (delete branch) + Task 6 (reconcile orphan delete).
- **Idempotency (spec §2):** Task 5 (`test_sync_is_idempotent_no_api_calls_second_run`).
- **Auth token (spec §2, §5):** `OWAW_OPENWEBUI_TOKEN` via `api_token_env` (Tasks 1, 8, 11).
- **Error handling table (spec §6):** retry/backoff (Task 8 `_request`, finding F-003: retries=3, exp backoff); per-entry state so partial failure retries next pass (Task 5); full reconcile for stale state (Task 6).
- **Testing (spec §7):** diff unit (Task 3), deletion unit (Task 5), idempotency unit (Task 5), integration add→delete + metadata round-trip (Tasks 5/8/10).
- **Open question #1 — API surface (spec §8, highest risk):** Task 7 spike; the `KnowledgeClient` abstraction confines any deltas to Task 8. Fallback (direct vector store) is the spike's worst-case verdict.
- **Spec findings carried in:** F-001 (volume rw) → Task 11 note; F-002 (debounce_ms default 1500) → Tasks 1/11; F-003 (retry bounds) → Task 8.
- **Open questions #2–#4 (bge-m3 binding / fallback / granularity):** out of implementation scope; #2 is an operator note (single collection embedded with bge-m3, re-index on model change), recorded in the sample-config comment and the spike findings doc.
