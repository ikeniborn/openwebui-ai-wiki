"""Ingest pipeline orchestration for one source file (incremental)."""
from __future__ import annotations

import logging
import os as _os
import re as _re
import shutil
from pathlib import Path

from owaw import paths as _paths
from owaw.chunking import DEFAULT_CHUNKING, ChunkingConfig, build_chunk_inputs
from owaw.chunkstore import ChunkStore
from owaw.domains import Domain
from owaw.entities import extract_entities
from owaw.extract import UnsupportedFormat, extract_text
from owaw.frontmatter import page_stem, split_frontmatter
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
    manifest.save()
    return True


# --- multi-file drivers ---

def iter_source_files(domain: Domain):
    for root in domain.source_paths:
        base = Path(root)
        if not base.exists():
            continue
        for f in sorted(base.rglob("*")):
            if f.is_file():
                yield f


def ingest_domain(llm, domain: Domain, chunking: ChunkingConfig = DEFAULT_CHUNKING,
                  today: str = "") -> int:
    _paths.ensure_dirs(domain.id)
    wiki_dir = _paths.wiki_dir(domain.id)
    chunks = ChunkStore(_paths.chunks_path(domain.id), domain=domain.id)
    manifest = Manifest.load(_paths.manifest_path(domain.id))
    reconcile_deletions(domain, wiki_dir, chunks, manifest)
    count = 0
    for f in iter_source_files(domain):
        if ingest_file(llm, domain, f, wiki_dir, chunks, manifest, chunking, today):
            count += 1
    manifest.save()
    return count


def rebuild_domain(llm, domain: Domain, chunking: ChunkingConfig = DEFAULT_CHUNKING,
                   today: str = "") -> int:
    """Drop the domain's wiki + chunks + manifest entries, then full re-ingest."""
    wiki_dir = _paths.wiki_dir(domain.id)
    if wiki_dir.exists():
        shutil.rmtree(wiki_dir)
    chunks_path = _paths.chunks_path(domain.id)
    if chunks_path.exists():
        chunks_path.unlink()
    manifest = Manifest.load(_paths.manifest_path(domain.id))
    for f in iter_source_files(domain):
        manifest.forget(f)
    manifest.save()
    return ingest_domain(llm, domain, chunking, today)


# --- source-deletion reconciliation ---

def _page_sources(page_text: str) -> list[str]:
    fm, _ = split_frontmatter(page_text)
    out: list[str] = []
    for entry in fm.get("wiki_sources", []) or []:
        m = _re.match(r"\[\[(.+?)\]\]", str(entry).strip())
        if m:
            out.append(m.group(1))
    return out


def prune_source_pages(source_stem: str, wiki_dir: Path, chunks: ChunkStore) -> int:
    removed = 0
    for page in wiki_dir.glob("*.md"):
        if page.stem == "_index":
            continue
        srcs = _page_sources(page.read_text(encoding="utf-8"))
        if source_stem in srcs and len(srcs) <= 1:
            page.unlink()
            chunks.delete_page(page.stem)
            removed += 1
    return removed


def _under_domain(src: Path, domain: Domain) -> bool:
    s = str(src)
    return any(s == r or s.startswith(str(Path(r)) + _os.sep) for r in domain.source_paths)


def reconcile_deletions(domain: Domain, wiki_dir: Path, chunks: ChunkStore,
                        manifest: Manifest) -> int:
    pruned = 0
    for src in manifest.tracked_paths():
        if _under_domain(src, domain) and not src.exists():
            prune_source_pages(src.stem, wiki_dir, chunks)
            manifest.forget(src)
            pruned += 1
    return pruned
