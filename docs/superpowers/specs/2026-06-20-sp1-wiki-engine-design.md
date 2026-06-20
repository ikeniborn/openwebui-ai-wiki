# SP1 — Wiki Engine — Design

- **Date:** 2026-06-20
- **Status:** Design (approved shape, pending written-spec review)
- **Project:** `openwebui-ai-wiki` (future standalone repo) — see [`../../../README.md`](../../../README.md)
- **Subsystem:** SP1 of 3 (SP1 Wiki engine → SP2 Embedding+sync → SP3 OpenWebUI agent)

## 1. Context

`openwebui-ai-wiki` builds and maintains a structured AI wiki from configurable document
sources and serves a shared documentation agent inside OpenWebUI. The system is split into three
subsystems, each with its own spec → plan → implementation cycle. This document specifies **SP1**,
the foundation the other two depend on.

SP1 is a **Python rewrite** of the engine in [`obsidian-ai-wiki`](../../../../obsidian-ai-wiki),
an Obsidian plugin. That project is used as a **reference specification** — its prompts, chunking
algorithm, and phase logic — **not as reused code** (engine strategy "Z", locked).

### Locked program decisions (apply across SP1–SP3)

- Engine strategy: **Python rewrite** in the OpenWebUI/LiteLLM stack.
- Generation LLM: **configurable, default cloud** (e.g. `ollama *:cloud` / Anthropic via LiteLLM).
- Embedding model: configurable, default **bge-m3** — an **SP2 concern**; SP1 chunk records are
  embedding-model-agnostic (they store `embed_text`, not vectors).
- PDF/Office extraction: **Docling**.
- Sources: a configurable set of **multiple folders, arbitrary nesting depth**.
- Update semantics: **incremental merge** by default, **full rebuild** via an explicit CLI command.
- Runtime: **daemon (inotify) + CLI**.

## 2. Goal and scope

**Goal.** Turn configured document sources into a maintained, cross-linked wiki on disk, plus
section-aware chunk records ready for embedding — kept current automatically as sources change.

### In scope

- Domain model and configuration (`domains.yaml`).
- Ingest pipeline: text extraction → entity/topic extraction → page create/merge → index/cross-link
  maintenance → re-chunking.
- Faithful port of the chunking algorithm (`page-similarity.ts`).
- Daemon (inotify watch, debounced) and CLI (`init`, `ingest`, `rebuild`, `domain add/list`).
- On-disk outputs: wiki markdown pages, chunk records, source-state manifest.
- Incremental update and orphan handling on source deletion.

### Out of scope (other subsystems)

- Embedding chunks with bge-m3 and pushing into an OpenWebUI Knowledge collection → **SP2**.
- inotify-driven sync of the Knowledge collection, deletion propagation to OpenWebUI → **SP2**.
- Doc Tool, Workspace Model, agent prompt, OpenWebUI wiring → **SP3**.
- Retrieval/ranking (RRF fusion, seeds) from the reference plugin — OpenWebUI provides retrieval;
  not reimplemented here.

## 3. Reference mapping

SP1 ports behavior from these `obsidian-ai-wiki` artifacts (read them when implementing):

| SP1 concern | Reference artifact |
|---|---|
| Domain schema | `src/domain.ts` (`DomainEntry`, `EntityType`) |
| Entity/topic extraction | `prompts/ingest-entities.md`, `src/phases/ingest.ts` |
| Page create/merge | `prompts/ingest.md`, `prompts/ingest-merge.md`, `src/phases/ingest.ts` |
| Cross-link/path fixing | `prompts/ingest-fix-paths.md`, `src/phases/query-link-validator.ts` |
| Domain init | `prompts/init.md`, `src/phases/init.ts` |
| Chunking | `src/page-similarity.ts` (`splitSections`, `buildChunkInputs`, `ChunkingConfig`) |
| Robust LLM JSON parsing | `src/phases/parse-with-retry.ts`, `prompts/repair-json.md` |

## 4. Domain model

A **domain** pairs a set of sources with a wiki output folder and the entity types to extract.
Ported from `DomainEntry` / `EntityType`. Stored in `domains.yaml`.

```yaml
domains:
  - id: infra                      # [\p{L}\p{N}_-]+
    name: "Infrastructure"
    wiki_folder: infra             # subfolder under wiki/
    source_paths:                  # multiple, arbitrary nesting
      - /data/sources/minipc-docs
      - /data/sources/runbooks
    entity_types:
      - type: service
        description: "A deployed service or daemon"
        extraction_cues: ["systemd unit", "container", "port"]
        min_mentions_for_page: 2   # optional: gate page creation
        wiki_subfolder: services   # optional: where pages of this type go
    language_notes: "Corpus is mostly Russian; keep entity names verbatim."
```

A small default `entity_types` set ships as a starting point and is overridable per domain.
CLI manages domains; `init` materializes the wiki structure (`_index.md`, domain config).

## 5. Ingest pipeline

Triggered per changed source file (daemon) or per domain (CLI). Steps:

1. **Extract text.** Docling for PDF/Office; passthrough for markdown/txt/code. Extraction
   failures skip the file (logged), pipeline continues.
2. **Extract entities/topics.** Generation LLM (default cloud) applies the domain's `entity_types`
   to produce structured entities/topics. JSON parsed with retry/repair.
3. **Create or merge pages.** For each entity/topic above its `min_mentions_for_page` threshold,
   create a new wiki page or **incrementally merge** into the existing one. Pages are markdown with
   frontmatter including an `annotation` (page-level summary) and `[[wikilinks]]`.
4. **Maintain index and cross-links.** Update `_index.md`; validate and fix wikilinks.
5. **Re-chunk affected pages.** Run `buildChunkInputs` (see §6); write chunk records for changed
   pages, replacing prior records for those pages.

`rebuild --domain` re-runs the full pipeline over all sources of a domain (drops and regenerates
its wiki + chunks). Used after major source changes or prompt/algorithm updates.

## 6. Chunking (faithful port)

Ports `splitSections` + `buildChunkInputs` exactly. Per wiki page, given its `annotation` (summary)
and `body`:

- **One `summary` chunk:** `embed_text = annotation`.
- **One `section` chunk per section window:** `embed_text = annotation + "\n\n" + heading + "\n" + window`.
  The annotation (article summary) is therefore **prepended to every section chunk** — this is the
  "article summary in each section" requirement.

Section windowing rules (from the reference):

- **Sectioning:** split body by `##` (H2); `###`+ stay inside their H2 unit; lead text before the
  first H2 is its own headless unit. (`toUnits`)
- **Merge short units:** a unit shorter than `minChars` merges into the previous *headed* unit only
  when that unit is itself ≥ `minChars` (prevents two short sections collapsing and losing labels).
  (`mergeShort`)
- **Intra-section overlap:** a unit longer than `maxChars` is sliding-windowed with
  `step = maxChars − overlapChars`. (`windowUnit`)
- **Fold cap:** if window count exceeds `maxCount`, the tail is folded into one final chunk.
- **Hashing:** each chunk carries a stable hash of its `embed_text` for change detection /
  idempotent replacement.

```
ChunkingConfig:  maxChars, minChars, overlapChars (default 200), maxCount
ChunkRecord:     { page_id, domain, kind: "summary" | "section", embed_text, hash }
```

Starting values for `maxChars` / `minChars` / `maxCount` are taken from `DEFAULT_CHUNKING` in
`page-similarity.ts` and exposed as config (§9) for tuning.

Chunk records are **embedding-model-agnostic**: they hold `embed_text`, not vectors. SP2 owns
embedding (bge-m3) and the vector cache.

## 7. Runtime

**Daemon.** Watches each domain's `source_paths` via inotify (recursive), debounced to coalesce
bursts. On change: resolve affected domain(s) → run the ingest pipeline for changed files →
update wiki + chunk records. Work is **serialized per domain** to avoid concurrent page writes;
distinct domains may run in parallel.

**CLI.**

| Command | Purpose |
|---|---|
| `init --domain <id>` | Materialize a domain's wiki structure and config |
| `ingest [--domain <id>]` | One-shot incremental ingest (all domains or one) |
| `rebuild --domain <id>` | Full re-ingest of a domain (drop + regenerate) |
| `domain add` / `domain list` | Manage `domains.yaml` |

**Idempotency.** `state/manifest.json` maps each source file → content hash + last processed
result. Unchanged files are skipped. A crash mid-run is recoverable: the manifest commits only
after a file's pages and chunks are written, so an interrupted run re-processes only the
in-flight file.

## 8. On-disk layout

A single data directory, mounted as a volume (consumed by SP2 for embedding and by SP3's Doc Tool
for live reads):

```
data/
  domains.yaml                 # domain definitions
  config.yaml                  # generation model, chunking params, Docling settings
  wiki/<domain>/*.md           # generated pages (frontmatter: annotation, entities, links)
  wiki/<domain>/_index.md      # domain index
  wiki/<domain>/.domain.yaml   # per-domain materialized config/state
  chunks/<domain>.jsonl        # chunk records: {page_id, kind, embed_text, hash}
  state/manifest.json          # source file hashes → processed state
  logs/                        # ingest run logs
```

Chunk store format: **JSONL** (one record per line; human-diffable; replace-by-page is a filtered
rewrite). Revisit to SQLite only if per-page rewrite cost becomes a bottleneck on a large corpus.

## 9. Configuration

`config.yaml`:

```yaml
generation:
  model: "<litellm-model-id>"    # default: a cloud model; configurable
  base_url: "http://host.docker.internal:4000/v1"   # LiteLLM
  # api key sourced from env / secrets file, not committed
chunking:
  maxChars: <n>
  minChars: <n>
  overlapChars: 200
  maxCount: <n>
extraction:
  engine: docling
daemon:
  debounce_ms: <n>
```

Secrets (LiteLLM key) come from an env file (`chmod 600`), never committed — consistent with the
existing `openwebui.conf` pattern in the `minipc-traefik` stack.

## 10. Error handling

| Failure | Behavior |
|---|---|
| Docling extraction fails | Skip file, log, continue pipeline |
| LLM call / JSON parse fails | Retry with repair (`parse-with-retry`); on exhaustion, skip the page and keep the last valid version |
| Source file deleted | Remove or mark stale the orphaned pages/chunks for that source (incremental) |
| Daemon crash mid-ingest | per-domain `manifest_<domain>.json` (saved after each file) enables resume; only the in-flight file re-processes |
| Embedding/LiteLLM down | Not SP1's path — SP1 never embeds; chunk records are produced regardless |

## 11. Testing

- **Chunker port (unit, golden):** assert parity with the reference on representative inputs —
  `##` sectioning, `###` nesting stays in-unit, lead-text headless unit, `mergeShort` label
  preservation, intra-section overlap (`step = maxChars − overlapChars`), summary-prefix on every
  section chunk, fold past `maxCount`, stable hashing.
- **Pipeline (integration):** a small fixture corpus (markdown + one PDF) → assert generated pages
  (frontmatter `annotation`, wikilinks) and chunk records. LLM calls are **mocked** for
  determinism; entity extraction and merge use canned responses.
- **Live smoke (optional, manual):** one real run against LiteLLM to validate end-to-end wiring.
- **Idempotency:** re-running ingest on unchanged sources produces no writes; editing one file
  re-chunks only its pages.

## 12. Open questions

None blocking. Defaults chosen above (JSONL chunk store; small default `entity_types` set;
debounce window) are revisitable during implementation without changing the architecture.

## 13. Implementation notes (post-build)

Resolved deltas from the original design, settled during implementation:

- **Per-domain manifest.** The state file is `state/manifest_<domain>.json` (not a single shared
  `state/manifest.json`). This removes a last-writer-wins race when distinct domains ingest in
  parallel under the daemon (§7). The manifest is also saved **after each file** (not once per run),
  so a crash re-processes only the in-flight file (§7 crash-recovery guarantee).
- **Cyrillic entity slugs.** `entity_slug` transliterates Russian Cyrillic → Latin before the ASCII
  fold (the corpus is Russian); otherwise Cyrillic names collapsed to an empty slug.
- **Prompts ship as package data** (`src/owaw/prompts/`, loaded via `importlib.resources`) so the
  wheel install works.
- **`write_page` path-traversal guard** rejects LLM-returned paths that escape the domain wiki dir.

Deferred (tracked as follow-ups, not built in SP1):

- **Wikilink validation/fixing** (§5 step 4). SP1 rebuilds `_index.md` but does not yet validate or
  repair `[[stem]]` links in page bodies. The synthesis prompt instructs correct links; impact is
  on **SP3** (which serves page bodies), not SP2 (which embeds `embed_text`). Add a deterministic
  dead-link pass or an LLM fix-paths phase in a follow-up.
- **`.domain.yaml` snapshot and `logs/` file routing** (§8) are not written/wired yet; `logging`
  currently goes to stderr. Low value until operations need them.
