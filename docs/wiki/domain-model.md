# Domain model

The configuration layer: how a domain pairs sources with a wiki output, how runtime config is loaded, and where artifacts live on disk. Three modules: `domains.py`, `config.py`, `paths.py`. Consumed everywhere downstream — see [[architecture#Module map]].

## Domain model (domains.py)

A **domain** pairs a set of source paths with a wiki output folder and the entity types to extract. Modelled as frozen dataclasses `Domain` and `EntityType`, persisted to `domains.yaml`. Ported from the reference `DomainEntry`/`EntityType`.

`Domain` fields: `id`, `name`, `wiki_folder`, `source_paths` (list, arbitrary nesting), `entity_types` (list of `EntityType`), `language_notes` (default `""`). `EntityType` fields: `type`, `description`, `extraction_cues` (list), optional `min_mentions_for_page`, optional `wiki_subfolder`.

## Domain ID validation

`validate_domain_id` enforces `^[\w-]+$` (Unicode word chars plus dash) and rejects empty IDs, returning an error string or `None`. `add_domain` calls it and refuses duplicate IDs before persisting.

The domain `id` flows into page stems (`wiki_<id>_<slug>`) and per-domain file paths, so the charset restriction keeps generated filenames safe. See [[entity-page-synthesis#Frontmatter and slugs]].

## domains.yaml persistence

`load_domains(path)` reads the YAML (returns `[]` if absent), mapping each entry through `_domain_from_dict`. `save_domains` writes `{"domains": [...]}` via `_domain_to_dict`, with `allow_unicode=True` and `sort_keys=False` to keep Cyrillic readable and field order stable.

`_domain_to_dict` drops `None` fields from each `EntityType` so optional keys (`min_mentions_for_page`, `wiki_subfolder`) are omitted rather than written as `null`. `add_domain(domain, path)` validates, loads existing, rejects duplicates, then re-saves the full list.

## Configuration (config.py)

`load_config(path)` parses `config.yaml` into a frozen `Config`: `generation` (`GenerationConfig`), `chunking` (`ChunkingConfig`), `extraction_engine` (default `"docling"`), `debounce_ms` (default `1000`). Secrets never live in the file.

`GenerationConfig` holds `model`, `base_url`, and `api_key_env` (default `OWAW_LLM_KEY`) — the **name** of the env var, not the key itself. `chunking` falls back to `ChunkingConfig()` defaults per field. The generation config feeds [[llm-client#Constructing the client]]; chunking feeds [[chunking-and-storage#Section-aware chunking]].

## Data layout (paths.py)

`paths.py` resolves the on-disk layout from `$OWAW_DATA_DIR` (default `data`). Pure path math — no I/O except `ensure_dirs`. Every other module asks `paths` for locations rather than hardcoding them.

Helpers: `data_dir()`, `domains_path()` (`data/domains.yaml`), `config_path()` (`data/config.yaml`), `wiki_dir(domain)` (`data/wiki/<domain>`), `chunks_path(domain)` (`data/chunks/<domain>.jsonl`), `manifest_path(domain)` (`data/state/manifest_<domain>.json`). `ensure_dirs(domain)` creates the wiki, chunks, state, and logs directories. Full tree: [[architecture#On-disk data layout]].
