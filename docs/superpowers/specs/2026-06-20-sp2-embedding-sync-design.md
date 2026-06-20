# SP2 — Embedding + Sync — Design

- **Date:** 2026-06-20
- **Status:** Design (drafted from locked SP1 decisions; pending review)
- **Project:** `openwebui-ai-wiki` (future standalone repo) — see [`../../../README.md`](../../../README.md)
- **Subsystem:** SP2 of 3 (SP1 Wiki engine → **SP2 Embedding+sync** → SP3 OpenWebUI agent)
- **Depends on:** SP1 (consumes its chunk records) — [`2026-06-20-sp1-wiki-engine-design.md`](2026-06-20-sp1-wiki-engine-design.md)

## 1. Context

SP1 produces, on disk, section-aware **chunk records** per domain
(`chunks/<domain>.jsonl`, records `{page_id, domain, kind, embed_text, hash}` — embedding-model-
agnostic, holding `embed_text`, not vectors). SP2 mirrors those records into a **single OpenWebUI
Knowledge collection** so the SP3 agent's retrieval (RAG) is always current. Embeddings are produced
with **bge-m3** (chosen for the Russian corpus), served via LiteLLM.

This realizes the **OpenWebUI-native RAG** half of the locked design: rather than building a vector
store, SP2 pushes each chunk's text into an OpenWebUI Knowledge collection and lets OpenWebUI embed
and index it with its configured embedding model (bge-m3 via LiteLLM). One on-disk chunk → one
collection entry, keyed by the chunk `hash`, kept in sync (add / delete) as SP1 rewrites the JSONL.

### Locked decisions carried in

- Single Knowledge collection; **inotify**-driven autosync.
- Embedding model configurable, default **bge-m3** via LiteLLM `/v1/embeddings`.
- Lives in the existing `minipc-traefik` stack; no new public route.

## 2. Goal and scope

**Goal.** Keep one OpenWebUI Knowledge collection in continuous sync with SP1's on-disk chunk
records — add new chunks, remove deleted ones — so RAG over the wiki reflects the current sources
within seconds of an SP1 ingest.

### In scope

- **bge-m3 enablement:** add the model to LiteLLM (embedding mode); point OpenWebUI's RAG embedding
  setting at it (OpenAI-compatible engine → LiteLLM `base_url`, model `bge-m3`).
- **Sync service (Python sidecar):** reads `chunks/<domain>.jsonl`, diffs against a persisted
  sync-state, and via the OpenWebUI Knowledge API adds new entries and deletes removed ones. One
  entry per chunk; external identity = chunk `hash` (content-addressed, so a changed chunk is a new
  hash → add-new + delete-old). Each entry carries metadata `{domain, page_id, kind}`.
- **Autosync:** inotify on the data dir's `chunks/` (debounced), or invoked right after an SP1
  ingest. Eventually-consistent; a full reconcile pass on start.
- **Deletion handling:** chunks gone from the JSONL (page pruned or re-chunked) → their entries are
  removed from the collection.
- **Idempotency:** re-running against an unchanged JSONL produces no API writes.
- **Auth:** an OpenWebUI API token (env/secret) for the Knowledge API.

### Out of scope

- Chunk/wiki generation → **SP1**.
- The Doc Tool, the Workspace Model, the agent prompt, RAG retrieval at query time → **SP3**
  (SP2 only *populates* the collection; OpenWebUI performs retrieval).

## 3. Architecture

```
SP1 data dir (shared volume)
  chunks/<domain>.jsonl  ──inotify──►  SP2 sync sidecar
                                          │  diff vs state/sync_<collection>.json
                                          ▼
                                  OpenWebUI Knowledge API
                                   add(text, meta) / delete(id)
                                          │  (OpenWebUI embeds each entry)
                                          ▼
                                  LiteLLM /v1/embeddings  → bge-m3
                                          ▼
                                  Knowledge collection "ai-wiki"  ──► (SP3 RAG)
```

- Sync sidecar container in `minipc-traefik`, reaching OpenWebUI over `proxy-net` (internal) with
  an API token. No public route.
- Shares SP1's data-dir volume read-only for `chunks/`.
- Sync-state file `state/sync_<collection>.json`: maps pushed `hash` → OpenWebUI entry id, so
  diffs are O(changed).

## 4. Data flow

1. SP1 writes/updates `chunks/<domain>.jsonl`.
2. inotify (debounced) → sidecar loads all chunk records across domains → desired set keyed by `hash`.
3. Diff vs sync-state: **new hashes** → `POST` add (text = `embed_text`, metadata `{domain,page_id,kind}`);
   **missing hashes** → `DELETE` the corresponding entries. Update sync-state on confirmed calls.
4. OpenWebUI embeds each added entry with bge-m3 (its RAG embedding model) and indexes it.
5. (Query time, SP3) OpenWebUI RAG retrieves top-k from the collection.

## 5. Configuration

```yaml
openwebui:
  base_url: "http://minipc-traefik-openwebui:8080"   # internal, proxy-net
  api_token_env: OWAW_OPENWEBUI_TOKEN                 # value from secrets, never committed
  collection: "ai-wiki"
embedding:
  model: "bge-m3"                                     # OpenWebUI RAG engine → LiteLLM
sync:
  debounce_ms: <n>
```

## 6. Error handling

| Failure | Behavior |
|---|---|
| OpenWebUI API unreachable | Retry with backoff; sync is eventually-consistent; sync-state only records confirmed calls |
| Embedding (bge-m3 / LiteLLM) down | OpenWebUI add returns an error → retry later; entry not marked synced |
| Partial batch failure | Per-entry state; the next reconcile retries only the unsynced/over-synced delta |
| Stale state vs collection | Periodic / startup **full reconcile**: list collection entries, converge to the JSONL desired set |

## 7. Testing

- **Diff logic (unit):** given old sync-state + new JSONL, assert the exact add/delete set (new
  hash → add; missing hash → delete; unchanged → no-op) against a fake Knowledge client.
- **Deletion (unit):** a hash removed from the JSONL yields a delete call and a state update.
- **Idempotency (unit):** re-running on an unchanged JSONL issues zero API calls.
- **Integration:** against a test OpenWebUI (or a recorded/mock API) — add then delete, asserting the
  collection converges; metadata round-trips.

## 8. Open questions (validate early in implementation)

- **OpenWebUI Knowledge API surface.** Confirm, against the deployed OpenWebUI version, how to add a
  **raw text snippet** (vs a file upload) to a Knowledge collection, whether a **stable external id**
  per entry is supported (else keep the hash→id map in sync-state), and the delete/list endpoints.
  This is the single highest-risk unknown — spike it first.
- **bge-m3 collection binding.** bge-m3 is 1024-dim; the collection must be created/embedded with
  bge-m3. Changing the embedding model later requires a **full re-index** of the collection.
- **Alternative (fallback) architecture.** If the Knowledge API cannot accept pre-chunked text
  cleanly, SP2 instead computes bge-m3 vectors via LiteLLM and writes to OpenWebUI's vector store
  directly — heavier and version-coupled; only if the API path is unworkable.
- **Granularity.** Single collection is locked; a per-domain collection split is a later option if
  access scoping is ever needed (would also touch SP3).
