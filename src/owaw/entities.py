"""Entity extraction phase. Prompt: prompts/ingest_entities.md."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from owaw.domains import Domain

_PROMPT = (Path(__file__).resolve().parents[2] / "prompts" / "ingest_entities.md").read_text(
    encoding="utf-8"
)


@dataclass(frozen=True)
class Entity:
    name: str
    type: str | None = None
    context_snippet: str | None = None


def entity_types_block(domain: Domain) -> str:
    if not domain.entity_types:
        return "(no predefined types — extract any significant concept)"
    lines = []
    for et in domain.entity_types:
        cues = ", ".join(et.extraction_cues)
        gate = f" (min_mentions_for_page={et.min_mentions_for_page})" if et.min_mentions_for_page else ""
        lines.append(f"- {et.type}: {et.description}. Cues: {cues}{gate}")
    return "\n".join(lines)


def build_prompt(domain: Domain, source_text: str) -> str:
    lang = f"\nLANGUAGE NOTES: {domain.language_notes}" if domain.language_notes else ""
    return _PROMPT.format(
        domain_name=domain.name,
        entity_types_block=entity_types_block(domain),
        lang_notes=lang,
        source_text=source_text,
    )


def extract_entities(llm, domain: Domain, source_text: str) -> list[Entity]:
    obj = llm.chat_json(build_prompt(domain, source_text))
    out: list[Entity] = []
    for e in obj.get("entities", []):
        name = (e.get("name") or "").strip()
        if not name:
            continue
        out.append(Entity(name=name, type=e.get("type"), context_snippet=e.get("context_snippet")))
    return out
