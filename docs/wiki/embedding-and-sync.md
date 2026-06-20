# Embedding and sync

SP2 — the sync sidecar that mirrors SP1's on-disk chunk records into a single OpenWebUI Knowledge collection, kept current as the chunks change. It reads `chunks/*.jsonl`, diffs against a persisted state, and adds/deletes entries via OpenWebUI's REST API; OpenWebUI embeds each entry with bge-m3 (via LiteLLM). One subsystem of three — see [[architecture#Three subsystems]]; consumes the records described in [[chunking-and-storage#Chunk store (chunkstore.py)]].

## Desired set and diff (sync.py)

`build_desired(chunks_dir)` loads every `chunks/*.jsonl` record across all domains into a hash-keyed `dict[str, DesiredEntry]`, deduping by content `hash` (identical text → one entry). `DesiredEntry` carries `hash, embed_text, domain, page_id, kind`. `diff(desired_hashes, synced_hashes)` returns `(to_add, to_delete)` as plain set differences — new hashes to push, stale hashes to remove. This layer is pure and unit-testable without any OpenWebUI client.

## Sync state (syncstate.py)

`SyncState` persists the mapping from each pushed chunk `hash` to its OpenWebUI entry id, at `state/sync_<collection>.json`. It mirrors the manifest pattern behind [[ingest-pipeline#Idempotency and crash recovery]]: `load`, `synced_hashes`, `entry_id`, `mark`, `forget`, `replace` (swap the whole map, used by reconcile), and `save` (parent mkdir + JSON). Keeping the map means a diff is O(changed), not O(collection). The path is resolved by `paths.sync_state_path` — see [[domain-model#Data layout (paths.py)]].

## Sync engine (sync.py)

`SyncEngine(client, state, chunks_dir)` converges the collection to the desired set. `sync()` builds the desired set, diffs against the state, calls `client.add` for new hashes (recording the returned entry id in state) and `client.delete` for stale ones (forgetting them), then saves state once. It is **per-entry resilient**: a failing add/delete is logged and skipped, so state records only confirmed calls and a re-run on unchanged input issues zero API calls (idempotent). `reconcile()` rebuilds state from the live collection listing first (handling stale state and orphan entries), then runs `sync()` — this is the full-reconcile pass run on startup.

## OpenWebUI Knowledge client (knowledge.py)

A `KnowledgeClient` Protocol (`add(hash, text, meta) -> entry_id`, `delete(entry_id)`, `list_entries() -> [(entry_id, hash)]`) decouples the engine from OpenWebUI's API, so the engine is tested against an in-memory fake and the API risk is isolated to one class. `OpenWebUIKnowledgeClient` implements it over httpx using the single-call upload-with-metadata path: `add` uploads `embed_text` as a file named `<hash>.md` to `POST /api/v1/files/` with a `file_metadata` JSON field `{domain, page_id, kind, file_hash, knowledge_id}`; the `knowledge_id` makes OpenWebUI auto-link the file to the collection and embed it server-side, so metadata is stored and there is no premature-attach race. `list_entries` recovers the hash from `meta.file_hash` (fallback: the filename stem). Requests carry a bearer token and retry with backoff on transport errors and 5xx; 4xx errors raise immediately (no wasted retries). `from_config` reads the token from the env var named by the config.

## Configuration (config.py)

Three optional sections extend the shared config — see [[domain-model#Configuration (config.py)]]. `OpenWebUIConfig` (`base_url`, `collection`, `api_token_env` defaulting to `OWAW_OPENWEBUI_TOKEN`) is required for sync and `None` when absent; `EmbeddingConfig` (`model`, default `bge-m3`); `SyncConfig` (`debounce_ms`, default 1500). Secrets stay in the environment, never the file — the token value is injected via the env var, never committed.

## CLI and autosync (cli.py, daemon.py)

Two commands extend the Typer app (see [[cli-and-daemon#CLI]]). `owaw sync` runs a one-shot full reconcile and prints `+added -deleted =unchanged`; it errors clearly if no `openwebui` section is configured. `owaw sync-watch` is the daemon: it reconciles on start, then re-syncs on every `chunks/` change. The watch reuses the SP1 `daemon.watch_paths` helper — a generic inotify observer over arbitrary directories, debounced by the same [[cli-and-daemon#Debouncer]] used by [[cli-and-daemon#Watch command]].

## Deployment (sidecar)

SP2 ships as a second container, `owaw-sync`, in the `minipc-traefik` stack — the same image as `owaw`, with `command: ["sync-watch"]`. It joins `proxy-net` to reach OpenWebUI internally (no Traefik router, no public route) and mounts the shared `owaw_data` volume read-write: it reads `chunks/` and writes only `state/sync_<collection>.json`. The `OWAW_OPENWEBUI_TOKEN` secret is injected via `env_file`. Sample config and the compose service live under `docs/deploy/` — see [[deployment#Compose wiring]] and [[deployment#Configuration files]].
