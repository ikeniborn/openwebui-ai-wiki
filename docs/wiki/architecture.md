# Architecture

`openwebui-ai-wiki` (package `owaw`) is a server-side AI wiki engine for OpenWebUI. It turns configured document sources into a maintained, cross-linked markdown wiki plus embedding-ready chunk records. This page maps the whole system and the SP1 module layout.

## Three subsystems

The product is split into three subsystems, each with its own spec → plan → implementation cycle. Only SP1 is implemented in this branch; SP2 and SP3 are designed but not built.

- **SP1 — Wiki engine** (this codebase): domains (sources → wiki), entity extraction, page create/merge, Docling extraction, section-aware chunking. Depends on nothing. See [[ingest-pipeline#Ingest pipeline]].
- **SP2 — Embedding + sync**: chunk records → bge-m3 embeddings (via LiteLLM) → one OpenWebUI Knowledge collection; inotify autosync; deletion propagation. Depends on SP1. SP1 chunk records are embedding-model-agnostic — they store `embed_text`, not vectors.
- **SP3 — OpenWebUI agent**: Doc Tool (live read/list/search, jailed read-only) + Workspace Model sharing wiki + Knowledge + Tool to all users. Depends on SP2.

## Lineage and strategy

SP1 is a clean Python rewrite of [`obsidian-ai-wiki`](../../README.md), an Obsidian plugin used as a **reference spec** — its prompts, chunking algorithm (`page-similarity.ts`), and phase logic — not as reused code (engine strategy "Z", locked).

The reference contributes: the domain schema (`src/domain.ts`), the entity/page prompts, the chunking port (`splitSections`/`buildChunkInputs`), and robust LLM JSON parsing. OpenWebUI provides retrieval/ranking, so RRF fusion and seeds from the plugin are out of scope.

## Locked decisions

Decisions that hold across SP1–SP3 and shape the code. They are fixed inputs, not open questions.

- **Engine:** Python rewrite in the OpenWebUI/LiteLLM stack.
- **Generation LLM:** configurable, default a cloud model via LiteLLM (`http://host.docker.internal:4000/v1`). See [[llm-client#LLM client]].
- **Embedding model:** configurable, default **bge-m3** (Russian corpus) — an SP2 concern.
- **PDF/Office extraction:** **Docling**. See [[ingest-pipeline#Text extraction]].
- **Sources:** multiple folders, arbitrary nesting depth, per domain.
- **Update semantics:** incremental merge by default; full rebuild via explicit CLI command.
- **Runtime:** daemon (inotify) + CLI. See [[cli-and-daemon#CLI]].

## Module map

SP1 is a single flat Python package `src/owaw/` (~980 lines). Modules group into the configuration layer, the ingest pipeline, the LLM synthesis phases, and the on-disk artifacts.

- Configuration & data layout: `domains.py`, `config.py`, `paths.py` → [[domain-model#Domain model (domains.py)]].
- Ingest orchestration: `ingest.py`, `extract.py`, `manifest.py` → [[ingest-pipeline#Ingest pipeline]].
- LLM synthesis: `entities.py`, `pages.py`, `frontmatter.py`, `prompts/` → [[entity-page-synthesis#Entity extraction (entities.py)]].
- LLM transport: `llm.py` → [[llm-client#LLM client]].
- Chunking & storage: `chunking.py`, `chunkstore.py`, `index.py` → [[chunking-and-storage#Section-aware chunking]].
- Runtime entry points: `cli.py`, `daemon.py` → [[cli-and-daemon#CLI]].
- Packaging & ops: `Dockerfile`, compose snippet, sample config → [[deployment#Packaging (pyproject.toml)]].

## On-disk data layout

A single data directory (root `$OWAW_DATA_DIR`, default `./data`) holds all inputs and outputs. It is mounted as a volume and later consumed by SP2 (embedding) and SP3 (live reads). Resolved by `paths.py` — see [[domain-model#Data layout (paths.py)]].

```
data/
  domains.yaml                    # domain definitions
  config.yaml                     # generation model, chunking params, Docling, debounce
  wiki/<domain>/*.md              # generated pages (frontmatter + [[wikilinks]])
  wiki/<domain>/_index.md         # domain index (sorted page list)
  chunks/<domain>.jsonl           # chunk records {page_id, domain, kind, embed_text, hash}
  state/manifest_<domain>.json    # per-domain source-hash state
  logs/                           # ingest run logs (dir created; file routing deferred)
```

The chunk store is JSONL (human-diffable; replace-by-page is a filtered rewrite). Per-domain manifests (not a single shared file) avoid a last-writer-wins race when domains ingest in parallel under the daemon.

## Implementation deltas

Resolved deltas from the original SP1 design, settled during the build. Useful when the spec and code disagree — the code wins.

- **Per-domain manifest** `state/manifest_<domain>.json`, saved after each file (crash re-processes only the in-flight file). See [[ingest-pipeline#Idempotency and crash recovery]].
- **Cyrillic entity slugs** transliterated to Latin before the ASCII fold. See [[entity-page-synthesis#Frontmatter and slugs]].
- **Prompts ship as package data** via `importlib.resources`.
- **`write_page` path-traversal guard** rejects LLM paths escaping the wiki dir.
- **Deferred:** wikilink validation/fixing, `.domain.yaml` snapshot, `logs/` file routing.
