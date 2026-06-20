# Ingest pipeline

`ingest.py` orchestrates turning one source file into wiki pages and chunk records, plus the multi-file drivers and source-deletion reconciliation. Supporting steps: text extraction (`extract.py`) and idempotency state (`manifest.py`). Entry points call this from [[cli-and-daemon#CLI]].

## Ingest pipeline

`ingest_file(llm, domain, src, wiki_dir, chunks, manifest, chunking, today)` processes one source file and returns `True` if (re)processed, `False` if skipped. It short-circuits when the manifest says the file is unchanged.

Steps in order: (1) skip if `manifest.is_changed(src)` is false; (2) `extract_text(src)` — on `UnsupportedFormat` or any extraction error, log and return `False`; (3) `extract_entities` → `page_stem` per entity → `read_existing_pages` → `synthesize_pages`, all guarded so an LLM/synthesis failure keeps the last valid wiki and returns `False` without marking the file; (4) for each page `write_page` + `chunks.replace_page`; (5) `rebuild_index`, then `manifest.mark(src)` and `manifest.save()`.

The LLM phases live in [[entity-page-synthesis#Entity extraction (entities.py)]]; chunk building in [[chunking-and-storage#Building chunk inputs]]; index in [[chunking-and-storage#Domain index]].

## Text extraction

`extract.py::extract_text(path)` returns markdown/plain text for a source. Text-like extensions pass through with `read_text`; PDF/Office go through Docling; anything else raises `UnsupportedFormat`.

`TEXT_EXTS` covers markdown, txt, rst, and common code/config formats (`.py`, `.ts`, `.yaml`, `.json`, …). `DOC_EXTS` covers `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.html`. Docling is imported lazily inside `_docling_to_markdown`, so the deterministic core and unit tests have no hard dependency on it.

## Multi-file drivers

`ingest_domain` and `rebuild_domain` apply the per-file pipeline across a domain's sources. `iter_source_files(domain)` yields every file under each `source_path` via sorted `rglob`, skipping missing roots.

`ingest_domain(llm, domain, chunking, today)` ensures dirs, opens the domain's `ChunkStore` and `Manifest`, runs `reconcile_deletions` first, then ingests each file, counting processed ones, and saves the manifest. `rebuild_domain` drops the domain wiki dir, deletes its chunks JSONL, `forget`s every current source in the manifest, then delegates to `ingest_domain` for a full regenerate.

## Idempotency and crash recovery

`manifest.py` tracks each source path → SHA-256 of its bytes, so unchanged files are skipped. The manifest is **per-domain** (`state/manifest_<domain>.json`) — see [[domain-model#Data layout (paths.py)]].

`Manifest.is_changed(src)` compares the stored hash to the current file hash; `mark` records it, `forget` drops it, `tracked_paths` lists all known sources. `ingest_file` calls `manifest.save()` immediately after a file's pages and chunks are written, so a crash mid-run re-processes only the in-flight file. Per-domain files also remove the last-writer-wins race when domains ingest in parallel under the daemon.

## Source-deletion reconciliation

When a source file disappears, its derived pages and chunks must be pruned. `reconcile_deletions` runs at the start of every `ingest_domain` pass over the manifest's tracked paths.

For each tracked path under the domain that no longer exists, `prune_source_pages(source_stem, wiki_dir, chunks)` deletes any page whose frontmatter `wiki_sources` references that source **and** lists no other source (`len(srcs) <= 1`), removing the page file and its chunks via `chunks.delete_page`; then `manifest.forget(src)`. `_page_sources` parses the `[[stem]]` entries from the page frontmatter using `split_frontmatter` — see [[entity-page-synthesis#Frontmatter and slugs]]. Pages backed by multiple sources are kept.
