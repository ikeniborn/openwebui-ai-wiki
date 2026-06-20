"""YAML frontmatter split + entity-name → wiki stem (matches ingest.md stem rule)."""
from __future__ import annotations

import re
import unicodedata

import yaml

_FM_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)

# Russian Cyrillic -> Latin (applied to lowercased text before the ASCII fold)
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def _translit(s: str) -> str:
    return "".join(_TRANSLIT.get(ch, ch) for ch in s)


def split_frontmatter(doc: str) -> tuple[dict, str]:
    m = _FM_RE.match(doc)
    if not m:
        return {}, doc
    fm = yaml.safe_load(m.group(1)) or {}
    return fm, doc[m.end():]


def entity_slug(name: str) -> str:
    lowered = _translit(name.lower())
    ascii_name = unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_name).strip("_")
    return slug


def page_stem(domain_id: str, entity_name: str) -> str:
    return f"wiki_{domain_id}_{entity_slug(entity_name)}"
