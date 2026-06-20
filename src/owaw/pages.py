"""Page synthesis (create/merge) + page IO. Prompt: prompts/ingest_pages.md."""
from __future__ import annotations

from dataclasses import dataclass
from importlib import resources

from owaw.domains import Domain
from owaw.entities import Entity, entity_types_block

_PROMPT = resources.files("owaw.prompts").joinpath("ingest_pages.md").read_text(encoding="utf-8")


@dataclass(frozen=True)
class WikiPage:
    path: str          # stem + ".md", relative to the domain wiki dir
    content: str       # full markdown incl. frontmatter
    annotation: str    # page-level summary for chunking (NOT written to frontmatter)


def _entities_block(entities: list[Entity]) -> str:
    return "\n".join(
        f"- {e.name}" + (f" [{e.type}]" if e.type else "")
        + (f": {e.context_snippet}" if e.context_snippet else "")
        for e in entities
    ) or "(none)"


def _existing_block(existing: list[WikiPage]) -> str:
    if not existing:
        return "(none)"
    return "\n\n".join(f"### {p.path}\n{p.content}" for p in existing)


def build_prompt(domain: Domain, source_text: str, source_stem: str,
                 entities: list[Entity], existing_pages: list[WikiPage], today: str) -> str:
    lang = f"\nLANGUAGE NOTES: {domain.language_notes}" if domain.language_notes else ""
    return _PROMPT.format(
        domain_name=domain.name,
        domain_id=domain.id,
        entity_types_block=entity_types_block(domain),
        lang_notes=lang,
        entities_block=_entities_block(entities),
        existing_pages_block=_existing_block(existing_pages),
        source_stem=source_stem,
        source_text=source_text,
        today=today,
    )


def synthesize_pages(llm, domain: Domain, source_text: str, source_stem: str,
                     entities: list[Entity], existing_pages: list[WikiPage],
                     today: str = "") -> list[WikiPage]:
    obj = llm.chat_json(
        build_prompt(domain, source_text, source_stem, entities, existing_pages, today)
    )
    pages: list[WikiPage] = []
    for p in obj.get("pages", []):
        path = (p.get("path") or "").strip()
        content = p.get("content") or ""
        if not path or not content:
            continue
        pages.append(WikiPage(path=path, content=content, annotation=p.get("annotation") or ""))
    return pages


def write_page(wiki_dir: Path, page: WikiPage) -> None:
    target = (wiki_dir / page.path).resolve()
    if not target.is_relative_to(wiki_dir.resolve()):
        raise ValueError(f"page path escapes wiki_dir: {page.path!r}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(page.content, encoding="utf-8")


def read_existing_pages(wiki_dir: Path, stems: list[str]) -> list[WikiPage]:
    out: list[WikiPage] = []
    for stem in stems:
        f = wiki_dir / f"{stem}.md"
        if f.exists():
            out.append(WikiPage(path=f"{stem}.md", content=f.read_text(encoding="utf-8"), annotation=""))
    return out
