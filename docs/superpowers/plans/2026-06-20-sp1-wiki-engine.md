# SP1 — Wiki Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python service that turns configured document sources into a maintained, cross-linked wiki plus section-aware chunk records on disk, kept current automatically as sources change.

**Architecture:** A `owaw` Python package with a deterministic core (chunking, config, domains, manifest, chunk store, extraction) and an LLM-driven synthesis layer (entity extraction, page create/merge, index). A daemon watches sources via inotify and runs an incremental ingest pipeline; a CLI exposes `init`, `ingest`, `rebuild`, `domain`. Chunking is a faithful port of `obsidian-ai-wiki`'s `page-similarity.ts`. The engine stops at chunk records (`embed_text` + `hash`); embedding (bge-m3) and OpenWebUI wiring belong to SP2/SP3.

**Tech Stack:** Python 3.12, Typer (CLI), PyYAML (config), `openai` SDK (LiteLLM, OpenAI-compatible), Docling (PDF/Office extraction), watchdog (inotify), pytest (+ monkeypatch) for tests. Package/test via `pyproject.toml` (hatchling).

**Spec:** [`../specs/2026-06-20-sp1-wiki-engine-design.md`](../specs/2026-06-20-sp1-wiki-engine-design.md)

**Reference (read, do not import):** `../../../../obsidian-ai-wiki/` — `src/page-similarity.ts`, `src/phases/zod-schemas.ts`, `prompts/ingest-entities.md`, `prompts/ingest.md`, `src/domain.ts`.

---

## File structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | Package metadata, deps, pytest config |
| `src/owaw/__init__.py` | Package marker + version |
| `src/owaw/chunking.py` | Port of `page-similarity`: section split, windows, `build_chunk_inputs` |
| `src/owaw/paths.py` | Data-dir layout helpers |
| `src/owaw/config.py` | `config.yaml` → `Config` (generation, chunking, extraction, daemon) |
| `src/owaw/domains.py` | `EntityType`/`Domain` models, `domains.yaml` load/save/validate |
| `src/owaw/manifest.py` | Source-file hash state (`state/manifest.json`) |
| `src/owaw/chunkstore.py` | `chunks/<domain>.jsonl` write / replace-by-page / read |
| `src/owaw/extract.py` | Text extraction: Docling (PDF/Office) + passthrough |
| `src/owaw/frontmatter.py` | Parse/emit YAML frontmatter, entity slug |
| `src/owaw/llm.py` | OpenAI-compatible client + JSON-with-retry |
| `src/owaw/entities.py` | Entity extraction phase |
| `src/owaw/pages.py` | Page synthesis (create/merge) + page IO |
| `src/owaw/index.py` | Domain `_index.md` maintenance |
| `src/owaw/ingest.py` | Pipeline orchestration (extract→entities→pages→index→chunk→manifest) |
| `src/owaw/daemon.py` | watchdog inotify watcher + debounce |
| `src/owaw/cli.py` | Typer app: `init`, `ingest`, `rebuild`, `domain`, `watch` |
| `prompts/ingest_entities.md` | Ported entity-extraction prompt |
| `prompts/ingest_pages.md` | Ported page-synthesis prompt |
| `tests/...` | One test module per source module + one integration test |

---

## Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `src/owaw/__init__.py`
- Create: `tests/test_smoke.py`

- [ ] **Step 1: Write the failing test**

`tests/test_smoke.py`:
```python
import owaw


def test_version_is_exposed():
    assert isinstance(owaw.__version__, str)
    assert owaw.__version__
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "owaw"
version = "0.1.0"
description = "openwebui-ai-wiki: server-side AI wiki engine (SP1)"
requires-python = ">=3.12"
dependencies = [
    "typer>=0.12",
    "pyyaml>=6.0",
    "openai>=1.40",
    "docling>=2.0",
    "watchdog>=4.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
owaw = "owaw.cli:app"

[tool.hatch.build.targets.wheel]
packages = ["src/owaw"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 3: Create `src/owaw/__init__.py`**

```python
__version__ = "0.1.0"
```

- [ ] **Step 4: Install dev deps and run the test**

Run:
```bash
cd /home/ikeniborn/Documents/Project/openwebui-ai-wiki
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest tests/test_smoke.py -v
```
Expected: PASS (`test_version_is_exposed`).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/owaw/__init__.py tests/test_smoke.py
git commit -m "chore(sp1): project scaffold (package, pytest, smoke test)"
```

---

## Task 2: Chunking core (faithful port of `page-similarity.ts`)

This is the crown jewel — pure functions, no I/O. Port exactly. `obsidian-ai-wiki/src/page-similarity.ts` is the reference (`splitSections`, `buildChunkInputs`, `DEFAULT_CHUNKING`).

**Files:**
- Create: `src/owaw/chunking.py`
- Test: `tests/test_chunking.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_chunking.py`:
```python
from owaw.chunking import (
    ChunkingConfig, DEFAULT_CHUNKING, build_chunk_inputs, split_sections,
)


def test_defaults_match_reference():
    assert DEFAULT_CHUNKING == ChunkingConfig(
        maxChars=1200, overlapChars=200, minChars=200, maxCount=12
    )


def test_summary_chunk_is_first_and_is_the_annotation():
    out = build_chunk_inputs("ANNOT", "# Title\n\n## A\nbody a", DEFAULT_CHUNKING)
    assert out[0].kind == "summary"
    assert out[0].embed_text == "ANNOT"


def test_section_chunk_prepends_annotation_and_heading():
    out = build_chunk_inputs("ANNOT", "# Title\n\n## A\nbody a", DEFAULT_CHUNKING)
    sections = [c for c in out if c.kind == "section"]
    assert len(sections) == 1
    assert sections[0].embed_text == "ANNOT\n\n## A\nbody a"


def test_h3_stays_inside_h2_unit():
    body = "## A\nalpha\n### A1\nbeta\n## B\ngamma"
    wins = split_sections(body, DEFAULT_CHUNKING)
    headings = [w.heading for w in wins]
    assert headings == ["## A", "## B"]
    assert "### A1" in wins[0].window and "beta" in wins[0].window


def test_lead_text_before_first_h2_is_headless_unit():
    body = "intro line\n\n## A\nbody"
    wins = split_sections(body, DEFAULT_CHUNKING)
    assert wins[0].heading == ""
    assert "intro line" in wins[0].window


def test_short_section_merges_into_previous_long_headed_unit():
    long_a = "## A\n" + ("x" * 250)
    short_b = "## B\nshort"
    wins = split_sections(f"{long_a}\n{short_b}", ChunkingConfig(1200, 200, 200, 12))
    assert len(wins) == 1
    assert "## B short" in wins[0].window


def test_two_short_sections_do_not_collapse():
    wins = split_sections("## A\naa\n## B\nbb", ChunkingConfig(1200, 200, 200, 12))
    assert [w.heading for w in wins] == ["## A", "## B"]


def test_intra_section_overlap_windows():
    body = "## A\n" + ("abcde" * 600)  # 3000 chars > maxChars
    cfg = ChunkingConfig(maxChars=1200, overlapChars=200, minChars=200, maxCount=12)
    wins = split_sections(body, cfg)
    assert len(wins) >= 3
    # step = maxChars - overlapChars = 1000; consecutive windows overlap by 200
    assert wins[0].window[-200:] == wins[1].window[:200]


def test_fold_past_max_count():
    body = "\n".join(f"## H{i}\n" + ("y" * 300) for i in range(20))
    cfg = ChunkingConfig(maxChars=1200, overlapChars=200, minChars=200, maxCount=12)
    wins = split_sections(body, cfg)
    assert len(wins) == 12
    assert wins[-1].heading.startswith("## (+")


def test_frontmatter_and_h1_stripped():
    body = "---\nkey: val\n---\n# Title\n\n## A\nbody"
    wins = split_sections(body, DEFAULT_CHUNKING)
    assert all("key: val" not in w.window for w in wins)
    assert all("# Title" not in w.window for w in wins)


def test_hash_is_stable_and_content_addressed():
    a = build_chunk_inputs("S", "## A\nb", DEFAULT_CHUNKING)
    b = build_chunk_inputs("S", "## A\nb", DEFAULT_CHUNKING)
    assert [c.hash for c in a] == [c.hash for c in b]
    c = build_chunk_inputs("S", "## A\nDIFFERENT", DEFAULT_CHUNKING)
    assert c[1].hash != a[1].hash
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_chunking.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'owaw.chunking'`.

- [ ] **Step 3: Implement `src/owaw/chunking.py`**

```python
"""Section-aware chunking. Faithful port of obsidian-ai-wiki/src/page-similarity.ts.

Each wiki page yields one `summary` chunk (the annotation) plus one `section`
chunk per section window, with the annotation prepended to every section chunk.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field


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
        if _H2_RE.match(line):                 # new H2 — H3+ stays inside the current unit
            if cur is not None:
                units.append(cur)
            cur = _RawUnit(heading=line.strip(), body="")
        elif cur is None:                      # lead text before the first H2 — headless unit
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_chunking.py -v`
Expected: PASS (all chunking tests).

- [ ] **Step 5: Commit**

```bash
git add src/owaw/chunking.py tests/test_chunking.py
git commit -m "feat(sp1): chunking core — faithful port of page-similarity"
```

---

## Task 3: Data-dir layout helpers

**Files:**
- Create: `src/owaw/paths.py`
- Test: `tests/test_paths.py`

- [ ] **Step 1: Write the failing test**

`tests/test_paths.py`:
```python
from pathlib import Path
from owaw import paths


def test_data_dir_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("OWAW_DATA_DIR", str(tmp_path))
    assert paths.data_dir() == tmp_path


def test_layout_helpers(monkeypatch, tmp_path):
    monkeypatch.setenv("OWAW_DATA_DIR", str(tmp_path))
    assert paths.domains_path() == tmp_path / "domains.yaml"
    assert paths.config_path() == tmp_path / "config.yaml"
    assert paths.wiki_dir("infra") == tmp_path / "wiki" / "infra"
    assert paths.chunks_path("infra") == tmp_path / "chunks" / "infra.jsonl"
    assert paths.manifest_path() == tmp_path / "state" / "manifest.json"


def test_ensure_dirs_creates_tree(monkeypatch, tmp_path):
    monkeypatch.setenv("OWAW_DATA_DIR", str(tmp_path))
    paths.ensure_dirs("infra")
    assert (tmp_path / "wiki" / "infra").is_dir()
    assert (tmp_path / "chunks").is_dir()
    assert (tmp_path / "state").is_dir()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_paths.py -v`
Expected: FAIL (`No module named 'owaw.paths'`).

- [ ] **Step 3: Implement `src/owaw/paths.py`**

```python
"""Resolve the on-disk data layout. Root is $OWAW_DATA_DIR (default ./data)."""
from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("OWAW_DATA_DIR", "data"))


def domains_path() -> Path:
    return data_dir() / "domains.yaml"


def config_path() -> Path:
    return data_dir() / "config.yaml"


def wiki_dir(domain: str) -> Path:
    return data_dir() / "wiki" / domain


def chunks_path(domain: str) -> Path:
    return data_dir() / "chunks" / f"{domain}.jsonl"


def manifest_path() -> Path:
    return data_dir() / "state" / "manifest.json"


def ensure_dirs(domain: str) -> None:
    wiki_dir(domain).mkdir(parents=True, exist_ok=True)
    (data_dir() / "chunks").mkdir(parents=True, exist_ok=True)
    (data_dir() / "state").mkdir(parents=True, exist_ok=True)
    (data_dir() / "logs").mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_paths.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/owaw/paths.py tests/test_paths.py
git commit -m "feat(sp1): data-dir layout helpers"
```

---

## Task 4: Config loader

**Files:**
- Create: `src/owaw/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:
```python
from owaw.config import load_config
from owaw.chunking import ChunkingConfig


def test_load_config_full(tmp_path):
    (tmp_path / "config.yaml").write_text(
        "generation:\n"
        "  model: claude-sonnet-cloud\n"
        "  base_url: http://host.docker.internal:4000/v1\n"
        "  api_key_env: LITELLM_KEY\n"
        "chunking:\n"
        "  maxChars: 1000\n"
        "  minChars: 150\n"
        "  overlapChars: 150\n"
        "  maxCount: 10\n"
        "extraction:\n"
        "  engine: docling\n"
        "daemon:\n"
        "  debounce_ms: 1500\n",
        encoding="utf-8",
    )
    cfg = load_config(tmp_path / "config.yaml")
    assert cfg.generation.model == "claude-sonnet-cloud"
    assert cfg.generation.api_key_env == "LITELLM_KEY"
    assert cfg.chunking == ChunkingConfig(maxChars=1000, overlapChars=150, minChars=150, maxCount=10)
    assert cfg.extraction_engine == "docling"
    assert cfg.debounce_ms == 1500


def test_load_config_applies_defaults(tmp_path):
    (tmp_path / "config.yaml").write_text(
        "generation:\n  model: m\n  base_url: u\n", encoding="utf-8"
    )
    cfg = load_config(tmp_path / "config.yaml")
    assert cfg.chunking == ChunkingConfig()  # defaults
    assert cfg.extraction_engine == "docling"
    assert cfg.debounce_ms == 1000
    assert cfg.generation.api_key_env == "OWAW_LLM_KEY"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL (`No module named 'owaw.config'`).

- [ ] **Step 3: Implement `src/owaw/config.py`**

```python
"""Load config.yaml into a typed Config. Secrets come from env, never the file."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from owaw.chunking import ChunkingConfig


@dataclass(frozen=True)
class GenerationConfig:
    model: str
    base_url: str
    api_key_env: str = "OWAW_LLM_KEY"


@dataclass(frozen=True)
class Config:
    generation: GenerationConfig
    chunking: ChunkingConfig
    extraction_engine: str
    debounce_ms: int


def load_config(path: Path) -> Config:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    gen = raw.get("generation") or {}
    generation = GenerationConfig(
        model=gen["model"],
        base_url=gen["base_url"],
        api_key_env=gen.get("api_key_env", "OWAW_LLM_KEY"),
    )
    ck = raw.get("chunking") or {}
    defaults = ChunkingConfig()
    chunking = ChunkingConfig(
        maxChars=ck.get("maxChars", defaults.maxChars),
        overlapChars=ck.get("overlapChars", defaults.overlapChars),
        minChars=ck.get("minChars", defaults.minChars),
        maxCount=ck.get("maxCount", defaults.maxCount),
    )
    extraction_engine = (raw.get("extraction") or {}).get("engine", "docling")
    debounce_ms = (raw.get("daemon") or {}).get("debounce_ms", 1000)
    return Config(
        generation=generation,
        chunking=chunking,
        extraction_engine=extraction_engine,
        debounce_ms=debounce_ms,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/owaw/config.py tests/test_config.py
git commit -m "feat(sp1): typed config loader"
```

---

## Task 5: Domain model + `domains.yaml`

Ported from `obsidian-ai-wiki/src/domain.ts` (`DomainEntry`, `EntityType`).

**Files:**
- Create: `src/owaw/domains.py`
- Test: `tests/test_domains.py`

- [ ] **Step 1: Write the failing test**

`tests/test_domains.py`:
```python
import pytest
from owaw.domains import (
    Domain, EntityType, validate_domain_id, load_domains, save_domains, add_domain,
)


def test_validate_domain_id():
    assert validate_domain_id("infra-1") is None
    assert validate_domain_id("") is not None
    assert validate_domain_id("bad id") is not None


def test_roundtrip_save_load(tmp_path):
    d = Domain(
        id="infra", name="Infra", wiki_folder="infra",
        source_paths=["/data/sources/a"],
        entity_types=[EntityType(type="service", description="a daemon",
                                 extraction_cues=["unit", "port"], min_mentions_for_page=2,
                                 wiki_subfolder="services")],
        language_notes="Russian corpus.",
    )
    p = tmp_path / "domains.yaml"
    save_domains([d], p)
    loaded = load_domains(p)
    assert loaded == [d]


def test_load_missing_returns_empty(tmp_path):
    assert load_domains(tmp_path / "nope.yaml") == []


def test_add_domain_rejects_duplicate(tmp_path):
    p = tmp_path / "domains.yaml"
    d = Domain(id="infra", name="Infra", wiki_folder="infra", source_paths=[], entity_types=[])
    add_domain(d, p)
    with pytest.raises(ValueError, match="exists"):
        add_domain(d, p)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_domains.py -v`
Expected: FAIL (`No module named 'owaw.domains'`).

- [ ] **Step 3: Implement `src/owaw/domains.py`**

```python
"""Domain model + domains.yaml persistence. Ported from src/domain.ts."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_domains.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/owaw/domains.py tests/test_domains.py
git commit -m "feat(sp1): domain model + domains.yaml persistence"
```

---

## Task 6: Manifest (source-hash state)

**Files:**
- Create: `src/owaw/manifest.py`
- Test: `tests/test_manifest.py`

- [ ] **Step 1: Write the failing test**

`tests/test_manifest.py`:
```python
from owaw.manifest import Manifest


def test_new_file_is_changed(tmp_path):
    src = tmp_path / "a.md"
    src.write_text("hello", encoding="utf-8")
    m = Manifest.load(tmp_path / "manifest.json")
    assert m.is_changed(src) is True


def test_marked_file_is_not_changed(tmp_path):
    src = tmp_path / "a.md"
    src.write_text("hello", encoding="utf-8")
    m = Manifest.load(tmp_path / "manifest.json")
    m.mark(src)
    assert m.is_changed(src) is False


def test_edited_file_is_changed_again(tmp_path):
    src = tmp_path / "a.md"
    src.write_text("hello", encoding="utf-8")
    m = Manifest.load(tmp_path / "manifest.json")
    m.mark(src)
    src.write_text("world", encoding="utf-8")
    assert m.is_changed(src) is True


def test_persisted_across_reload(tmp_path):
    src = tmp_path / "a.md"
    src.write_text("hello", encoding="utf-8")
    mpath = tmp_path / "manifest.json"
    m = Manifest.load(mpath)
    m.mark(src)
    m.save()
    m2 = Manifest.load(mpath)
    assert m2.is_changed(src) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_manifest.py -v`
Expected: FAIL (`No module named 'owaw.manifest'`).

- [ ] **Step 3: Implement `src/owaw/manifest.py`**

```python
"""Track processed source files by content hash for idempotent ingest."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Manifest:
    def __init__(self, path: Path, hashes: dict[str, str]):
        self._path = path
        self._hashes = hashes

    @classmethod
    def load(cls, path: Path) -> "Manifest":
        hashes: dict[str, str] = {}
        if path.exists():
            hashes = json.loads(path.read_text(encoding="utf-8"))
        return cls(path, hashes)

    def is_changed(self, src: Path) -> bool:
        return self._hashes.get(str(src)) != _hash_file(src)

    def mark(self, src: Path) -> None:
        self._hashes[str(src)] = _hash_file(src)

    def forget(self, src: Path) -> None:
        self._hashes.pop(str(src), None)

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._hashes, indent=2), encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_manifest.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/owaw/manifest.py tests/test_manifest.py
git commit -m "feat(sp1): source-hash manifest for idempotent ingest"
```

---

## Task 7: Chunk store (JSONL, replace-by-page)

**Files:**
- Create: `src/owaw/chunkstore.py`
- Test: `tests/test_chunkstore.py`

- [ ] **Step 1: Write the failing test**

`tests/test_chunkstore.py`:
```python
from owaw.chunkstore import ChunkStore
from owaw.chunking import ChunkInput


def _chunks(tag):
    return [
        ChunkInput(kind="summary", embed_text=f"{tag}-s", hash=f"{tag}h0"),
        ChunkInput(kind="section", embed_text=f"{tag}-a", hash=f"{tag}h1"),
    ]


def test_replace_page_writes_records(tmp_path):
    store = ChunkStore(tmp_path / "infra.jsonl", domain="infra")
    store.replace_page("wiki_infra_a", _chunks("a"))
    rows = store.read_all()
    assert len(rows) == 2
    assert {r["page_id"] for r in rows} == {"wiki_infra_a"}
    assert rows[0]["domain"] == "infra"
    assert {r["kind"] for r in rows} == {"summary", "section"}


def test_replace_page_is_idempotent(tmp_path):
    store = ChunkStore(tmp_path / "infra.jsonl", domain="infra")
    store.replace_page("wiki_infra_a", _chunks("a"))
    store.replace_page("wiki_infra_a", _chunks("a2"))
    rows = store.read_all()
    assert len(rows) == 2
    assert {r["embed_text"] for r in rows} == {"a2-s", "a2-a"}


def test_replace_one_page_keeps_others(tmp_path):
    store = ChunkStore(tmp_path / "infra.jsonl", domain="infra")
    store.replace_page("wiki_infra_a", _chunks("a"))
    store.replace_page("wiki_infra_b", _chunks("b"))
    store.replace_page("wiki_infra_a", _chunks("a3"))
    rows = store.read_all()
    assert {r["page_id"] for r in rows} == {"wiki_infra_a", "wiki_infra_b"}
    assert len(rows) == 4


def test_delete_page(tmp_path):
    store = ChunkStore(tmp_path / "infra.jsonl", domain="infra")
    store.replace_page("wiki_infra_a", _chunks("a"))
    store.replace_page("wiki_infra_b", _chunks("b"))
    store.delete_page("wiki_infra_a")
    assert {r["page_id"] for r in store.read_all()} == {"wiki_infra_b"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_chunkstore.py -v`
Expected: FAIL (`No module named 'owaw.chunkstore'`).

- [ ] **Step 3: Implement `src/owaw/chunkstore.py`**

```python
"""JSONL chunk store. One record per line; replace/delete are filtered rewrites.

Record shape: {page_id, domain, kind, embed_text, hash}. Embedding-model-agnostic
— SP2 reads embed_text and produces vectors.
"""
from __future__ import annotations

import json
from pathlib import Path

from owaw.chunking import ChunkInput


class ChunkStore:
    def __init__(self, path: Path, domain: str):
        self._path = path
        self._domain = domain

    def read_all(self) -> list[dict]:
        if not self._path.exists():
            return []
        return [
            json.loads(line)
            for line in self._path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def _rewrite(self, rows: list[dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
        )

    def replace_page(self, page_id: str, chunks: list[ChunkInput]) -> None:
        rows = [r for r in self.read_all() if r["page_id"] != page_id]
        for c in chunks:
            rows.append({
                "page_id": page_id,
                "domain": self._domain,
                "kind": c.kind,
                "embed_text": c.embed_text,
                "hash": c.hash,
            })
        self._rewrite(rows)

    def delete_page(self, page_id: str) -> None:
        self._rewrite([r for r in self.read_all() if r["page_id"] != page_id])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_chunkstore.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/owaw/chunkstore.py tests/test_chunkstore.py
git commit -m "feat(sp1): jsonl chunk store with replace-by-page"
```

---

## Task 8: Text extraction (Docling + passthrough)

**Files:**
- Create: `src/owaw/extract.py`
- Test: `tests/test_extract.py`

- [ ] **Step 1: Write the failing test**

`tests/test_extract.py`:
```python
import pytest
from owaw import extract


def test_passthrough_text_extensions(tmp_path):
    for name, text in [("a.md", "# Md"), ("b.txt", "plain"), ("c.py", "x = 1")]:
        p = tmp_path / name
        p.write_text(text, encoding="utf-8")
        assert extract.extract_text(p) == text


def test_pdf_routes_to_docling(tmp_path, monkeypatch):
    called = {}

    def fake_docling(path):
        called["path"] = path
        return "EXTRACTED PDF"

    monkeypatch.setattr(extract, "_docling_to_markdown", fake_docling)
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    assert extract.extract_text(pdf) == "EXTRACTED PDF"
    assert called["path"] == pdf


def test_unknown_binary_raises(tmp_path):
    p = tmp_path / "img.png"
    p.write_bytes(b"\x89PNG")
    with pytest.raises(extract.UnsupportedFormat):
        extract.extract_text(p)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_extract.py -v`
Expected: FAIL (`No module named 'owaw.extract'`).

- [ ] **Step 3: Implement `src/owaw/extract.py`**

```python
"""Extract plain text/markdown from a source file.

Text-like formats pass through; PDF/Office go through Docling. Docling is imported
lazily so the deterministic core has no hard dependency on it during unit tests.
"""
from __future__ import annotations

from pathlib import Path

TEXT_EXTS = {".md", ".markdown", ".txt", ".rst", ".py", ".js", ".ts", ".go",
             ".rs", ".c", ".h", ".java", ".sh", ".yaml", ".yml", ".toml", ".json"}
DOC_EXTS = {".pdf", ".docx", ".pptx", ".xlsx", ".html", ".htm"}


class UnsupportedFormat(Exception):
    pass


def _docling_to_markdown(path: Path) -> str:
    from docling.document_converter import DocumentConverter  # lazy import

    converter = DocumentConverter()
    result = converter.convert(str(path))
    return result.document.export_to_markdown()


def extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in TEXT_EXTS:
        return path.read_text(encoding="utf-8")
    if ext in DOC_EXTS:
        return _docling_to_markdown(path)
    raise UnsupportedFormat(f"unsupported extension: {ext}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_extract.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/owaw/extract.py tests/test_extract.py
git commit -m "feat(sp1): text extraction (docling + passthrough)"
```

---

## Task 9: Frontmatter + entity slug helpers

**Files:**
- Create: `src/owaw/frontmatter.py`
- Test: `tests/test_frontmatter.py`

- [ ] **Step 1: Write the failing test**

`tests/test_frontmatter.py`:
```python
from owaw.frontmatter import split_frontmatter, entity_slug, page_stem


def test_split_frontmatter_present():
    doc = "---\nwiki_status: stub\n---\n# Title\n\nbody"
    fm, body = split_frontmatter(doc)
    assert fm["wiki_status"] == "stub"
    assert body == "# Title\n\nbody"


def test_split_frontmatter_absent():
    fm, body = split_frontmatter("# Title\n\nbody")
    assert fm == {}
    assert body == "# Title\n\nbody"


def test_entity_slug_ascii_snake():
    assert entity_slug("Neural Networks") == "neural_networks"
    assert entity_slug("host.docker.internal") == "host_docker_internal"
    assert entity_slug("CPU/GPU split") == "cpu_gpu_split"


def test_page_stem():
    assert page_stem("infra", "Neural Networks") == "wiki_infra_neural_networks"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_frontmatter.py -v`
Expected: FAIL (`No module named 'owaw.frontmatter'`).

- [ ] **Step 3: Implement `src/owaw/frontmatter.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_frontmatter.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/owaw/frontmatter.py tests/test_frontmatter.py
git commit -m "feat(sp1): frontmatter split + entity slug helpers"
```

---

## Task 10: LLM client + JSON-with-retry

Wraps the OpenAI SDK against LiteLLM and guarantees a parsed JSON object (port of the
`parse-with-retry` idea: re-ask once on malformed JSON).

**Files:**
- Create: `src/owaw/llm.py`
- Test: `tests/test_llm.py`

- [ ] **Step 1: Write the failing test**

`tests/test_llm.py`:
```python
import json
import pytest
from owaw.llm import LLM


class FakeClient:
    """Stub matching the openai client surface we use."""
    def __init__(self, replies):
        self._replies = list(replies)
        self.calls = []

        class _Completions:
            def __init__(self, outer):
                self._outer = outer

            def create(self, **kwargs):
                self._outer.calls.append(kwargs)
                content = self._outer._replies.pop(0)
                return type("R", (), {"choices": [
                    type("C", (), {"message": type("M", (), {"content": content})()})()
                ]})()

        class _Chat:
            def __init__(self, outer):
                self.completions = _Completions(outer)

        self.chat = _Chat(self)


def test_chat_json_parses_object():
    fake = FakeClient(['{"reasoning":"r","entities":[]}'])
    llm = LLM(client=fake, model="m")
    assert llm.chat_json("prompt") == {"reasoning": "r", "entities": []}


def test_chat_json_strips_code_fence():
    fake = FakeClient(['```json\n{"ok":true}\n```'])
    llm = LLM(client=fake, model="m")
    assert llm.chat_json("prompt") == {"ok": True}


def test_chat_json_retries_once_on_garbage():
    fake = FakeClient(["not json at all", '{"ok":true}'])
    llm = LLM(client=fake, model="m")
    assert llm.chat_json("prompt") == {"ok": True}
    assert len(fake.calls) == 2


def test_chat_json_raises_after_retry():
    fake = FakeClient(["garbage", "still garbage"])
    llm = LLM(client=fake, model="m")
    with pytest.raises(ValueError, match="invalid JSON"):
        llm.chat_json("prompt")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_llm.py -v`
Expected: FAIL (`No module named 'owaw.llm'`).

- [ ] **Step 3: Implement `src/owaw/llm.py`**

```python
"""LLM client over LiteLLM (OpenAI-compatible) with JSON-object guarantee."""
from __future__ import annotations

import json
import os
import re

from owaw.config import GenerationConfig

_FENCE_RE = re.compile(r"^```[a-zA-Z]*\n(.*)\n```$", re.DOTALL)


def _extract_json(text: str) -> dict:
    s = text.strip()
    m = _FENCE_RE.match(s)
    if m:
        s = m.group(1).strip()
    return json.loads(s)


class LLM:
    def __init__(self, client, model: str):
        self._client = client
        self._model = model

    @classmethod
    def from_config(cls, gen: GenerationConfig) -> "LLM":
        from openai import OpenAI  # lazy import

        api_key = os.environ.get(gen.api_key_env, "")
        client = OpenAI(base_url=gen.base_url, api_key=api_key)
        return cls(client=client, model=gen.model)

    def _complete(self, prompt: str) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        return resp.choices[0].message.content or ""

    def chat_json(self, prompt: str) -> dict:
        text = self._complete(prompt)
        try:
            return _extract_json(text)
        except (json.JSONDecodeError, ValueError):
            repair = (
                prompt
                + "\n\nYour previous answer was not valid JSON. "
                + "Reply with ONLY a single valid JSON object, no prose, no code fence."
            )
            text = self._complete(repair)
            try:
                return _extract_json(text)
            except (json.JSONDecodeError, ValueError) as e:
                raise ValueError(f"LLM returned invalid JSON after retry: {e}") from e
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_llm.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/owaw/llm.py tests/test_llm.py
git commit -m "feat(sp1): llm client with json-retry over litellm"
```

---

## Task 11: Entity extraction phase

Ported from `prompts/ingest-entities.md` + `EntitiesOutputSchema`.

**Files:**
- Create: `prompts/ingest_entities.md`
- Create: `src/owaw/entities.py`
- Test: `tests/test_entities.py`

- [ ] **Step 1: Create the prompt `prompts/ingest_entities.md`**

```text
You are an entity extractor from a source for the domain "{domain_name}".

DOMAIN ENTITY TYPES:
{entity_types_block}
{lang_notes}

TASK:
- Read the source.
- Return all entities worthy of a separate wiki page:
  - If an entity matches a type above, specify its type.
  - If it matches no type but the concept is significant, return it without a type.
  - Do not return an empty list if the source contains significant concepts.
- For each entity:
  - name: the canonical entity name (no quotes), like a future page heading
  - type: a type from the list above (optional)
  - context_snippet: one phrase from the source explaining why the entity matters (optional)

Do not duplicate: one name -> one record. Do not extract entities whose type has
min_mentions_for_page > 1 if they are mentioned only once.

SOURCE:
{source_text}

Return ONLY one JSON object:
{{"reasoning":"...","entities":[{{"name":"...","type":"...","context_snippet":"..."}}]}}
```

- [ ] **Step 2: Write the failing test**

`tests/test_entities.py`:
```python
from owaw.entities import extract_entities, Entity
from owaw.domains import Domain, EntityType


class StubLLM:
    def __init__(self, obj):
        self._obj = obj
        self.prompt = None

    def chat_json(self, prompt):
        self.prompt = prompt
        return self._obj


def _domain():
    return Domain(
        id="infra", name="Infra", wiki_folder="infra", source_paths=[],
        entity_types=[EntityType(type="service", description="a daemon",
                                 extraction_cues=["unit"], min_mentions_for_page=1)],
        language_notes="Russian corpus.",
    )


def test_extract_entities_parses_records():
    llm = StubLLM({"reasoning": "r", "entities": [
        {"name": "Traefik", "type": "service", "context_snippet": "reverse proxy"},
        {"name": "Loki"},
    ]})
    ents = extract_entities(llm, _domain(), "source body")
    assert ents == [
        Entity(name="Traefik", type="service", context_snippet="reverse proxy"),
        Entity(name="Loki", type=None, context_snippet=None),
    ]


def test_prompt_includes_domain_and_source():
    llm = StubLLM({"reasoning": "r", "entities": []})
    extract_entities(llm, _domain(), "THE SOURCE TEXT")
    assert "Infra" in llm.prompt
    assert "service" in llm.prompt
    assert "THE SOURCE TEXT" in llm.prompt
    assert "Russian corpus." in llm.prompt


def test_empty_entities_yields_empty_list():
    llm = StubLLM({"reasoning": "r", "entities": []})
    assert extract_entities(llm, _domain(), "x") == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_entities.py -v`
Expected: FAIL (`No module named 'owaw.entities'`).

- [ ] **Step 4: Implement `src/owaw/entities.py`**

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_entities.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add prompts/ingest_entities.md src/owaw/entities.py tests/test_entities.py
git commit -m "feat(sp1): entity extraction phase"
```

---

## Task 12: Page synthesis (create/merge) + page IO

Ported from `prompts/ingest.md` + `WikiPagesOutputSchema`. The LLM receives the source,
the extracted entities, and any existing pages for those entities, and returns full page
contents (create or merge — never drop existing facts) plus a per-page `annotation`.

**Files:**
- Create: `prompts/ingest_pages.md`
- Create: `src/owaw/pages.py`
- Test: `tests/test_pages.py`

- [ ] **Step 1: Create the prompt `prompts/ingest_pages.md`**

```text
You are a wiki-knowledge synthesis assistant for the domain "{domain_name}".
Create or update wiki pages from the source. Synthesis, not copying.

DOMAIN ENTITY TYPES:
{entity_types_block}
{lang_notes}

RULES:
- CREATE: entity has no existing page -> write a new page.
- UPDATE: entity has an existing page -> add new information, do NOT remove old facts.
- The page file stem (without .md) MUST be exactly: wiki_{domain_id}_<entity_slug>,
  where <entity_slug> is the ASCII entity name in lowercase snake_case ([a-z0-9_] only).
- Frontmatter is mandatory and must include:
    wiki_sources: ["[[{source_stem}]]"]
    wiki_updated: {today}
    wiki_status: stub|developing|mature
    tags: []
    wiki_outgoing_links: []
  wiki_sources lists ONLY source files (bare name in [[...]], double-quoted).
  wiki_outgoing_links lists ONLY other wiki pages by stem (never source files).
- In page bodies use ONLY [[stem]] wiki links — never [[stem|alias]].
- For each page add an "annotation" field in the JSON (NOT in frontmatter): a single-line,
  ~600-800 char description covering ALL body sections, listing entities/terms/IDs for search.

EXTRACTED ENTITIES (this source):
{entities_block}

EXISTING PAGES (merge into these where the stem matches):
{existing_pages_block}

SOURCE ("{source_stem}"):
{source_text}

Return ONLY one JSON object:
{{"reasoning":"...","pages":[{{"path":"<stem>.md","content":"---\\n...frontmatter...\\n---\\n# Name\\n\\nbody","annotation":"..."}}]}}
```

- [ ] **Step 2: Write the failing test**

`tests/test_pages.py`:
```python
from pathlib import Path
from owaw.pages import synthesize_pages, write_page, read_existing_pages, WikiPage
from owaw.domains import Domain, EntityType
from owaw.entities import Entity


class StubLLM:
    def __init__(self, obj):
        self._obj = obj
        self.prompt = None

    def chat_json(self, prompt):
        self.prompt = prompt
        return self._obj


def _domain():
    return Domain(id="infra", name="Infra", wiki_folder="infra", source_paths=[],
                  entity_types=[EntityType(type="service", description="d", extraction_cues=[])])


def test_synthesize_returns_pages():
    llm = StubLLM({"reasoning": "r", "pages": [
        {"path": "wiki_infra_traefik.md",
         "content": "---\nwiki_status: stub\n---\n# Traefik\n\n## Role\nproxy",
         "annotation": "Traefik reverse proxy. Terms: ingress, tls."},
    ]})
    pages = synthesize_pages(llm, _domain(), "src body", "minipc-docs",
                             [Entity(name="Traefik", type="service")], existing_pages=[])
    assert pages == [WikiPage(
        path="wiki_infra_traefik.md",
        content="---\nwiki_status: stub\n---\n# Traefik\n\n## Role\nproxy",
        annotation="Traefik reverse proxy. Terms: ingress, tls.",
    )]


def test_prompt_includes_entities_and_existing(tmp_path):
    llm = StubLLM({"reasoning": "r", "pages": []})
    synthesize_pages(llm, _domain(), "src", "minipc-docs",
                     [Entity(name="Traefik")], existing_pages=[
                         WikiPage(path="wiki_infra_traefik.md", content="old", annotation="a")])
    assert "Traefik" in llm.prompt
    assert "old" in llm.prompt
    assert "minipc-docs" in llm.prompt


def test_write_and_read_page_roundtrip(tmp_path):
    page = WikiPage(path="wiki_infra_traefik.md",
                    content="---\nwiki_status: stub\n---\n# Traefik\n\nbody", annotation="a")
    write_page(tmp_path, page)
    on_disk = (tmp_path / "wiki_infra_traefik.md").read_text(encoding="utf-8")
    assert on_disk == page.content
    existing = read_existing_pages(tmp_path, ["wiki_infra_traefik", "wiki_infra_absent"])
    assert len(existing) == 1
    assert existing[0].path == "wiki_infra_traefik.md"
    assert existing[0].content == page.content
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_pages.py -v`
Expected: FAIL (`No module named 'owaw.pages'`).

- [ ] **Step 4: Implement `src/owaw/pages.py`**

```python
"""Page synthesis (create/merge) + page IO. Prompt: prompts/ingest_pages.md."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from owaw.domains import Domain
from owaw.entities import Entity, entity_types_block

_PROMPT = (Path(__file__).resolve().parents[2] / "prompts" / "ingest_pages.md").read_text(
    encoding="utf-8"
)


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
    target = wiki_dir / page.path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(page.content, encoding="utf-8")


def read_existing_pages(wiki_dir: Path, stems: list[str]) -> list[WikiPage]:
    out: list[WikiPage] = []
    for stem in stems:
        f = wiki_dir / f"{stem}.md"
        if f.exists():
            out.append(WikiPage(path=f"{stem}.md", content=f.read_text(encoding="utf-8"), annotation=""))
    return out
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_pages.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add prompts/ingest_pages.md src/owaw/pages.py tests/test_pages.py
git commit -m "feat(sp1): page synthesis (create/merge) + page io"
```

---

## Task 13: Domain index maintenance

Maintains `_index.md` — a generated list of the domain's pages. Deterministic (no LLM):
rebuilt from the wiki directory contents.

**Files:**
- Create: `src/owaw/index.py`
- Test: `tests/test_index.py`

- [ ] **Step 1: Write the failing test**

`tests/test_index.py`:
```python
from owaw.index import rebuild_index


def test_index_lists_pages_sorted(tmp_path):
    (tmp_path / "wiki_infra_b.md").write_text("# B", encoding="utf-8")
    (tmp_path / "wiki_infra_a.md").write_text("# A", encoding="utf-8")
    rebuild_index(tmp_path, domain_name="Infra")
    text = (tmp_path / "_index.md").read_text(encoding="utf-8")
    assert "# Infra — index" in text
    assert text.index("[[wiki_infra_a]]") < text.index("[[wiki_infra_b]]")


def test_index_excludes_itself(tmp_path):
    (tmp_path / "wiki_infra_a.md").write_text("# A", encoding="utf-8")
    rebuild_index(tmp_path, domain_name="Infra")
    rebuild_index(tmp_path, domain_name="Infra")  # idempotent, never lists _index
    text = (tmp_path / "_index.md").read_text(encoding="utf-8")
    assert "[[_index]]" not in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_index.py -v`
Expected: FAIL (`No module named 'owaw.index'`).

- [ ] **Step 3: Implement `src/owaw/index.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_index.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/owaw/index.py tests/test_index.py
git commit -m "feat(sp1): deterministic domain index maintenance"
```

---

## Task 14: Ingest orchestration

Wires the pipeline for one source file: extract → entities → synthesize pages → write →
rebuild index → re-chunk → mark manifest. Skips unchanged files.

**Files:**
- Create: `src/owaw/ingest.py`
- Test: `tests/test_ingest.py`

- [ ] **Step 1: Write the failing test**

`tests/test_ingest.py`:
```python
from pathlib import Path
import owaw.ingest as ingest_mod
from owaw.ingest import ingest_file
from owaw.domains import Domain, EntityType
from owaw.entities import Entity
from owaw.pages import WikiPage
from owaw.manifest import Manifest
from owaw.chunkstore import ChunkStore


class StubLLM:
    def chat_json(self, prompt):  # not used — phases are monkeypatched
        raise AssertionError("LLM should be stubbed at phase level")


def _domain(src_dir):
    return Domain(id="infra", name="Infra", wiki_folder="infra",
                  source_paths=[str(src_dir)],
                  entity_types=[EntityType(type="service", description="d", extraction_cues=[])])


def test_ingest_file_writes_page_index_and_chunks(tmp_path, monkeypatch):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    src = src_dir / "doc.md"
    src.write_text("# Doc\n\n## Role\nTraefik proxies traffic.", encoding="utf-8")

    wiki_dir = tmp_path / "wiki" / "infra"
    wiki_dir.mkdir(parents=True)
    chunks = ChunkStore(tmp_path / "chunks" / "infra.jsonl", domain="infra")
    manifest = Manifest.load(tmp_path / "manifest.json")

    monkeypatch.setattr(ingest_mod, "extract_entities",
                        lambda llm, d, text: [Entity(name="Traefik", type="service")])
    monkeypatch.setattr(ingest_mod, "synthesize_pages",
                        lambda llm, d, text, stem, ents, existing, today: [
                            WikiPage(path="wiki_infra_traefik.md",
                                     content="---\nwiki_status: stub\n---\n# Traefik\n\n## Role\nproxy",
                                     annotation="Traefik proxy. Terms: ingress.")])

    changed = ingest_file(StubLLM(), _domain(src_dir), src, wiki_dir, chunks, manifest)

    assert changed is True
    assert (wiki_dir / "wiki_infra_traefik.md").exists()
    assert (wiki_dir / "_index.md").exists()
    rows = chunks.read_all()
    assert {r["page_id"] for r in rows} == {"wiki_infra_traefik"}
    assert any(r["kind"] == "summary" for r in rows)
    assert manifest.is_changed(src) is False  # marked processed


def test_ingest_file_skips_unchanged(tmp_path, monkeypatch):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    src = src_dir / "doc.md"
    src.write_text("# Doc", encoding="utf-8")
    wiki_dir = tmp_path / "wiki" / "infra"
    wiki_dir.mkdir(parents=True)
    chunks = ChunkStore(tmp_path / "chunks" / "infra.jsonl", domain="infra")
    manifest = Manifest.load(tmp_path / "manifest.json")
    manifest.mark(src)  # pretend already processed

    called = {"n": 0}
    monkeypatch.setattr(ingest_mod, "extract_entities",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1) or [])

    changed = ingest_file(StubLLM(), _domain(src_dir), src, wiki_dir, chunks, manifest)
    assert changed is False
    assert called["n"] == 0  # phases not invoked
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ingest.py -v`
Expected: FAIL (`No module named 'owaw.ingest'`).

- [ ] **Step 3: Implement `src/owaw/ingest.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ingest.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/owaw/ingest.py tests/test_ingest.py
git commit -m "feat(sp1): ingest pipeline orchestration (incremental)"
```

---

## Task 15: Domain walking + `ingest_domain` / `rebuild_domain`

Adds the multi-file drivers used by both the CLI and the daemon.

**Files:**
- Modify: `src/owaw/ingest.py` (append functions)
- Test: `tests/test_ingest_domain.py`

- [ ] **Step 1: Write the failing test**

`tests/test_ingest_domain.py`:
```python
from pathlib import Path
import owaw.ingest as ingest_mod
from owaw.ingest import iter_source_files, ingest_domain
from owaw.domains import Domain


def _domain(src_dir):
    return Domain(id="infra", name="Infra", wiki_folder="infra",
                  source_paths=[str(src_dir)], entity_types=[])


def test_iter_source_files_recurses(tmp_path):
    (tmp_path / "a.md").write_text("a", encoding="utf-8")
    nested = tmp_path / "deep" / "deeper"
    nested.mkdir(parents=True)
    (nested / "b.md").write_text("b", encoding="utf-8")
    files = sorted(p.name for p in iter_source_files(_domain(tmp_path)))
    assert files == ["a.md", "b.md"]


def test_ingest_domain_processes_each_changed_file(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.md").write_text("a", encoding="utf-8")
    (src / "b.md").write_text("b", encoding="utf-8")

    processed = []
    monkeypatch.setattr(ingest_mod, "ingest_file",
                        lambda llm, d, f, *a, **k: processed.append(f.name) or True)
    monkeypatch.setenv("OWAW_DATA_DIR", str(tmp_path / "data"))

    n = ingest_domain(llm=object(), domain=_domain(src))
    assert n == 2
    assert sorted(processed) == ["a.md", "b.md"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ingest_domain.py -v`
Expected: FAIL (`cannot import name 'iter_source_files'`).

- [ ] **Step 3: Append to `src/owaw/ingest.py`**

```python
# --- appended: multi-file drivers ---
from owaw import paths as _paths


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
    manifest = Manifest.load(_paths.manifest_path())
    count = 0
    for f in iter_source_files(domain):
        if ingest_file(llm, domain, f, wiki_dir, chunks, manifest, chunking, today):
            count += 1
    manifest.save()
    return count


def rebuild_domain(llm, domain: Domain, chunking: ChunkingConfig = DEFAULT_CHUNKING,
                   today: str = "") -> int:
    """Drop the domain's wiki + chunks + manifest entries, then full re-ingest."""
    import shutil

    wiki_dir = _paths.wiki_dir(domain.id)
    if wiki_dir.exists():
        shutil.rmtree(wiki_dir)
    chunks_path = _paths.chunks_path(domain.id)
    if chunks_path.exists():
        chunks_path.unlink()
    manifest = Manifest.load(_paths.manifest_path())
    for f in iter_source_files(domain):
        manifest.forget(f)
    manifest.save()
    return ingest_domain(llm, domain, chunking, today)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ingest_domain.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/owaw/ingest.py tests/test_ingest_domain.py
git commit -m "feat(sp1): domain walking + ingest_domain/rebuild_domain"
```

---

## Task 16: CLI (`init`, `ingest`, `rebuild`, `domain`)

**Files:**
- Create: `src/owaw/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

`tests/test_cli.py`:
```python
from typer.testing import CliRunner
import owaw.cli as cli_mod
from owaw.cli import app
from owaw.domains import Domain, load_domains

runner = CliRunner()


def test_domain_add_and_list(tmp_path, monkeypatch):
    monkeypatch.setenv("OWAW_DATA_DIR", str(tmp_path))
    r = runner.invoke(app, ["domain", "add", "--id", "infra", "--name", "Infra",
                            "--wiki-folder", "infra", "--source", str(tmp_path / "src")])
    assert r.exit_code == 0, r.output
    assert load_domains(tmp_path / "domains.yaml")[0].id == "infra"
    r2 = runner.invoke(app, ["domain", "list"])
    assert "infra" in r2.output


def test_init_creates_dirs_and_index(tmp_path, monkeypatch):
    monkeypatch.setenv("OWAW_DATA_DIR", str(tmp_path))
    runner.invoke(app, ["domain", "add", "--id", "infra", "--name", "Infra",
                        "--wiki-folder", "infra", "--source", str(tmp_path / "src")])
    r = runner.invoke(app, ["init", "--domain", "infra"])
    assert r.exit_code == 0, r.output
    assert (tmp_path / "wiki" / "infra" / "_index.md").exists()


def test_ingest_invokes_domain_driver(tmp_path, monkeypatch):
    monkeypatch.setenv("OWAW_DATA_DIR", str(tmp_path))
    runner.invoke(app, ["domain", "add", "--id", "infra", "--name", "Infra",
                        "--wiki-folder", "infra", "--source", str(tmp_path / "src")])
    seen = {}
    monkeypatch.setattr(cli_mod, "ingest_domain",
                        lambda llm, domain, **k: seen.setdefault("id", domain.id) or 3)
    monkeypatch.setattr(cli_mod.LLM, "from_config", classmethod(lambda cls, gen: object()))
    (tmp_path / "config.yaml").write_text(
        "generation:\n  model: m\n  base_url: u\n", encoding="utf-8")
    r = runner.invoke(app, ["ingest", "--domain", "infra"])
    assert r.exit_code == 0, r.output
    assert seen["id"] == "infra"
    assert "3" in r.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL (`No module named 'owaw.cli'`).

- [ ] **Step 3: Implement `src/owaw/cli.py`**

```python
"""Typer CLI: init, ingest, rebuild, domain add/list, watch."""
from __future__ import annotations

import typer

from owaw import paths
from owaw.config import load_config
from owaw.domains import Domain, add_domain, load_domains
from owaw.ingest import ingest_domain, rebuild_domain
from owaw.index import rebuild_index
from owaw.llm import LLM

app = typer.Typer(help="openwebui-ai-wiki engine (SP1)")
domain_app = typer.Typer(help="Manage domains")
app.add_typer(domain_app, name="domain")


def _get_domain(domain_id: str) -> Domain:
    for d in load_domains(paths.domains_path()):
        if d.id == domain_id:
            return d
    raise typer.BadParameter(f"unknown domain: {domain_id}")


def _llm() -> LLM:
    cfg = load_config(paths.config_path())
    return LLM.from_config(cfg.generation)


@domain_app.command("add")
def domain_add(
    id: str = typer.Option(...),
    name: str = typer.Option(...),
    wiki_folder: str = typer.Option(...),
    source: list[str] = typer.Option(..., help="Source path (repeatable)"),
):
    add_domain(
        Domain(id=id, name=name, wiki_folder=wiki_folder, source_paths=list(source), entity_types=[]),
        paths.domains_path(),
    )
    typer.echo(f"added domain '{id}'")


@domain_app.command("list")
def domain_list():
    for d in load_domains(paths.domains_path()):
        typer.echo(f"{d.id}\t{d.name}\t{len(d.source_paths)} source(s)")


@app.command()
def init(domain: str = typer.Option(...)):
    d = _get_domain(domain)
    paths.ensure_dirs(d.id)
    rebuild_index(paths.wiki_dir(d.id), d.name)
    typer.echo(f"initialised domain '{d.id}' at {paths.wiki_dir(d.id)}")


@app.command()
def ingest(domain: str = typer.Option(None, help="Domain id; omit for all")):
    domains = [_get_domain(domain)] if domain else load_domains(paths.domains_path())
    llm = _llm()
    cfg = load_config(paths.config_path())
    total = 0
    for d in domains:
        n = ingest_domain(llm, d, chunking=cfg.chunking)
        typer.echo(f"{d.id}: processed {n} file(s)")
        total += n
    typer.echo(f"done: {total} file(s)")


@app.command()
def rebuild(domain: str = typer.Option(...)):
    d = _get_domain(domain)
    cfg = load_config(paths.config_path())
    n = rebuild_domain(_llm(), d, chunking=cfg.chunking)
    typer.echo(f"rebuilt '{d.id}': {n} file(s)")


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/owaw/cli.py tests/test_cli.py
git commit -m "feat(sp1): typer cli (init, ingest, rebuild, domain)"
```

---

## Task 17: Daemon (watchdog inotify + debounce)

**Files:**
- Create: `src/owaw/daemon.py`
- Modify: `src/owaw/cli.py` (add `watch` command)
- Test: `tests/test_daemon.py`

- [ ] **Step 1: Write the failing test**

`tests/test_daemon.py`:
```python
from owaw.daemon import Debouncer


def test_debouncer_coalesces_until_flush():
    fired = []
    deb = Debouncer(delay_ms=10_000, on_flush=lambda items: fired.append(sorted(items)))
    deb.add("a")
    deb.add("b")
    deb.add("a")
    assert fired == []          # nothing fired yet
    deb.flush_now()
    assert fired == [["a", "b"]]  # coalesced unique set


def test_debouncer_resets_after_flush():
    fired = []
    deb = Debouncer(delay_ms=10_000, on_flush=lambda items: fired.append(sorted(items)))
    deb.add("a")
    deb.flush_now()
    deb.add("c")
    deb.flush_now()
    assert fired == [["a"], ["c"]]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_daemon.py -v`
Expected: FAIL (`No module named 'owaw.daemon'`).

- [ ] **Step 3: Implement `src/owaw/daemon.py`**

```python
"""inotify watcher + debounce. The Debouncer is timer-free for tests (flush_now)."""
from __future__ import annotations

import threading
from collections.abc import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


class Debouncer:
    """Collect a unique set of items; fire on_flush after delay_ms of quiet, or flush_now()."""

    def __init__(self, delay_ms: int, on_flush: Callable[[set], None]):
        self._delay = delay_ms / 1000.0
        self._on_flush = on_flush
        self._pending: set = set()
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def add(self, item) -> None:
        with self._lock:
            self._pending.add(item)
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._delay, self.flush_now)
            self._timer.daemon = True
            self._timer.start()

    def flush_now(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            items, self._pending = self._pending, set()
        if items:
            self._on_flush(items)


class _Handler(FileSystemEventHandler):
    def __init__(self, debouncer: Debouncer):
        self._deb = debouncer

    def on_any_event(self, event):
        if not event.is_directory:
            self._deb.add(event.src_path)


def watch(domain, debounce_ms: int, on_change: Callable[[set], None]) -> Observer:
    """Start observing a domain's source paths. Returns a started Observer (caller joins/stops)."""
    debouncer = Debouncer(debounce_ms, on_change)
    observer = Observer()
    handler = _Handler(debouncer)
    for root in domain.source_paths:
        observer.schedule(handler, root, recursive=True)
    observer.start()
    return observer
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_daemon.py -v`
Expected: PASS.

- [ ] **Step 5: Add the `watch` CLI command to `src/owaw/cli.py`**

Append to `src/owaw/cli.py` (before `if __name__`):
```python
@app.command()
def watch(domain: str = typer.Option(None, help="Domain id; omit for all")):
    import time
    from owaw import paths as _paths
    from owaw.daemon import watch as watch_domain

    domains = [_get_domain(domain)] if domain else load_domains(_paths.domains_path())
    cfg = load_config(_paths.config_path())
    llm = _llm()

    def make_handler(d):
        def _on_change(_paths_changed):
            n = ingest_domain(llm, d, chunking=cfg.chunking)
            typer.echo(f"[watch] {d.id}: reingested, {n} file(s) changed")
        return _on_change

    observers = [watch_domain(d, cfg.debounce_ms, make_handler(d)) for d in domains]
    typer.echo(f"watching {len(domains)} domain(s); Ctrl-C to stop")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        for o in observers:
            o.stop()
        for o in observers:
            o.join()
```

- [ ] **Step 6: Run the full suite**

Run: `pytest -v`
Expected: PASS (all modules; `watch` is smoke-covered by import + `Debouncer` tests).

- [ ] **Step 7: Commit**

```bash
git add src/owaw/daemon.py src/owaw/cli.py tests/test_daemon.py
git commit -m "feat(sp1): inotify daemon + watch command"
```

---

## Task 18: Source deletion (orphan pruning)

When a source file is deleted, prune the wiki pages and chunks that derived from it alone.
Provenance is read deterministically from each page's `wiki_sources` frontmatter (no LLM). A page
still referenced by another source is kept. Reconciliation runs inside `ingest_domain`, so both the
CLI and the daemon get it.

**Files:**
- Modify: `src/owaw/manifest.py` (add `tracked_paths`)
- Modify: `src/owaw/ingest.py` (add pruning + call it in `ingest_domain`)
- Test: `tests/test_deletion.py`

- [ ] **Step 1: Write the failing test**

`tests/test_deletion.py`:
```python
from pathlib import Path
import owaw.ingest as ingest_mod
from owaw.ingest import ingest_domain
from owaw.domains import Domain
from owaw.entities import Entity
from owaw.pages import WikiPage
from owaw.chunkstore import ChunkStore
from owaw import paths


def _domain(src_dir):
    return Domain(id="infra", name="Infra", wiki_folder="infra",
                  source_paths=[str(src_dir)], entity_types=[])


def _stub_phases(monkeypatch, source_stem):
    monkeypatch.setattr(ingest_mod, "extract_entities",
                        lambda llm, d, text: [Entity(name="Traefik")])
    monkeypatch.setattr(ingest_mod, "synthesize_pages",
                        lambda llm, d, text, stem, ents, existing, today: [
                            WikiPage(
                                path="wiki_infra_traefik.md",
                                content=f"---\nwiki_sources: [\"[[{source_stem}]]\"]\n"
                                        f"wiki_status: stub\n---\n# Traefik\n\nbody",
                                annotation="a")])


def test_deleting_only_source_prunes_page_and_chunks(tmp_path, monkeypatch):
    monkeypatch.setenv("OWAW_DATA_DIR", str(tmp_path / "data"))
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    src = src_dir / "doc.md"
    src.write_text("# Doc", encoding="utf-8")
    _stub_phases(monkeypatch, "doc")

    assert ingest_domain(llm=object(), domain=_domain(src_dir)) == 1
    page = paths.wiki_dir("infra") / "wiki_infra_traefik.md"
    assert page.exists()
    assert ChunkStore(paths.chunks_path("infra"), domain="infra").read_all()

    src.unlink()  # delete the only source
    ingest_domain(llm=object(), domain=_domain(src_dir))  # reconcile prunes the orphan
    assert not page.exists()
    assert ChunkStore(paths.chunks_path("infra"), domain="infra").read_all() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_deletion.py -v`
Expected: FAIL (`cannot import name 'tracked_paths'` / page still exists after deletion).

- [ ] **Step 3: Add `tracked_paths` to `src/owaw/manifest.py`**

Add this method to the `Manifest` class:
```python
    def tracked_paths(self) -> list[Path]:
        return [Path(k) for k in self._hashes]
```

- [ ] **Step 4: Add pruning to `src/owaw/ingest.py`**

Append to `src/owaw/ingest.py`:
```python
# --- appended: source-deletion reconciliation ---
import os as _os
import re as _re

from owaw.frontmatter import split_frontmatter


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
```

- [ ] **Step 5: Call reconciliation in `ingest_domain`**

In `src/owaw/ingest.py`, edit `ingest_domain` to reconcile deletions before walking files. Change:
```python
    manifest = Manifest.load(_paths.manifest_path())
    count = 0
    for f in iter_source_files(domain):
```
to:
```python
    manifest = Manifest.load(_paths.manifest_path())
    reconcile_deletions(domain, wiki_dir, chunks, manifest)
    count = 0
    for f in iter_source_files(domain):
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_deletion.py -v`
Expected: PASS.

- [ ] **Step 7: Run the full suite**

Run: `pytest -v`
Expected: PASS (all modules).

- [ ] **Step 8: Commit**

```bash
git add src/owaw/manifest.py src/owaw/ingest.py tests/test_deletion.py
git commit -m "feat(sp1): prune orphan pages/chunks on source deletion"
```

---

## Task 19: Integration test (fixture corpus, mocked LLM)

End-to-end through `ingest_domain` with phases stubbed, asserting real wiki + chunk output.

**Files:**
- Create: `tests/fixtures/sources/intro.md`
- Create: `tests/test_integration.py`

- [ ] **Step 1: Create the fixture**

`tests/fixtures/sources/intro.md`:
```text
# Stack intro

## Reverse proxy
Traefik terminates TLS and routes to services.

## Logging
Loki stores logs; the collector tails files.
```

- [ ] **Step 2: Write the integration test**

`tests/test_integration.py`:
```python
from pathlib import Path
import owaw.ingest as ingest_mod
from owaw.ingest import ingest_domain
from owaw.domains import Domain
from owaw.entities import Entity
from owaw.pages import WikiPage
from owaw.chunkstore import ChunkStore
from owaw import paths

FIXTURES = Path(__file__).parent / "fixtures" / "sources"


def test_end_to_end_produces_wiki_and_chunks(tmp_path, monkeypatch):
    monkeypatch.setenv("OWAW_DATA_DIR", str(tmp_path / "data"))
    domain = Domain(id="infra", name="Infra", wiki_folder="infra",
                    source_paths=[str(FIXTURES)], entity_types=[])

    monkeypatch.setattr(ingest_mod, "extract_entities",
                        lambda llm, d, text: [Entity(name="Traefik", type=None)])

    def fake_pages(llm, d, text, stem, ents, existing, today):
        body = ("---\nwiki_sources: [\"[[intro]]\"]\nwiki_status: stub\n---\n"
                "# Traefik\n\n## Role\nTLS termination and routing.")
        return [WikiPage(path="wiki_infra_traefik.md", content=body,
                         annotation="Traefik reverse proxy. Terms: tls, routing, ingress.")]

    monkeypatch.setattr(ingest_mod, "synthesize_pages", fake_pages)

    n = ingest_domain(llm=object(), domain=domain)
    assert n == 1

    page = paths.wiki_dir("infra") / "wiki_infra_traefik.md"
    assert page.exists()
    assert "TLS termination" in page.read_text(encoding="utf-8")
    assert (paths.wiki_dir("infra") / "_index.md").exists()

    rows = ChunkStore(paths.chunks_path("infra"), domain="infra").read_all()
    kinds = {r["kind"] for r in rows}
    assert kinds == {"summary", "section"}
    summary = next(r for r in rows if r["kind"] == "summary")
    assert summary["embed_text"].startswith("Traefik reverse proxy")
    section = next(r for r in rows if r["kind"] == "section")
    assert section["embed_text"].startswith("Traefik reverse proxy")  # annotation prepended
    assert "## Role" in section["embed_text"]


def test_second_run_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("OWAW_DATA_DIR", str(tmp_path / "data"))
    domain = Domain(id="infra", name="Infra", wiki_folder="infra",
                    source_paths=[str(FIXTURES)], entity_types=[])
    monkeypatch.setattr(ingest_mod, "extract_entities", lambda *a, **k: [Entity(name="Traefik")])
    monkeypatch.setattr(ingest_mod, "synthesize_pages",
                        lambda llm, d, text, stem, ents, existing, today: [
                            WikiPage(path="wiki_infra_traefik.md",
                                     content="---\nwiki_status: stub\n---\n# Traefik\n\nbody",
                                     annotation="a")])
    assert ingest_domain(llm=object(), domain=domain) == 1
    assert ingest_domain(llm=object(), domain=domain) == 0  # nothing changed
```

- [ ] **Step 3: Run the integration test**

Run: `pytest tests/test_integration.py -v`
Expected: PASS (both tests).

- [ ] **Step 4: Run the full suite**

Run: `pytest -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/sources/intro.md tests/test_integration.py
git commit -m "test(sp1): end-to-end integration with mocked llm"
```

---

## Task 20: Packaging (Docker + compose snippet + sample config)

Containerise SP1 for the `minipc-traefik` stack. No public route; the daemon runs as a
service, the data dir is a volume shared with SP2/SP3.

**Files:**
- Create: `Dockerfile`
- Create: `docs/deploy/docker-compose.snippet.yml`
- Create: `docs/deploy/config.sample.yaml`
- Create: `docs/deploy/domains.sample.yaml`

- [ ] **Step 1: Create `Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY prompts ./prompts
RUN pip install --no-cache-dir .
ENV OWAW_DATA_DIR=/data
VOLUME ["/data"]
ENTRYPOINT ["owaw"]
CMD ["watch"]
```

- [ ] **Step 2: Create `docs/deploy/config.sample.yaml`**

```yaml
generation:
  model: "<litellm-cloud-model-id>"          # e.g. an ollama *:cloud or anthropic model
  base_url: "http://host.docker.internal:4000/v1"
  api_key_env: OWAW_LLM_KEY                   # value injected from secrets, never committed
chunking:
  maxChars: 1200
  minChars: 200
  overlapChars: 200
  maxCount: 12
extraction:
  engine: docling
daemon:
  debounce_ms: 1500
```

- [ ] **Step 3: Create `docs/deploy/domains.sample.yaml`**

```yaml
domains:
  - id: infra
    name: "Infrastructure"
    wiki_folder: infra
    source_paths:
      - /data/sources/minipc-docs
    entity_types:
      - type: service
        description: "A deployed service or daemon"
        extraction_cues: ["systemd unit", "container", "port"]
        min_mentions_for_page: 2
    language_notes: "Corpus is mostly Russian; keep entity names verbatim."
```

- [ ] **Step 4: Create `docs/deploy/docker-compose.snippet.yml`**

```yaml
# Add to the minipc-traefik stack. No Traefik router — internal service only.
services:
  owaw:
    build: ../openwebui-ai-wiki        # or image: once published
    container_name: minipc-traefik-owaw
    restart: unless-stopped
    env_file:
      - ./owaw.conf                    # OWAW_LLM_KEY=... (chmod 600, not committed)
    volumes:
      - owaw_data:/data                # wiki + chunks + state (shared with SP2/SP3)
      - /opt/minipc-docs:/data/sources/minipc-docs:ro   # source(s), read-only, nested ok
    extra_hosts:
      - "host.docker.internal:host-gateway"   # reach LiteLLM on the host
    networks:
      - proxy-net

volumes:
  owaw_data:
```

- [ ] **Step 5: Verify the image builds and the CLI runs**

Run:
```bash
cd /home/ikeniborn/Documents/Project/openwebui-ai-wiki
docker build -t owaw:dev .
docker run --rm owaw:dev --help
```
Expected: build succeeds; `--help` lists `init`, `ingest`, `rebuild`, `domain`, `watch`.

- [ ] **Step 6: Commit**

```bash
git add Dockerfile docs/deploy/
git commit -m "build(sp1): dockerfile + compose snippet + sample config"
```

---

## Done — SP1 acceptance

After Task 20, SP1 is complete and testable on its own:

- `owaw domain add` → `owaw init` → `owaw ingest` builds a wiki + chunk records from sources.
- `owaw watch` keeps them current (inotify, debounced, incremental).
- `owaw rebuild --domain` does a full regenerate.
- Chunk records (`chunks/<domain>.jsonl`) carry `embed_text` + `hash`, ready for **SP2** (bge-m3
  embedding → OpenWebUI Knowledge). The wiki tree is ready for **SP3**'s Doc Tool live reads.

Run the whole suite once more before handing off: `pytest -v` → all green.
