---
review:
  plan_hash: 7ed975680a617e3e
  spec_hash: 3055a1f4b76186da
  last_run: 2026-06-21
  phases:
    structure:     { status: passed }
    coverage:      { status: passed }
    dependencies:  { status: passed }
    verifiability: { status: passed }
    consistency:   { status: passed }
  findings: []
chain:
  intent: null
  spec: docs/superpowers/specs/2026-06-20-sp3-openwebui-agent-design.md
---

# SP3 — OpenWebUI Agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose a shared OpenWebUI "Doc Agent" — a Workspace Model with a read-only, jailed Doc Tool over the mounted wiki + sources, the ported `query.md` system prompt, and the SP2 `ai-wiki` Knowledge collection attached — provisioned reproducibly via a tested OpenWebUI API client.

**Architecture:** Two code units plus deployment glue. (1) `doc_tool.py` is a **self-contained single-file** OpenWebUI Python Tool (only stdlib + pydantic) exposing `list_docs` / `read_doc` / `search_docs`; all retrieval is **pure-Python** (`os.walk` + `re`), jailed by realpath containment, with size/result caps — no `ripgrep`, so it is hermetic and needs no extra binary in the OpenWebUI container. (2) `provision.py` is the **only** SP3 OpenWebUI API egress: it upserts the Tool, sets its valves, resolves the `ai-wiki` collection id, and upserts the Workspace Model (base model + ported system prompt + `meta.knowledge` + `meta.toolIds` + public access). A Typer command `owaw owui-provision` wires it to config. A validation spike confirms the version-sensitive OpenWebUI API shapes before the client is written.

**Tech Stack:** Python 3.12, `httpx` (already a dep), `pydantic` (already present transitively via `openai`), `typer`, `pytest` with `httpx.MockTransport` and `tmp_path`. Package data shipped via hatchling `force-include` and read with `importlib.resources`.

**Spec:** [`../specs/2026-06-20-sp3-openwebui-agent-design.md`](../specs/2026-06-20-sp3-openwebui-agent-design.md)

**Depends on (already merged):**
- SP1 — wiki + source files on disk under `$OWAW_DATA_DIR/wiki` and the configured source roots.
- SP2 — the populated `ai-wiki` Knowledge collection and the `openwebui` config section + `OpenWebUIKnowledgeClient` HTTP pattern this plan mirrors.

---

## Design decisions (locked before planning)

- **Search backend = pure-Python** (`os.walk` + `re`), not `ripgrep`. Honours the spec's intent (fixed pattern, no shell injection, size caps) while staying hermetic and free of a container-side `rg` dependency. Deviation from the spec's literal "ripgrep"/"grep" wording (spec finding F-001) is intentional and noted here.
- **Provisioning = tested API client + CLI** (`owaw owui-provision`), not manual UI. Mirrors SP2's `OpenWebUIKnowledgeClient` (httpx + retry + `MockTransport` tests). Gated by a validation spike because the OpenWebUI Tools/Models/access shapes are version-sensitive.
- **Doc Tool = self-contained single file**, tested by direct import (`from owaw.owui import doc_tool`). It must not import from `owaw` (a guard test enforces this) because OpenWebUI stores and exec's the file standalone.
- **PDF/Office in `read_doc` → defer to RAG** (spec default): return a short note, do not extract.
- **Quantified caps (resolves spec finding F-002):** `max_read_bytes = 100_000`, `max_results = 20`, base chat model = config `agent.base_model` (no hardcode).
- **Public/shared visibility is verified** in the deploy E2E checklist (resolves spec finding F-003).

## Design contract (types and signatures used across tasks)

Config (Task 1) — `src/owaw/config.py`:
- `@dataclass(frozen=True) class AgentConfig:` fields `base_model: str`, `model_id: str = "ai-wiki-agent"`, `model_name: str = "Doc Agent"`, `tool_id: str = "wiki_docs"`, `tool_name: str = "Wiki Docs"`, `doc_roots: tuple[str, ...] = ("/data/wiki", "/data/sources")`, `max_read_bytes: int = 100_000`, `max_results: int = 20`, `public: bool = True`.
- `Config` gains `agent: AgentConfig | None = None`.

Doc Tool (Task 2) — `src/owaw/owui/doc_tool.py` (module-level, underscore-prefixed so the `Tools` methods can share their names):
- `_roots(raw: str) -> list[Path]`
- `_resolve_within(roots: list[Path], rel: str) -> Path`  (raises `ValueError` on escape)
- `_list_docs(roots: list[Path], rel: str = "") -> str`
- `_read_doc(roots: list[Path], rel: str, max_bytes: int = 100_000) -> str`
- `_search_docs(roots: list[Path], query: str, max_results: int = 20, max_bytes: int = 100_000) -> str`
- `class Tools:` with `class Valves(BaseModel)` and async methods `list_docs(path="")`, `read_doc(path)`, `search_docs(query)`.

Provisioner (Task 5) — `src/owaw/owui/provision.py`:
- `doc_tool_source() -> str`, `agent_system_prompt() -> str` (read package data).
- `_public_grants() -> list[dict]` (version-sensitive; confirmed by Task 4).
- `class OpenWebUIProvisioner` with `upsert_tool(tool_id, name, content, description, public=True) -> str`, `set_tool_valves(tool_id, valves: dict) -> None`, `resolve_collection_id(name) -> str | None`, `upsert_model(*, model_id, name, base_model, system_prompt, collection_id, collection_name, tool_id, public=True) -> str`, classmethod `from_config(ow: OpenWebUIConfig)`.
- `provision_agent(ow: OpenWebUIConfig, agent: AgentConfig, *, provisioner=None) -> dict` returning `{"tool_id", "model_id", "collection_id"}`.

CLI (Task 6) — `src/owaw/cli.py`: `@app.command("owui-provision")`.

## File structure

| File | Status | Responsibility |
|---|---|---|
| `src/owaw/config.py` | modify | add `AgentConfig` + load `agent:` section |
| `src/owaw/owui/__init__.py` | create | new subpackage for OpenWebUI deploy artifacts |
| `src/owaw/owui/doc_tool.py` | create | self-contained OpenWebUI Tool (jail/list/read/search) |
| `src/owaw/owui/provision.py` | create | OpenWebUI API client: upsert Tool + Model, attach knowledge |
| `src/owaw/prompts/agent_query.md` | create | ported `query.md` system prompt (static, no templating) |
| `src/owaw/cli.py` | modify | add `owui-provision` command |
| `pyproject.toml` | modify | `force-include` for `agent_query.md` |
| `tests/test_config.py` | modify | `agent:` parse + defaults |
| `tests/test_doc_tool.py` | create | jail/list/read/search + self-contained guard + Tools methods + package data |
| `tests/test_provision.py` | create | provisioner MockTransport tests |
| `tests/test_provision_cli.py` | create | `owui-provision` CLI test (provisioner monkeypatched) |
| `docs/deploy/config.sample.yaml` | modify | `agent:` sample section |
| `docs/deploy/sp3-openwebui-agent.md` | create | OpenWebUI mounts + provisioning + manual E2E checklist |
| `docs/superpowers/specs/2026-06-20-sp3-openwebui-api-findings.md` | create | Task 4 spike output |

---

## Task 1: Config — `AgentConfig` + sample section

**Files:**
- Modify: `src/owaw/config.py`
- Modify: `tests/test_config.py`
- Modify: `docs/deploy/config.sample.yaml`

- [ ] **Step 1: Write the failing config tests**

Append to `tests/test_config.py`:

```python
def test_load_config_parses_agent(tmp_path):
    (tmp_path / "config.yaml").write_text(
        "generation:\n  model: m\n  base_url: u\n"
        "agent:\n"
        "  base_model: gpt-4o\n"
        "  model_id: ai-wiki-agent\n"
        "  model_name: Doc Agent\n"
        "  tool_id: wiki_docs\n"
        "  tool_name: Wiki Docs\n"
        "  doc_roots:\n    - /data/wiki\n    - /data/sources\n"
        "  max_read_bytes: 50000\n"
        "  max_results: 10\n"
        "  public: true\n",
        encoding="utf-8",
    )
    cfg = load_config(tmp_path / "config.yaml")
    assert cfg.agent.base_model == "gpt-4o"
    assert cfg.agent.doc_roots == ("/data/wiki", "/data/sources")
    assert cfg.agent.max_read_bytes == 50000
    assert cfg.agent.max_results == 10
    assert cfg.agent.public is True


def test_load_config_agent_optional_with_defaults(tmp_path):
    (tmp_path / "config.yaml").write_text(
        "generation:\n  model: m\n  base_url: u\n"
        "agent:\n  base_model: gpt-4o\n",
        encoding="utf-8",
    )
    cfg = load_config(tmp_path / "config.yaml")
    assert cfg.agent.model_id == "ai-wiki-agent"
    assert cfg.agent.tool_id == "wiki_docs"
    assert cfg.agent.doc_roots == ("/data/wiki", "/data/sources")
    assert cfg.agent.max_read_bytes == 100_000
    assert cfg.agent.public is True


def test_load_config_no_agent_section(tmp_path):
    (tmp_path / "config.yaml").write_text(
        "generation:\n  model: m\n  base_url: u\n", encoding="utf-8"
    )
    cfg = load_config(tmp_path / "config.yaml")
    assert cfg.agent is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'agent'`.

- [ ] **Step 3: Add `AgentConfig` and wire it into `Config`**

In `src/owaw/config.py`, add the dataclass after `SyncConfig` (before `Config`):

```python
@dataclass(frozen=True)
class AgentConfig:
    base_model: str
    model_id: str = "ai-wiki-agent"
    model_name: str = "Doc Agent"
    tool_id: str = "wiki_docs"
    tool_name: str = "Wiki Docs"
    doc_roots: tuple[str, ...] = ("/data/wiki", "/data/sources")
    max_read_bytes: int = 100_000
    max_results: int = 20
    public: bool = True
```

Add the field to `Config` (after `sync`):

```python
@dataclass(frozen=True)
class Config:
    generation: GenerationConfig
    chunking: ChunkingConfig
    extraction_engine: str
    debounce_ms: int
    openwebui: OpenWebUIConfig | None = None
    embedding: EmbeddingConfig = EmbeddingConfig()
    sync: SyncConfig = SyncConfig()
    agent: AgentConfig | None = None
```

- [ ] **Step 4: Parse the `agent:` section in `load_config`**

In `load_config`, just before the final `return Config(...)`, add:

```python
    ag_raw = raw.get("agent")
    agent = None
    if ag_raw:
        agent = AgentConfig(
            base_model=ag_raw["base_model"],
            model_id=ag_raw.get("model_id", "ai-wiki-agent"),
            model_name=ag_raw.get("model_name", "Doc Agent"),
            tool_id=ag_raw.get("tool_id", "wiki_docs"),
            tool_name=ag_raw.get("tool_name", "Wiki Docs"),
            doc_roots=tuple(ag_raw.get("doc_roots", ["/data/wiki", "/data/sources"])),
            max_read_bytes=ag_raw.get("max_read_bytes", 100_000),
            max_results=ag_raw.get("max_results", 20),
            public=ag_raw.get("public", True),
        )
```

Then add `agent=agent,` to the `Config(...)` call.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: PASS (all existing config tests plus the 3 new ones).

- [ ] **Step 6: Add the `agent:` sample section**

Append to `docs/deploy/config.sample.yaml`:

```yaml
agent:
  base_model: "<litellm-chat-model-id>"   # the LiteLLM chat model the Doc Agent wraps
  model_id: "ai-wiki-agent"               # OpenWebUI model id
  model_name: "Doc Agent"
  tool_id: "wiki_docs"
  tool_name: "Wiki Docs"
  doc_roots:                              # paths INSIDE the OpenWebUI container (mounted :ro)
    - /data/wiki
    - /data/sources
  max_read_bytes: 100000                  # read_doc truncation cap
  max_results: 20                         # search_docs result cap
  public: true                            # share the agent + tool with all users
```

- [ ] **Step 7: Commit**

```bash
git add src/owaw/config.py tests/test_config.py docs/deploy/config.sample.yaml
git commit -m "feat(sp3): AgentConfig section + sample config"
```

---

## Task 2: Doc Tool — self-contained jailed reader

**Files:**
- Create: `src/owaw/owui/__init__.py`
- Create: `src/owaw/owui/doc_tool.py`
- Create: `tests/test_doc_tool.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_doc_tool.py`:

```python
import asyncio
from pathlib import Path

import pytest

from owaw.owui import doc_tool
from owaw.owui.doc_tool import Tools, _list_docs, _read_doc, _resolve_within, _roots, _search_docs


def _tree(tmp_path):
    root = tmp_path / "wiki"
    (root / "sub").mkdir(parents=True)
    (root / "a.md").write_text("alpha\nNEEDLE here\n", encoding="utf-8")
    (root / "sub" / "b.md").write_text("beta line\n", encoding="utf-8")
    (root / "big.md").write_text("x" * 50, encoding="utf-8")
    (root / "img.png").write_bytes(b"\x89PNG\x00\x00binary")
    (root / "doc.pdf").write_bytes(b"%PDF-1.4 not text")
    return [root.resolve()]


def test_resolve_rejects_parent_traversal(tmp_path):
    roots = _tree(tmp_path)
    with pytest.raises(ValueError):
        _resolve_within(roots, "../secret.txt")


def test_resolve_rejects_absolute_escape(tmp_path):
    roots = _tree(tmp_path)
    with pytest.raises(ValueError):
        _resolve_within(roots, "/etc/passwd")


def test_resolve_allows_nested(tmp_path):
    roots = _tree(tmp_path)
    assert _resolve_within(roots, "sub/b.md") == (roots[0] / "sub" / "b.md")


def test_list_docs_lists_children(tmp_path):
    roots = _tree(tmp_path)
    out = _list_docs(roots, "")
    assert "a.md" in out and "sub/" in out


def test_read_doc_returns_text(tmp_path):
    roots = _tree(tmp_path)
    assert "alpha" in _read_doc(roots, "a.md")


def test_read_doc_truncates_over_cap(tmp_path):
    roots = _tree(tmp_path)
    out = _read_doc(roots, "big.md", max_bytes=10)
    assert "[truncated at 10 bytes]" in out


def test_read_doc_defers_pdf(tmp_path):
    roots = _tree(tmp_path)
    out = _read_doc(roots, "doc.pdf")
    assert "RAG" in out


def test_read_doc_rejects_binary(tmp_path):
    roots = _tree(tmp_path)
    out = _read_doc(roots, "img.png")
    assert "binary" in out.lower()


def test_read_doc_missing(tmp_path):
    roots = _tree(tmp_path)
    assert "not found" in _read_doc(roots, "nope.md")


def test_search_docs_finds_literal(tmp_path):
    roots = _tree(tmp_path)
    out = _search_docs(roots, "NEEDLE")
    assert "a.md" in out and ":2:" in out


def test_search_docs_respects_max_results(tmp_path):
    roots = _tree(tmp_path)
    (roots[0] / "c.md").write_text("NEEDLE\nNEEDLE\nNEEDLE\n", encoding="utf-8")
    out = _search_docs(roots, "NEEDLE", max_results=2)
    assert len(out.splitlines()) == 2


def test_tool_file_is_self_contained():
    src = Path(doc_tool.__file__).read_text(encoding="utf-8")
    assert "import owaw" not in src
    assert "from owaw" not in src


def test_tools_methods_use_valves(tmp_path):
    roots = _tree(tmp_path)
    t = Tools()
    t.valves.roots = str(roots[0])
    assert "alpha" in asyncio.run(t.read_doc("a.md"))
    assert "a.md" in asyncio.run(t.list_docs(""))
    assert "NEEDLE" in asyncio.run(t.search_docs("NEEDLE"))
    assert "escapes" in asyncio.run(t.read_doc("../x"))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_doc_tool.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'owaw.owui'`.

- [ ] **Step 3: Create the subpackage marker**

Create `src/owaw/owui/__init__.py` (empty file):

```python
```

- [ ] **Step 4: Write the Doc Tool**

Create `src/owaw/owui/doc_tool.py`:

```python
"""
title: Wiki Docs
author: openwebui-ai-wiki
description: Read-only, jailed access to the AI wiki and its source files (list, read, search).
version: 0.1.0
required_open_webui_version: 0.5.0
requirements:
"""
# Self-contained OpenWebUI Tool. Only stdlib + pydantic — do NOT import from owaw;
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_doc_tool.py -v`
Expected: PASS (14 tests).

- [ ] **Step 6: Commit**

```bash
git add src/owaw/owui/__init__.py src/owaw/owui/doc_tool.py tests/test_doc_tool.py
git commit -m "feat(sp3): self-contained jailed Doc Tool (list/read/search, pure-Python)"
```

---

## Task 3: System prompt port + package-data shipping

**Files:**
- Create: `src/owaw/prompts/agent_query.md`
- Modify: `pyproject.toml`
- Modify: `tests/test_doc_tool.py` (add a package-data resources test)

> The provisioner (Task 5) reads the tool source and the system prompt via `importlib.resources`. This task creates the prompt, ships it as package data, and proves both artifacts are loadable from the installed package.

- [ ] **Step 1: Write the failing resources test**

Append to `tests/test_doc_tool.py`:

```python
def test_package_data_loadable():
    from importlib.resources import files
    tool_src = files("owaw.owui").joinpath("doc_tool.py").read_text(encoding="utf-8")
    assert "class Tools" in tool_src
    prompt = files("owaw.prompts").joinpath("agent_query.md").read_text(encoding="utf-8")
    assert "Doc Agent" in prompt
    assert "[[" in prompt  # wikilink citation convention is preserved
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_doc_tool.py::test_package_data_loadable -v`
Expected: FAIL — `FileNotFoundError` / `IsADirectoryError` for `agent_query.md` (does not exist yet).

- [ ] **Step 3: Create the ported system prompt**

Create `src/owaw/prompts/agent_query.md` (persona adapted to a shared multi-domain agent; the formatting rules are ported verbatim from `obsidian-ai-wiki/prompts/query.md`):

```markdown
You are the **Doc Agent** for the documentation wiki. Answer strictly based on the wiki and its source files. Do not invent facts that are not in the documentation.

## Retrieval

Use the available retrieval surfaces — do not answer from memory:
- **Knowledge (RAG):** semantic search over the wiki, for conceptual questions.
- **Doc Tool** (read-only, jailed to the docs):
  - `search_docs(query)` — find an exact string across the wiki and sources (precise terms, config keys, commands).
  - `read_doc(path)` — read a full page or source file.
  - `list_docs(path)` — inspect the current folder structure.

Prefer `search_docs` / `read_doc` when the user asks for an exact value, a specific file, or the current folder state. If RAG returns nothing useful, fall back to the Doc Tool and say so. When referring to wiki pages, cite them as WikiLinks `[[name]]`.

## Formatting rules

**MANDATORY — code and commands:**

Any command, script, path, or config is ALWAYS rendered as a fenced block with a language tag.

WRONG:
Run sudo systemctl restart nginx

RIGHT:
```bash
sudo systemctl restart nginx
```

This rule applies inside numbered and bulleted lists as well.

WRONG:
- Disable all swap: `sudo swapoff -a`

RIGHT:
- Disable all swap:
  ```bash
  sudo swapoff -a
  ```

Languages: `bash` for shell commands, `yaml`/`toml`/`ini` for configs, `python`/`go`/`js` for code, `text` if unknown.
Only file names and flags without spaces may be written inline in `` `backticks` ``: `/etc/fstab`, `--show`, `vm.swappiness`.

**Answer structure:**
- A short, direct answer at the start — no introductions.
- If there are several topics — separate them with `##` headings.
- Enumerations: ALWAYS a list (`-` or `1.`), not comma-separated inline.
- Comparative/numeric data (≥3 rows, ≥2 columns) → a table.
- Key terms and entities → `**bold**` at first mention.

**Links to the wiki:**
- Reference the source page via `[[WikiLink]]` after a fact or section.
- Do not list sources in a separate block — insert links in place.

**Compactness:**
- No intro phrases ("Of course", "In order to").
- No repetition from the context without adding meaning.
- Use a table only if the data is genuinely tabular (≥3 rows, ≥2 columns).
```

- [ ] **Step 4: Ship the prompt as package data**

In `pyproject.toml`, add the prompt to the existing `force-include` block:

```toml
[tool.hatch.build.targets.wheel.force-include]
"src/owaw/prompts/ingest_entities.md" = "owaw/prompts/ingest_entities.md"
"src/owaw/prompts/ingest_pages.md" = "owaw/prompts/ingest_pages.md"
"src/owaw/prompts/agent_query.md" = "owaw/prompts/agent_query.md"
```

(`doc_tool.py` is a `.py` file inside the `owaw` package and is included automatically — no `force-include` needed.)

- [ ] **Step 5: Reinstall and run the test to verify it passes**

Run:
```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest tests/test_doc_tool.py -v
```
Expected: PASS (15 tests, including `test_package_data_loadable`).

- [ ] **Step 6: Commit**

```bash
git add src/owaw/prompts/agent_query.md pyproject.toml tests/test_doc_tool.py
git commit -m "feat(sp3): ported query.md system prompt shipped as package data"
```

---

## Task 4: Validation spike — confirm OpenWebUI Tools/Models/access API

> **Spike (research, no TDD).** The OpenWebUI Tool/Model create + update endpoints, the access-control representation, and the knowledge-attach field are **version-sensitive**. Confirm them against the **deployed** OpenWebUI version before writing the provisioner (Task 5). Output a findings doc that Task 5's code and tests must match. Mirrors SP2 Task 7.

**Files:**
- Create: `docs/superpowers/specs/2026-06-20-sp3-openwebui-api-findings.md`

Seed findings (from SP3 design research; treat as hypotheses to confirm, not ground truth):
- Tool create: `POST /api/v1/tools/create`, body `{id, name, content, meta:{description}, access_grants}`; update: `POST /api/v1/tools/id/{id}/update`; valves: `POST /api/v1/tools/id/{id}/valves/update`. `content` carries the full Python source.
- Model create: `POST /api/v1/models/create` (`ModelForm`); update: `POST /api/v1/models/model/update`. Tools attach via `meta.toolIds`; knowledge via `meta.knowledge` (list of `{id, name, type:"collection"}`); system prompt via `params.system`; native calling via `params.function_calling="native"`.
- Knowledge id resolved by listing `GET /api/v1/knowledge/` and matching `name` (already used in `knowledge.py`).
- **Access control is the highest-risk unknown:** newer OpenWebUI uses `access_grants` (a list; public = wildcard `{"principal_type":"user","principal_id":"*","permission":"read"}`), while older versions use `access_control` (a dict; `null` = public). Confirm which the deployed version expects.
- Native function-calling mode may **disable** knowledge auto-injection — the agent must call the knowledge/Doc tools (the system prompt instructs this).

- [ ] **Step 1: Identify the deployed OpenWebUI version**

Run (adjust container name to the stack):
```bash
docker exec minipc-traefik-openwebui python -c "import open_webui; print(open_webui.__version__)" 2>/dev/null \
  || docker inspect --format '{{ index .Config.Labels "org.opencontainers.image.version" }}' minipc-traefik-openwebui
```
Record the exact version.

- [ ] **Step 2: Confirm the API shapes against that version**

For the pinned version, confirm each endpoint + body shape from the official docs (https://docs.openwebui.com) and, where ambiguous, the backend source for the matching tag (`backend/open_webui/routers/{tools,models,knowledge}.py`, `models/{tools,models}.py`). Confirm specifically: tool create/update/valves paths and `ToolForm` fields; `ModelForm` fields incl. `base_model_id`, `meta.toolIds`, `meta.knowledge`, `params.system`, `params.function_calling`; and the **access field name + public representation**.

- [ ] **Step 3: Write the findings doc**

Create `docs/superpowers/specs/2026-06-20-sp3-openwebui-api-findings.md` recording, per endpoint: HTTP method, path, exact JSON body shape, and any delta from the seed hypotheses above. State plainly: the access field name (`access_grants` list vs `access_control` dict) and the exact public value; whether knowledge auto-injects under native mode. End with a "Deltas for Task 5" list naming any body/path changes the provisioner and its tests must adopt.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-06-20-sp3-openwebui-api-findings.md
git commit -m "docs(sp3): OpenWebUI Tools/Models/access API findings (spike)"
```

---

## Task 5: Provisioner — upsert Tool + Workspace Model

> Apply any **Deltas for Task 5** from the Task 4 findings doc to the paths, body shapes, and `_public_grants()` below before/while implementing. The code here reflects the seed hypotheses; the findings doc is authoritative.

**Files:**
- Create: `src/owaw/owui/provision.py`
- Create: `tests/test_provision.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_provision.py`:

```python
import json

import httpx
import pytest

from owaw.config import AgentConfig, OpenWebUIConfig
from owaw.owui.provision import OpenWebUIProvisioner, provision_agent


def _provisioner(handler):
    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport, base_url="http://owui:8080")
    return OpenWebUIProvisioner(base_url="http://owui:8080", token="T",
                                http=http, sleep=lambda _s: None)


def test_upsert_tool_creates_public():
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path))
        if request.url.path == "/api/v1/tools/create":
            body = json.loads(request.content)
            assert body["id"] == "wiki_docs"
            assert "class Tools" in body["content"]
            assert body["access_grants"] == [
                {"principal_type": "user", "principal_id": "*", "permission": "read"}
            ]
            return httpx.Response(200, json={"id": "wiki_docs"})
        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    tid = _provisioner(handler).upsert_tool("wiki_docs", "Wiki Docs", "class Tools: pass", "d")
    assert tid == "wiki_docs"
    assert ("POST", "/api/v1/tools/create") in seen


def test_upsert_tool_updates_when_exists():
    seen = []

    def handler(request):
        seen.append(request.url.path)
        if request.url.path == "/api/v1/tools/create":
            return httpx.Response(400, json={"detail": "id taken"})
        if request.url.path == "/api/v1/tools/id/wiki_docs/update":
            return httpx.Response(200, json={"id": "wiki_docs"})
        raise AssertionError(f"unexpected {request.url.path}")

    _provisioner(handler).upsert_tool("wiki_docs", "Wiki Docs", "class Tools: pass", "d")
    assert "/api/v1/tools/id/wiki_docs/update" in seen


def test_resolve_collection_id():
    def handler(request):
        if request.url.path == "/api/v1/knowledge/":
            return httpx.Response(200, json=[{"id": "cid", "name": "ai-wiki"}])
        raise AssertionError

    assert _provisioner(handler).resolve_collection_id("ai-wiki") == "cid"
    assert _provisioner(handler).resolve_collection_id("absent") is None


def test_upsert_model_attaches_knowledge_tool_and_prompt():
    def handler(request):
        if request.url.path == "/api/v1/models/create":
            body = json.loads(request.content)
            assert body["base_model_id"] == "gpt-4o"
            assert body["meta"]["toolIds"] == ["wiki_docs"]
            assert body["meta"]["knowledge"] == [
                {"id": "cid", "name": "ai-wiki", "type": "collection"}
            ]
            assert body["params"]["function_calling"] == "native"
            assert "Doc Agent" in body["params"]["system"]
            assert body["access_grants"][0]["principal_id"] == "*"
            return httpx.Response(200, json={"id": "ai-wiki-agent"})
        raise AssertionError(f"unexpected {request.url.path}")

    mid = _provisioner(handler).upsert_model(
        model_id="ai-wiki-agent", name="Doc Agent", base_model="gpt-4o",
        system_prompt="You are the Doc Agent.", collection_id="cid",
        collection_name="ai-wiki", tool_id="wiki_docs",
    )
    assert mid == "ai-wiki-agent"


def test_provision_agent_end_to_end():
    seen = []

    def handler(request):
        p = request.url.path
        seen.append((request.method, p))
        if p == "/api/v1/tools/create":
            return httpx.Response(200, json={"id": "wiki_docs"})
        if p == "/api/v1/tools/id/wiki_docs/valves/update":
            assert json.loads(request.content)["roots"] == "/data/wiki,/data/sources"
            return httpx.Response(200, json={})
        if p == "/api/v1/knowledge/":
            return httpx.Response(200, json=[{"id": "cid", "name": "ai-wiki"}])
        if p == "/api/v1/models/create":
            return httpx.Response(200, json={"id": "ai-wiki-agent"})
        raise AssertionError(f"unexpected {request.method} {p}")

    ow = OpenWebUIConfig(base_url="http://owui:8080", collection="ai-wiki")
    agent = AgentConfig(base_model="gpt-4o")
    res = provision_agent(ow, agent, provisioner=_provisioner(handler))
    assert res == {"tool_id": "wiki_docs", "model_id": "ai-wiki-agent", "collection_id": "cid"}
    assert ("POST", "/api/v1/tools/create") in seen
    assert ("POST", "/api/v1/models/create") in seen
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_provision.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'owaw.owui.provision'`.

- [ ] **Step 3: Write the provisioner**

Create `src/owaw/owui/provision.py`:

```python
"""Provision the OpenWebUI Doc Agent: upsert the Doc Tool + Workspace Model.

This is the ONLY SP3 OpenWebUI API egress. Endpoint paths, body shapes, and the
access-control representation are confirmed by the SP3 validation spike against the
deployed OpenWebUI version (docs/superpowers/specs/2026-06-20-sp3-openwebui-api-findings.md).
The retry/backoff pattern mirrors owaw.knowledge.OpenWebUIKnowledgeClient.
"""
from __future__ import annotations

import os
import time
from importlib.resources import files

import httpx

from owaw.config import AgentConfig, OpenWebUIConfig


def _public_grants() -> list[dict]:
    """Public read for all users. Version-sensitive — see the Task 4 findings doc."""
    return [{"principal_type": "user", "principal_id": "*", "permission": "read"}]


def doc_tool_source() -> str:
    return files("owaw.owui").joinpath("doc_tool.py").read_text(encoding="utf-8")


def agent_system_prompt() -> str:
    return files("owaw.prompts").joinpath("agent_query.md").read_text(encoding="utf-8")


class OpenWebUIProvisioner:
    def __init__(self, base_url: str, token: str, *,
                 http: httpx.Client | None = None, sleep=time.sleep, retries: int = 3):
        self._token = token
        self._sleep = sleep
        self._retries = retries
        self._http = http or httpx.Client(base_url=base_url, timeout=30.0)

    def _request(self, method: str, path: str, **kw) -> httpx.Response:
        headers = kw.pop("headers", {})
        headers = {"Authorization": f"Bearer {self._token}", **headers}
        last: Exception | None = None
        for attempt in range(self._retries):
            try:
                resp = self._http.request(method, path, headers=headers, **kw)
            except httpx.TransportError as e:
                last = e
                self._sleep(0.5 * (2 ** attempt))
                continue
            if resp.status_code >= 500:
                last = httpx.HTTPStatusError("server error", request=resp.request, response=resp)
                self._sleep(0.5 * (2 ** attempt))
                continue
            resp.raise_for_status()   # 4xx -> raises immediately, NOT retried
            return resp
        raise RuntimeError(f"OpenWebUI request failed after {self._retries} tries: {last}")

    def upsert_tool(self, tool_id: str, name: str, content: str, description: str,
                    public: bool = True) -> str:
        body = {
            "id": tool_id,
            "name": name,
            "content": content,
            "meta": {"description": description},
            "access_grants": _public_grants() if public else [],
        }
        try:
            self._request("POST", "/api/v1/tools/create", json=body)
        except httpx.HTTPStatusError as e:
            if e.response.status_code not in (400, 409):
                raise
            self._request("POST", f"/api/v1/tools/id/{tool_id}/update", json=body)
        return tool_id

    def set_tool_valves(self, tool_id: str, valves: dict) -> None:
        self._request("POST", f"/api/v1/tools/id/{tool_id}/valves/update", json=valves)

    def resolve_collection_id(self, name: str) -> str | None:
        for c in self._request("GET", "/api/v1/knowledge/").json():
            if c.get("name") == name:
                return c["id"]
        return None

    def upsert_model(self, *, model_id: str, name: str, base_model: str, system_prompt: str,
                     collection_id: str | None, collection_name: str, tool_id: str,
                     public: bool = True) -> str:
        meta = {
            "description": "AI wiki documentation agent",
            "toolIds": [tool_id],
            "knowledge": [],
            "capabilities": {"builtin_tools": True, "file_context": True},
        }
        if collection_id:
            meta["knowledge"] = [
                {"id": collection_id, "name": collection_name, "type": "collection"}
            ]
        body = {
            "id": model_id,
            "base_model_id": base_model,
            "name": name,
            "meta": meta,
            "params": {"system": system_prompt, "function_calling": "native"},
            "access_grants": _public_grants() if public else [],
            "is_active": True,
        }
        try:
            self._request("POST", "/api/v1/models/create", json=body)
        except httpx.HTTPStatusError as e:
            if e.response.status_code not in (400, 409):
                raise
            self._request("POST", "/api/v1/models/model/update", json=body)
        return model_id

    @classmethod
    def from_config(cls, ow: OpenWebUIConfig) -> "OpenWebUIProvisioner":
        token = os.environ.get(ow.api_token_env, "")
        return cls(base_url=ow.base_url, token=token)


def provision_agent(ow: OpenWebUIConfig, agent: AgentConfig, *,
                    provisioner: OpenWebUIProvisioner | None = None) -> dict:
    p = provisioner or OpenWebUIProvisioner.from_config(ow)
    p.upsert_tool(
        agent.tool_id, agent.tool_name, doc_tool_source(),
        "Read-only jailed access to the AI wiki and sources", public=agent.public,
    )
    p.set_tool_valves(agent.tool_id, {
        "roots": ",".join(agent.doc_roots),
        "max_read_bytes": agent.max_read_bytes,
        "max_results": agent.max_results,
    })
    cid = p.resolve_collection_id(ow.collection)
    p.upsert_model(
        model_id=agent.model_id, name=agent.model_name, base_model=agent.base_model,
        system_prompt=agent_system_prompt(), collection_id=cid,
        collection_name=ow.collection, tool_id=agent.tool_id, public=agent.public,
    )
    return {"tool_id": agent.tool_id, "model_id": agent.model_id, "collection_id": cid}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_provision.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/owaw/owui/provision.py tests/test_provision.py
git commit -m "feat(sp3): OpenWebUI provisioner — upsert Doc Tool + Workspace Model"
```

---

## Task 6: CLI — `owaw owui-provision`

**Files:**
- Modify: `src/owaw/cli.py`
- Create: `tests/test_provision_cli.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_provision_cli.py`:

```python
from typer.testing import CliRunner

from owaw.cli import app

runner = CliRunner()

_CONFIG = (
    "generation:\n  model: m\n  base_url: u\n"
    "openwebui:\n  base_url: http://owui:8080\n  collection: ai-wiki\n"
    "agent:\n  base_model: gpt-4o\n"
)


def test_owui_provision_calls_provisioner(tmp_path, monkeypatch):
    monkeypatch.setenv("OWAW_DATA_DIR", str(tmp_path))
    (tmp_path / "config.yaml").write_text(_CONFIG, encoding="utf-8")

    called = {}

    def fake_provision(ow, agent, **kw):
        called["ok"] = (ow.collection, agent.base_model)
        return {"tool_id": "wiki_docs", "model_id": "ai-wiki-agent", "collection_id": "cid"}

    monkeypatch.setattr("owaw.owui.provision.provision_agent", fake_provision)
    r = runner.invoke(app, ["owui-provision"])
    assert r.exit_code == 0, r.output
    assert called["ok"] == ("ai-wiki", "gpt-4o")
    assert "ai-wiki-agent" in r.output


def test_owui_provision_errors_without_agent(tmp_path, monkeypatch):
    monkeypatch.setenv("OWAW_DATA_DIR", str(tmp_path))
    (tmp_path / "config.yaml").write_text(
        "generation:\n  model: m\n  base_url: u\n"
        "openwebui:\n  base_url: http://owui:8080\n  collection: ai-wiki\n",
        encoding="utf-8",
    )
    r = runner.invoke(app, ["owui-provision"])
    assert r.exit_code == 1
    assert "agent" in r.output
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_provision_cli.py -v`
Expected: FAIL — `No such command 'owui-provision'` (exit code 2).

- [ ] **Step 3: Add the command**

In `src/owaw/cli.py`, add after the `sync_watch` command (before `if __name__ == "__main__":`):

```python
@app.command("owui-provision")
def owui_provision():
    """Create/update the OpenWebUI Doc Agent (Tool + Workspace Model)."""
    from owaw.owui.provision import provision_agent

    cfg = load_config(paths.config_path())
    if cfg.openwebui is None:
        typer.echo("Error: no 'openwebui' section in config.yaml", err=False)
        raise typer.Exit(code=1)
    if cfg.agent is None:
        typer.echo("Error: no 'agent' section in config.yaml", err=False)
        raise typer.Exit(code=1)
    res = provision_agent(cfg.openwebui, cfg.agent)
    typer.echo(
        f"provisioned: tool={res['tool_id']} model={res['model_id']} "
        f"collection={res['collection_id']}"
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_provision_cli.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/owaw/cli.py tests/test_provision_cli.py
git commit -m "feat(sp3): owui-provision CLI command"
```

---

## Task 7: Deploy — OpenWebUI mounts + provisioning guide

> The Doc Tool reads `/data/wiki` and `/data/sources` **inside the OpenWebUI container**, so the OpenWebUI service (in the `minipc-traefik` stack — not in this repo's compose snippet) must mount the wiki + sources read-only. This task documents those mounts, the one-shot provisioning command, and the manual end-to-end checklist from spec §8 (including the shared/public-visibility check that resolves spec finding F-003). No code, so no TDD; verification is the documented commands plus a clean full-suite run.

**Files:**
- Create: `docs/deploy/sp3-openwebui-agent.md`

- [ ] **Step 1: Write the deploy guide**

Create `docs/deploy/sp3-openwebui-agent.md`:

````markdown
# SP3 — OpenWebUI Doc Agent — Deployment

The Doc Agent is a shared OpenWebUI Workspace Model plus a read-only Doc Tool. It reuses
`chat.ikeniborn.ru` (no new route) and the SP2 `ai-wiki` Knowledge collection.

## 1. Mount the wiki + sources into OpenWebUI (read-only)

The Doc Tool reads files **inside the OpenWebUI container**. Add these volumes to the
`openwebui` service in the `minipc-traefik` stack (paths must match `agent.doc_roots` in
`config.yaml`):

```yaml
  # openwebui service (minipc-traefik stack) — add:
    volumes:
      - owaw_data:/data:ro                                   # provides /data/wiki, read-only
      - /opt/minipc-docs:/data/sources/minipc-docs:ro        # same source bind as owaw, read-only
```

`owaw_data` is the volume SP1/SP2 already write; mounting it `:ro` exposes `/data/wiki`.
Mount each configured source root under `/data/sources/...` to match `doc_roots`.

## 2. Configure the agent

Set the `agent:` section in `config.yaml` (see `config.sample.yaml`). `base_model` is the
LiteLLM chat model id the agent wraps; `doc_roots` are the in-container mount paths above.

`OWAW_OPENWEBUI_TOKEN` (an OpenWebUI API key, Settings → Account) must be in `owaw.conf` —
the same env file SP2 uses.

## 3. Provision the Tool + Model

One-shot, idempotent (re-run to update):

```bash
docker compose run --rm owaw owui-provision
```

This upserts the `wiki_docs` Tool (with valves set from `doc_roots`), resolves the `ai-wiki`
collection, and upserts the public `ai-wiki-agent` Workspace Model (ported system prompt +
attached knowledge + tool + native function-calling).

## 4. Manual end-to-end checklist (spec §8)

- [ ] In OpenWebUI, the **Doc Agent** model is visible to a non-admin user (shared/public works).
- [ ] Ask a conceptual question answerable from the wiki → answer cites pages as `[[wikilinks]]` in the `query.md` format.
- [ ] Ask for an exact string only in a source file → the agent calls `search_docs` and returns the file:line.
- [ ] Request a path outside the roots (e.g. `read_doc("../../etc/passwd")`) → tool refuses with an "escapes the configured roots" message.
- [ ] Confirm RAG context is used (or, under native function-calling, the agent calls the tools) — adjust the knowledge attachment mode per the Task 4 findings if context is missing.
````

- [ ] **Step 2: Verify the suite is still green**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (all tests, including every SP3 test added above).

- [ ] **Step 3: Commit**

```bash
git add docs/deploy/sp3-openwebui-agent.md
git commit -m "docs(sp3): OpenWebUI mounts + provisioning + E2E deploy guide"
```

---

## Task 8: Finalize — wiki docs + full verification

> Per the project's CLAUDE.md, regenerate the `docs/wiki/` pages for the new subsystem and lint the doc graph. Then run the full suite once more as a final gate.

**Files:**
- Generated by iwiki under `docs/wiki/` (do not hand-write).

- [ ] **Step 1: Full suite + editable reinstall**

Run:
```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```
Expected: PASS (entire suite, ~fast).

- [ ] **Step 2: Regenerate the wiki pages for SP3**

Use the iwiki skill (not raw engine subcommands) to ingest the new/changed sources:
- `iwiki:iwiki-ingest src/owaw/owui/doc_tool.py`
- `iwiki:iwiki-ingest src/owaw/owui/provision.py`
- `iwiki:iwiki-ingest src/owaw/cli.py`
- `iwiki:iwiki-ingest src/owaw/config.py`

- [ ] **Step 3: Lint the doc graph**

Run `/iwiki-lint` (the config-free `iwiki_engine lint`). Expected: no broken `[[refs]]`, no orphan or stale pages for the SP3 additions. Fix any reported issues.

- [ ] **Step 4: Commit the docs**

```bash
git add docs/wiki
git commit -m "docs(wiki): document SP3 OpenWebUI agent subsystem (doc tool + provisioner)"
```

- [ ] **Step 5: Final review handoff**

Hand off to the final code-review stage (subagent-driven-development) and then
`superpowers:finishing-a-development-branch`.

---

## Self-review (against the spec)

**Spec coverage:**
- §2 Doc Tool (`list_docs`/`read_doc`/`search_docs`, read-only, jailed, size caps, PDF→RAG note) → Task 2.
- §2 Mounts (`wiki/` + source roots `:ro` into OpenWebUI) → Task 7.
- §2 Workspace Model (base model + ported `query.md` prompt + Knowledge attached + Tool enabled + shared) → Tasks 3 (prompt), 5 (provisioner attaches knowledge+tool, public), 6 (CLI).
- §2 Deployment (config + Tool install + Model definition, reuse `chat.ikeniborn.ru`) → Tasks 5–7.
- §6 Error handling (escape→reject, too-large→truncate, missing/binary messages, RAG-empty→tool fallback) → Task 2 (tool behaviors) + prompt instruction (Task 3) for fallback.
- §7 Security (read-only, realpath jail, fixed-pattern search/no injection, size caps, no new route) → Task 2; mounts `:ro` → Task 7.
- §8 Testing (jailing, list/read/search, size-cap, binary/missing unit tests; manual E2E incl. shared-visibility) → Task 2 + Task 7 checklist.
- §9 Open questions: Tools API → Task 4 spike; base chat model → `agent.base_model` config (Task 1); PDF/Office → defer-to-RAG (Task 2); provisioning → API (Tasks 5–6).

**Spec advisory findings addressed:** F-001 (grep/ripgrep wording) — deviation to pure-Python documented; F-002 (unquantified caps) — `max_read_bytes`/`max_results`/`base_model` quantified in Task 1; F-003 (no shared-visibility test) — added to Task 7 E2E checklist.

**Deviations (intentional, see Design decisions):** search uses pure-Python instead of `ripgrep`.

**Placeholder scan:** every code step contains complete code; commands have expected output; the spike (Task 4) and deploy/docs tasks (7, 8) are explicitly non-TDD with concrete deliverables and verification.

**Type consistency:** `AgentConfig`/`OpenWebUIConfig` fields, the `_resolve_within`/`_list_docs`/`_read_doc`/`_search_docs` signatures, and the provisioner method signatures are used identically across Tasks 1, 2, 5, 6.
