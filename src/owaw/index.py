"""Maintain a domain's _index.md — a sorted list of its wiki pages (deterministic)."""
from __future__ import annotations

from pathlib import Path


def rebuild_index(wiki_dir: Path, domain_name: str) -> None:
    stems = sorted(
        p.stem for p in wiki_dir.glob("*.md")
        if p.stem != "_index" and not p.stem.startswith("_")
    )
    lines = [f"# {domain_name} — index", ""]
    lines += [f"- [[{stem}]]" for stem in stems]
    (wiki_dir / "_index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
