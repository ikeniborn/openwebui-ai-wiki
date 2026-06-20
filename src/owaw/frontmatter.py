"""YAML frontmatter split + entity-name → wiki stem (matches ingest.md stem rule)."""
from __future__ import annotations

import re
import unicodedata

import yaml

_FM_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)


def split_frontmatter(doc: str) -> tuple[dict, str]:
    m = _FM_RE.match(doc)
    if not m:
        return {}, doc
    fm = yaml.safe_load(m.group(1)) or {}
    return fm, doc[m.end():]


def entity_slug(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    ascii_name = ascii_name.lower()
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_name).strip("_")
    return slug


def page_stem(domain_id: str, entity_name: str) -> str:
    return f"wiki_{domain_id}_{entity_slug(entity_name)}"
