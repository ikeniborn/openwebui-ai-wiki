# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`openwebui-ai-wiki` (Python package `owaw`) is a server-side AI wiki engine for OpenWebUI. It turns configured document sources into a maintained, cross-linked markdown wiki plus embedding-ready chunk records, then (in later subsystems) embeds them and exposes a Doc Agent inside OpenWebUI.

It is a **clean Python rewrite** of the `obsidian-ai-wiki` Obsidian plugin (sibling dir `../obsidian-ai-wiki`). That plugin is a **reference spec only** — its prompts, the `page-similarity.ts` chunking algorithm, and phase logic are ported, never imported. Don't add it as a dependency.

The product is three subsystems, each with its own spec → plan → implementation cycle:
- **SP1 — Wiki engine** (this codebase, implemented & merged): sources → wiki pages + chunk records.
- **SP2 — Embedding + sync** (designed, not built): chunk records → bge-m3 embeddings via LiteLLM → one OpenWebUI Knowledge collection; inotify autosync. Depends on SP1.
- **SP3 — OpenWebUI agent** (designed, not built): Doc Tool + Workspace Model shared to all users. Depends on SP2.

Design specs for SP2/SP3 live under `docs/superpowers/specs/`.

## Commands

```bash
# Install (editable, with dev extras) into the existing venv
.venv/bin/pip install -e ".[dev]"

# Run the full test suite (fast, deterministic, ~0.2s, no LLM/Docling needed)
.venv/bin/python -m pytest -q

# Run a single test file / single test
.venv/bin/python -m pytest tests/test_chunking.py
.venv/bin/python -m pytest tests/test_ingest.py::test_name -q

# CLI (console script `owaw`, also at .venv/bin/owaw)
owaw init --domain <id>          # materialize a domain's wiki structure
owaw ingest [--domain <id>]      # one-shot incremental ingest (all domains if omitted)
owaw rebuild --domain <id>       # full drop + regenerate of one domain
owaw watch [--domain <id>]       # run the inotify daemon (continuous autosync)
owaw domain add | domain list    # edit / inspect domains.yaml

# Container: bare run starts the daemon over all domains
docker build -t owaw . && docker run -v owaw_data:/data --env-file owaw.conf owaw
```

There is no separate lint step configured.

## Architecture

Single flat package `src/owaw/` (~980 lines). Layers:

- **Config & layout**: `domains.py` (Domain/EntityType, `domains.yaml`), `config.py` (`config.yaml` → frozen `Config`), `paths.py` (resolves everything under `$OWAW_DATA_DIR`, default `./data`).
- **Ingest orchestration**: `ingest.py` (per-file pipeline + multi-file drivers + deletion reconcile), `extract.py` (text/Docling extraction), `manifest.py` (per-domain source-hash state).
- **LLM synthesis**: `entities.py` (extract entities), `pages.py` (create/merge pages), `frontmatter.py` (frontmatter split + slug derivation), `prompts/*.md`.
- **LLM transport**: `llm.py` — the **only** module that does LLM egress.
- **Chunking & storage**: `chunking.py` (port of `page-similarity.ts`), `chunkstore.py` (JSONL), `index.py` (`_index.md`).
- **Runtime**: `cli.py` (Typer), `daemon.py` (watchdog/inotify + debouncer).

### Ingest flow (per source file)

`ingest_file`: skip if manifest hash unchanged → `extract_text` → `extract_entities` → `synthesize_pages` (merges into existing pages, never overwrites) → `write_page` + `chunks.replace_page` per page → `rebuild_index` → `manifest.mark` + `manifest.save`. Each LLM phase is guarded so a failure keeps the last valid wiki and leaves the file unmarked (re-tried next pass).

### On-disk data layout (`$OWAW_DATA_DIR`)

```
data/
  domains.yaml                  # domain definitions
  config.yaml                   # generation model, chunking params, docling, debounce
  wiki/<domain>/*.md            # generated pages (frontmatter + [[wikilinks]])
  wiki/<domain>/_index.md       # sorted page list, regenerated each ingest
  chunks/<domain>.jsonl         # {page_id, domain, kind, embed_text, hash}
  state/manifest_<domain>.json  # per-domain source→SHA-256
```

## Conventions that bite if missed

- **Chunk records are embedding-model-agnostic**: they store `embed_text`, not vectors. SP2 produces vectors. Don't put embeddings in SP1.
- **Per-domain manifest** (not one shared file): avoids a last-writer-wins race when domains ingest in parallel under the daemon. The manifest is saved immediately after each file so a crash re-processes only the in-flight file.
- **Secrets never touch `config.yaml`**: `GenerationConfig.api_key_env` holds the *name* of the env var (default `OWAW_LLM_KEY`); the value lives in the environment.
- **Generation goes through LiteLLM** (OpenAI-compatible, default `http://host.docker.internal:4000/v1`). The actual backend is chosen by config, not code.
- **`write_page` has a path-traversal guard**: rejects LLM-returned paths that escape the domain wiki dir. Keep it.
- **Cyrillic entity slugs are transliterated Russian→Latin** before ASCII fold (corpus is Russian; without it slugs folded to empty). Page stems are `wiki_<domain_id>_<slug>`.
- **Prompts ship as package data** (`force-include` in `pyproject.toml`, loaded via `importlib.resources`) — not read from a relative path. Editing prompts means editing `src/owaw/prompts/*.md`.
- **Docling and openai are lazy-imported** inside their functions, so the deterministic core and unit tests have no hard dependency on them.
- **LLM JSON is parsed with one repair retry** (`llm.chat_json`), tolerating code-fenced output.
- **Deferred (not yet built), don't assume present**: wikilink validation/repair inside page bodies, `logs/` file routing.

## Documentation

`docs/wiki/` is the authoritative architecture knowledge base, maintained via the **iwiki** skills. Start a task by querying it (`/iwiki-query`) for the relevant module before reading code — the wiki pages encode the decisions and implementation deltas above in depth. **After any change to functionality/architecture/behavior, regenerate the affected page (`iwiki:iwiki-ingest <changed-source>`) and run `/iwiki-lint` before responding.** Always drive iwiki via its skills, never by guessing engine subcommands.
