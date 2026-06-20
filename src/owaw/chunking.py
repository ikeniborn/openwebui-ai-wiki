"""Section-aware chunking. Faithful port of obsidian-ai-wiki/src/page-similarity.ts.

Each wiki page yields one `summary` chunk (the annotation) plus one `section`
chunk per section window, with the annotation prepended to every section chunk.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ChunkingConfig:
    maxChars: int = 1200
    overlapChars: int = 200
    minChars: int = 200
    maxCount: int = 12


DEFAULT_CHUNKING = ChunkingConfig()


@dataclass(frozen=True)
class SectionWindow:
    heading: str
    window: str


@dataclass(frozen=True)
class ChunkInput:
    kind: str  # "summary" | "section"
    embed_text: str
    hash: str


_FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n?", re.DOTALL)
_H1_RE = re.compile(r"^#\s+[^\n]*\n?")
_H2_RE = re.compile(r"^##\s+")


def _strip_frontmatter_and_title(body: str) -> str:
    no_fm = _FRONTMATTER_RE.sub("", body, count=1).lstrip()
    return _H1_RE.sub("", no_fm, count=1)


@dataclass
class _RawUnit:
    heading: str
    body: str


def _to_units(text: str) -> list[_RawUnit]:
    units: list[_RawUnit] = []
    cur: _RawUnit | None = None
    for line in text.split("\n"):
        if _H2_RE.match(line):
            if cur is not None:
                units.append(cur)
            cur = _RawUnit(heading=line.strip(), body="")
        elif cur is None:
            cur = _RawUnit(heading="", body=line + "\n")
        else:
            cur.body += line + "\n"
    if cur is not None:
        units.append(cur)
    out: list[_RawUnit] = []
    for u in units:
        h, b = u.heading, u.body.strip()
        if len(h) > 0 or len(b) > 0:
            out.append(_RawUnit(heading=h, body=b))
    return out


def _unit_len(u: _RawUnit) -> int:
    return len(u.heading) + len(u.body)


def _merge_short(units: list[_RawUnit], min_chars: int) -> list[_RawUnit]:
    out: list[_RawUnit] = []
    for u in units:
        prev = out[-1] if out else None
        if (_unit_len(u) < min_chars and prev is not None
                and len(prev.heading) > 0 and _unit_len(prev) >= min_chars):
            prev.body = f"{prev.body}\n\n{u.heading} {u.body}".strip()
        else:
            out.append(_RawUnit(heading=u.heading, body=u.body))
    return out


def _window_unit(u: _RawUnit, max_chars: int, overlap_chars: int) -> list[SectionWindow]:
    text = u.body
    if len(text) <= max_chars:
        return [SectionWindow(heading=u.heading, window=text)]
    windows: list[SectionWindow] = []
    step = max(1, max_chars - overlap_chars)
    i = 0
    while i < len(text):
        windows.append(SectionWindow(heading=u.heading, window=text[i:i + max_chars]))
        if i + max_chars >= len(text):
            break
        i += step
    return windows


def split_sections(body: str, chunking: ChunkingConfig) -> list[SectionWindow]:
    stripped = _strip_frontmatter_and_title(body).strip()
    if not stripped:
        return []
    merged = _merge_short(_to_units(stripped), chunking.minChars)
    windows: list[SectionWindow] = []
    for u in merged:
        windows.extend(_window_unit(u, chunking.maxChars, chunking.overlapChars))
    if not windows:
        return []
    if len(windows) > chunking.maxCount:
        kept = windows[: chunking.maxCount - 1]
        folded_count = len(windows) - len(kept)
        folded_body = "\n\n".join(
            f"{w.heading} {w.window}" for w in windows[chunking.maxCount - 1:]
        )[: chunking.maxChars]
        kept.append(SectionWindow(heading=f"## (+{folded_count} sections folded)", window=folded_body))
        windows = kept
    return windows


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def build_chunk_inputs(
    annotation: str, body: str, chunking: ChunkingConfig = DEFAULT_CHUNKING
) -> list[ChunkInput]:
    inputs: list[ChunkInput] = [
        ChunkInput(kind="summary", embed_text=annotation, hash=_hash(annotation))
    ]
    for w in split_sections(body, chunking):
        embed_text = f"{annotation}\n\n{w.heading}\n{w.window}"
        inputs.append(ChunkInput(kind="section", embed_text=embed_text, hash=_hash(embed_text)))
    return inputs
