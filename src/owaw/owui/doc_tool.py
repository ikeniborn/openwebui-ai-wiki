"""
title: Wiki Docs
author: openwebui-ai-wiki
description: Read-only, jailed access to the AI wiki and its source files (list, read, search).
version: 0.1.0
required_open_webui_version: 0.5.0
requirements:
"""
# Self-contained OpenWebUI Tool. Only stdlib + pydantic — no owaw imports allowed;
# OpenWebUI stores this file and exec's it standalone (a test enforces this).
from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

DEFAULT_ROOTS = "/data/wiki,/data/sources"
TEXT_SUFFIXES = {
    ".md", ".markdown", ".txt", ".rst", ".yaml", ".yml", ".toml", ".ini",
    ".json", ".csv", ".cfg", ".conf", ".py", ".sh", ".go", ".js", ".ts",
}
DEFER_SUFFIXES = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}


def _roots(raw: str) -> list[Path]:
    return [Path(r.strip()).resolve() for r in raw.split(",") if r.strip()]


def _contained(real: Path, roots: list[Path]) -> bool:
    return any(real == root or root in real.parents for root in roots)


def _resolve_within(roots: list[Path], rel: str) -> Path:
    """Resolve `rel` (relative to each root, or absolute) to a realpath inside the roots.

    Raises ValueError if the resolved realpath escapes every configured root —
    this is the jail: `../` traversal, absolute escape, and symlink escape all fail.
    """
    candidate = Path(rel)
    bases = [candidate] if candidate.is_absolute() else [root / candidate for root in roots]
    for base in bases:
        real = base.resolve()
        if _contained(real, roots):
            return real
    raise ValueError(f"path escapes the configured roots: {rel}")


def _is_binary(data: bytes) -> bool:
    return b"\x00" in data


def _list_docs(roots: list[Path], rel: str = "") -> str:
    targets = [_resolve_within(roots, rel)] if rel else [r for r in roots if r.exists()]
    lines: list[str] = []
    for target in targets:
        if not target.exists():
            continue
        if target.is_file():
            lines.append(target.name)
            continue
        for child in sorted(target.iterdir()):
            lines.append(f"{child.name}/" if child.is_dir() else child.name)
    return "\n".join(lines) if lines else "(empty)"


def _read_doc(roots: list[Path], rel: str, max_bytes: int = 100_000) -> str:
    real = _resolve_within(roots, rel)
    if not real.exists() or not real.is_file():
        return f"not found: {rel}"
    if real.suffix.lower() in DEFER_SUFFIXES:
        return f"{real.suffix} document — not read directly; rely on RAG search instead: {rel}"
    data = real.read_bytes()
    if _is_binary(data[:8192]):
        return f"binary file — cannot display: {rel}"
    if len(data) > max_bytes:
        return data[:max_bytes].decode("utf-8", "replace") + f"\n\n[truncated at {max_bytes} bytes]"
    return data.decode("utf-8", "replace")


def _search_docs(roots: list[Path], query: str, max_results: int = 20,
                 max_bytes: int = 100_000) -> str:
    if not query.strip():
        return "(empty query)"
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    hits: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if len(hits) >= max_results:
                return "\n".join(hits)
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            try:
                data = path.read_bytes()
            except OSError:
                continue
            if len(data) > max_bytes or _is_binary(data[:8192]):
                continue
            for i, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
                if pattern.search(line):
                    hits.append(f"{path}:{i}: {line.strip()[:200]}")
                    if len(hits) >= max_results:
                        break
    return "\n".join(hits) if hits else f"no matches for: {query}"


class Tools:
    def __init__(self):
        self.valves = self.Valves()
        self.citation = True

    class Valves(BaseModel):
        roots: str = Field(DEFAULT_ROOTS, description="Comma-separated read-only roots")
        max_read_bytes: int = Field(100_000, description="Max bytes returned by read_doc")
        max_results: int = Field(20, description="Max lines returned by search_docs")

    async def list_docs(self, path: str = "", __user__: dict | None = None) -> str:
        """
        List files and folders inside the documentation roots.
        :param path: Relative path within the roots; empty lists the roots themselves
        """
        try:
            return _list_docs(_roots(self.valves.roots), path)
        except ValueError as e:
            return str(e)

    async def read_doc(self, path: str, __user__: dict | None = None) -> str:
        """
        Read a single text document from the documentation roots.
        :param path: Relative path to the file within the roots
        """
        try:
            return _read_doc(_roots(self.valves.roots), path, self.valves.max_read_bytes)
        except ValueError as e:
            return str(e)

    async def search_docs(self, query: str, __user__: dict | None = None) -> str:
        """
        Search the documentation for a literal string and return matching lines.
        :param query: Text to search for (case-insensitive, literal)
        """
        return _search_docs(_roots(self.valves.roots), query,
                            self.valves.max_results, self.valves.max_read_bytes)
