"""Ingest pipeline orchestration for one source file (incremental)."""
from __future__ import annotations

import logging
from pathlib import Path

from owaw.chunking import DEFAULT_CHUNKING, ChunkingConfig, build_chunk_inputs
from owaw.chunkstore import ChunkStore
from owaw.domains import Domain
from owaw.entities import extract_entities
from owaw.extract import UnsupportedFormat, extract_text
from owaw.frontmatter import page_stem
from owaw.index import rebuild_index
from owaw.manifest import Manifest
from owaw.pages import read_existing_pages, synthesize_pages, write_page

log = logging.getLogger("owaw.ingest")


def ingest_file(
    llm, domain: Domain, src: Path, wiki_dir: Path, chunks: ChunkStore,
    manifest: Manifest, chunking: ChunkingConfig = DEFAULT_CHUNKING, today: str = "",
) -> bool:
    """Process one source file. Returns True if it was (re)processed, False if skipped."""
    if not manifest.is_changed(src):
        return False
    try:
        text = extract_text(src)
    except UnsupportedFormat:
        log.warning("skip unsupported file: %s", src)
        return False
    except Exception:  # extraction (e.g. Docling) failed — skip, keep going
        log.exception("extraction failed: %s", src)
        return False

    try:
        entities = extract_entities(llm, domain, text)
        stems = [page_stem(domain.id, e.name) for e in entities]
        existing = read_existing_pages(wiki_dir, stems)
        pages = synthesize_pages(llm, domain, text, src.stem, entities, existing, today)
    except Exception:  # LLM/synthesis failed — keep the last valid wiki, do not mark processed
        log.exception("synthesis failed, keeping last valid wiki: %s", src)
        return False

    for page in pages:
        write_page(wiki_dir, page)
        chunks.replace_page(Path(page.path).stem, build_chunk_inputs(page.annotation, page.content, chunking))

    rebuild_index(wiki_dir, domain.name)
    manifest.mark(src)
    return True
