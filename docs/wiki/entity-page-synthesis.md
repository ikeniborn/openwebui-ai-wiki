# Entity and page synthesis

The two LLM-driven phases that turn extracted source text into wiki pages: entity extraction (`entities.py`) and page create/merge (`pages.py`), plus the frontmatter/slug helpers (`frontmatter.py`) and the prompt templates shipped as package data. Both phases are called from [[ingest-pipeline#Ingest pipeline]].

## Entity extraction (entities.py)

`extract_entities(llm, domain, source_text)` asks the LLM for the entities worth a wiki page, returning a list of frozen `Entity(name, type, context_snippet)`. Entries with an empty name are dropped.

`build_prompt` fills `prompts/ingest_entities.md` with the domain name, the entity-types block, optional language notes, and the source. `entity_types_block(domain)` renders each `EntityType` as `- <type>: <description>. Cues: <cues>` with an optional `(min_mentions_for_page=N)` gate, or a fallback line telling the model to extract any significant concept when no types are defined. The `EntityType` schema is in [[domain-model#Domain model (domains.py)]].

## Page synthesis (pages.py)

`synthesize_pages(llm, domain, source_text, source_stem, entities, existing_pages, today)` returns a list of `WikiPage(path, content, annotation)`. It calls `llm.chat_json` and keeps only objects with both a non-empty `path` and `content`.

`WikiPage` carries the file path (`<stem>.md`), the full markdown including frontmatter, and an `annotation` — a page-level summary used for chunking but **not** written into the frontmatter. `build_prompt` fills `prompts/ingest_pages.md` with the entities block, the existing-pages block (so the model merges instead of overwriting), the source, and `today`. The `annotation` becomes the summary chunk in [[chunking-and-storage#Building chunk inputs]].

## Page I/O

`write_page(wiki_dir, page)` resolves the target under the domain wiki dir, **rejects any path that escapes it** (`is_relative_to` guard against LLM-returned traversal), creates parent dirs, and writes UTF-8. `read_existing_pages(wiki_dir, stems)` loads pages whose stem files already exist, for the merge step.

The existing-page read is keyed by the stems computed from extracted entities, so synthesis sees only the pages it might update. Merge semantics (add new facts, never drop old) are enforced by the prompt, not the code.

## Frontmatter and slugs

`frontmatter.py` splits YAML frontmatter and derives wiki page stems from entity names. `split_frontmatter(doc)` returns `(dict, body)`, or `({}, doc)` when there is no frontmatter block. Used both here and by deletion reconciliation in [[ingest-pipeline#Source-deletion reconciliation]].

`page_stem(domain_id, entity_name)` returns `wiki_<domain_id>_<entity_slug>`. `entity_slug` lowercases, **transliterates Russian Cyrillic → Latin** via a fixed map, NFKD-folds to ASCII, then collapses non-`[a-z0-9]` runs to `_`. The transliteration step exists because the corpus is Russian; without it Cyrillic names folded to an empty slug.

## Prompt templates

Two prompts live in `src/owaw/prompts/` and ship as package data, loaded once at import via `importlib.resources` (so wheel installs work). They are reference-derived, not reused code.

`ingest_entities.md` instructs the model to return `{"reasoning","entities":[...]}` with canonical names, optional types, and a context snippet, honoring the `min_mentions_for_page` gate. `ingest_pages.md` instructs create-or-merge, mandates the `wiki_<domain_id>_<slug>` stem, requires frontmatter (`wiki_sources`, `wiki_updated`, `wiki_status`, `tags`, `wiki_outgoing_links`), restricts body links to bare `[[stem]]`, and requires a ~600–800 char single-line `annotation` per page. Both return a single JSON object parsed by [[llm-client#JSON with retry]].
