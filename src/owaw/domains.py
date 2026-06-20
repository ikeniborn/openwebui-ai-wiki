"""Domain model + domains.yaml persistence. Ported from src/domain.ts."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

_ID_RE = re.compile(r"^[\w-]+$", re.UNICODE)


@dataclass(frozen=True)
class EntityType:
    type: str
    description: str
    extraction_cues: list[str]
    min_mentions_for_page: int | None = None
    wiki_subfolder: str | None = None


@dataclass(frozen=True)
class Domain:
    id: str
    name: str
    wiki_folder: str
    source_paths: list[str]
    entity_types: list[EntityType]
    language_notes: str = ""


def validate_domain_id(domain_id: str) -> str | None:
    if not domain_id:
        return "domain id is empty"
    if not _ID_RE.match(domain_id):
        return "domain id allows only letters/digits/_/-"
    return None


def _domain_to_dict(d: Domain) -> dict:
    out = asdict(d)
    out["entity_types"] = [
        {k: v for k, v in asdict(et).items() if v is not None} for et in d.entity_types
    ]
    return out


def _domain_from_dict(raw: dict) -> Domain:
    ets = [
        EntityType(
            type=e["type"],
            description=e.get("description", ""),
            extraction_cues=list(e.get("extraction_cues", [])),
            min_mentions_for_page=e.get("min_mentions_for_page"),
            wiki_subfolder=e.get("wiki_subfolder"),
        )
        for e in raw.get("entity_types", [])
    ]
    return Domain(
        id=raw["id"],
        name=raw.get("name", raw["id"]),
        wiki_folder=raw["wiki_folder"],
        source_paths=list(raw.get("source_paths", [])),
        entity_types=ets,
        language_notes=raw.get("language_notes", ""),
    )


def load_domains(path: Path) -> list[Domain]:
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [_domain_from_dict(d) for d in raw.get("domains", [])]


def save_domains(domains: list[Domain], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"domains": [_domain_to_dict(d) for d in domains]}
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def add_domain(domain: Domain, path: Path) -> None:
    err = validate_domain_id(domain.id)
    if err:
        raise ValueError(err)
    existing = load_domains(path)
    if any(d.id == domain.id for d in existing):
        raise ValueError(f"domain '{domain.id}' already exists")
    save_domains([*existing, domain], path)
