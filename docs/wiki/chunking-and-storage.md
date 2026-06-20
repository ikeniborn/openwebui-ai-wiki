# Chunking and storage

The chunk-production path and the on-disk artifacts it writes: the section-aware chunker (`chunking.py`, a faithful port of `page-similarity.ts`), the JSONL chunk store (`chunkstore.py`), and the per-domain index (`index.py`). Driven by [[ingest-pipeline#Ingest pipeline]]; consumed downstream by [[embedding-and-sync#Desired set and diff (sync.py)]] (SP2).

## Section-aware chunking

`chunking.py` ports `splitSections` + `buildChunkInputs` exactly. Per wiki page it emits one `summary` chunk (the annotation) plus one `section` chunk per section window, with the annotation prepended to every section chunk.

`ChunkingConfig` (frozen) holds `maxChars=1200`, `overlapChars=200`, `minChars=200`, `maxCount=12`; `DEFAULT_CHUNKING` is the shared default. Config overrides flow from [[domain-model#Configuration (config.py)]]. Dataclasses `SectionWindow(heading, window)` and `ChunkInput(kind, embed_text, hash)` carry the intermediate and output shapes.

## Section windowing rules

`split_sections(body, chunking)` strips frontmatter and the H1 title, splits into units, merges short ones, windows long ones, and folds the tail past the cap. Each rule mirrors the reference algorithm.

- **Sectioning** (`_to_units`): split by `##` (H2); text before the first H2 becomes a headless lead unit; `###`+ stay inside their H2 unit. Empty units are dropped.
- **Merge short** (`_merge_short`): a unit shorter than `minChars` merges into the previous unit only when that previous unit is itself headed and ≥ `minChars` — preventing two short sections from collapsing and losing labels.
- **Intra-section overlap** (`_window_unit`): a unit longer than `maxChars` is sliding-windowed with `step = max(1, maxChars − overlapChars)`.
- **Fold cap**: if window count exceeds `maxCount`, the tail is folded into one final `## (+N sections folded)` chunk capped at `maxChars`.

## Building chunk inputs

`build_chunk_inputs(annotation, body, chunking)` returns the chunk list: first a `summary` chunk whose `embed_text` is the annotation, then one `section` chunk per window whose `embed_text` is `annotation + "\n\n" + heading + "\n" + window`.

Prepending the annotation to every section chunk is the "article summary in each section" requirement from the reference. Each `ChunkInput` carries a SHA-256 `hash` of its `embed_text` for change detection and idempotent replacement. The annotation comes from page synthesis — see [[entity-page-synthesis#Page synthesis (pages.py)]].

## Chunk store (chunkstore.py)

`ChunkStore` persists chunk records as JSONL — one record per line, human-diffable. Record shape: `{page_id, domain, kind, embed_text, hash}`. Records are embedding-model-agnostic (they hold `embed_text`, not vectors); SP2 reads them and produces vectors.

`replace_page(page_id, chunks)` rewrites the file with all rows for other pages plus the new chunks for this page (replace-by-page). `delete_page(page_id)` rewrites without that page's rows. `read_all` parses non-blank lines; `_rewrite` writes with `ensure_ascii=False` so Cyrillic stays readable. Both `write` paths are filtered full rewrites — revisit to SQLite only if that cost becomes a bottleneck.

## Domain index

`index.py::rebuild_index(wiki_dir, domain_name)` regenerates `_index.md` deterministically: a `# <domain_name> — index` heading followed by a sorted `- [[stem]]` line per page, excluding `_index` and any `_`-prefixed stem.

It is rewritten on every successful `ingest_file` so the index always reflects current pages. Note: SP1 rebuilds the index but does **not** yet validate or repair `[[stem]]` links inside page bodies — that is a deferred follow-up noted in [[architecture#Implementation deltas]].
