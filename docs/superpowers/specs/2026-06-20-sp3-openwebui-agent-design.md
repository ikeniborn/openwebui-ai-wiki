---
review:
  spec_hash: 3055a1f4b76186da
  last_run: 2026-06-21
  phases:
    structure:   { status: passed }
    coverage:    { status: passed }
    clarity:     { status: passed }
    consistency: { status: passed }
  findings:
    - id: F-001
      phase: clarity
      severity: WARNING
      section: "1. Context / 4. Architecture and data flow / 5. Components / 7. Security"
      section_hash: a2ac1a96b19b2827
      text: >-
        Inconsistent term for the search mechanism: §1 and §4 say "grep", while §5
        and §7 say "ripgrep" for the same Doc Tool search_docs path. Same entity,
        two names.
      verdict: open
      verdict_at: null
    - id: F-002
      phase: clarity
      severity: WARNING
      section: "2. Goal and scope / 4. Architecture and data flow / 5. Components"
      section_hash: 7e8a21eb083bfa4b
      text: >-
        Unquantified acceptance criteria: "size caps", "top-k", and "configurable"
        base chat model appear without concrete values or a DoD. No numeric cap,
        no default top-k, no concrete default model are stated.
      verdict: open
      verdict_at: null
    - id: F-003
      phase: coverage
      severity: INFO
      section: "8. Testing"
      section_hash: f29c267f2ad0c2ec
      text: >-
        End-to-end verification of the "shared/public to all users" requirement
        (§2 in-scope, §7 security) is not covered by any test step; §8 tests RAG,
        Tool, jailing, and citations but not the sharing/visibility behavior.
      verdict: open
      verdict_at: null
chain:
  intent: null
---

# SP3 — OpenWebUI Agent — Design

- **Date:** 2026-06-20
- **Status:** Design (drafted from locked SP1 decisions; pending review)
- **Project:** `openwebui-ai-wiki` (future standalone repo) — see [`../../../README.md`](../../../README.md)
- **Subsystem:** SP3 of 3 (SP1 Wiki engine → SP2 Embedding+sync → **SP3 OpenWebUI agent**)
- **Depends on:** SP2 (the populated Knowledge collection) and SP1 (wiki + source files on disk) —
  [`2026-06-20-sp2-embedding-sync-design.md`](2026-06-20-sp2-embedding-sync-design.md)

## 1. Context

With the wiki + sources on disk (SP1) and a Knowledge collection kept current (SP2), SP3 exposes a
**shared "Doc Agent"** inside OpenWebUI that answers questions over the documentation. It is the
**hybrid** retrieval surface chosen in the SP1 brainstorm: OpenWebUI **RAG** (semantic search over
the bge-m3 Knowledge collection) plus a **live Tool** that reads the actual files on disk for exact
reads, grep, and current folder state without waiting for re-indexing. The agent's behavior (answer
strictly from the wiki, cite pages, strict markdown formatting) is ported from
`obsidian-ai-wiki/prompts/query.md`.

### Locked decisions carried in

- **Hybrid** retrieval: RAG (Knowledge) + Tool (live file read).
- **Shared** agent — available to **all** OpenWebUI users.
- Lives in the existing `minipc-traefik` stack; served via the existing `chat.ikeniborn.ru`
  route (no new public route).

## 2. Goal and scope

**Goal.** A shared OpenWebUI **Workspace Model** "Doc Agent" that answers documentation questions
using RAG over the wiki plus a jailed, read-only filesystem Tool, returning answers with citations
in the ported `query.md` style.

### In scope

- **Doc Tool** (OpenWebUI Python Tool): `list_docs(path)`, `read_doc(path)`, `search_docs(query)`
  over the mounted wiki + source roots. **Read-only**, **jailed** (resolved realpath must stay within
  the configured roots — no traversal, no absolute escape), with size caps. For PDF/Office in
  sources, returns a note to rely on RAG (optionally reuse Docling — see open questions).
- **Mounts:** the SP1 `wiki/` output and the configured source roots mounted **read-only** into the
  OpenWebUI container.
- **Workspace Model:** base = a LiteLLM chat model (configurable); system prompt = ported `query.md`
  (answer-from-wiki persona, `[[wikilinks]]` → citations, the strict code-block/table/list
  formatting rules); the Knowledge collection attached (auto-RAG context injection); the Doc Tool
  enabled; **shared/public** to all users.
- **Deployment** into the existing OpenWebUI service (config + Tool install + Model definition);
  reuses `chat.ikeniborn.ru`.

### Out of scope

- Wiki generation → **SP1**; embedding + collection sync → **SP2**.
- Authentication/user management — OpenWebUI's native auth already governs access (see the OpenWebUI
  guide); SP3 adds no new auth layer.

## 3. Reference mapping

| SP3 concern | Reference artifact |
|---|---|
| Agent system prompt (persona, citations, formatting) | `obsidian-ai-wiki/prompts/query.md` |
| Answer-structure / wikilink conventions | `prompts/query.md`, `prompts/chat.md` |

## 4. Architecture and data flow

```
browser → Traefik :443 → OpenWebUI (chat.ikeniborn.ru)
                          │
                   Doc Agent (Workspace Model)
                   ├─ system prompt: ported query.md
                   ├─ Knowledge: "ai-wiki"  ──RAG (bge-m3)──► top-k chunks → context
                   └─ Tool: Doc Tool ──read/list/search──► wiki/ + sources (mounted :ro, jailed)
                          │
                   LiteLLM :4000 (chat model)
```

1. A user asks the **Doc Agent** in OpenWebUI.
2. OpenWebUI RAG retrieves top-k chunks from the `ai-wiki` collection (bge-m3) and injects them as
   context.
3. The agent may call the **Doc Tool** to read a full page, grep an exact string, or inspect the
   live folder structure (no re-index needed).
4. It answers with citations, following the `query.md` formatting rules.

## 5. Components

| Component | Responsibility |
|---|---|
| `doc_tool.py` | OpenWebUI Tool — `list_docs` / `read_doc` / `search_docs`; jailed read-only FS access over the mounted roots; ripgrep with fixed args; size caps |
| Workspace Model config | base chat model + ported `query.md` system prompt + Knowledge attached + Tool enabled + shared to all |
| Mounts / env | `wiki/` and source roots mounted `:ro`; config for roots, base model, collection name |

## 6. Error handling

| Failure | Behavior |
|---|---|
| Tool path escapes the roots | Reject (no read); return a clear error |
| File too large | Truncate with a marker, or refuse with a size note |
| Missing / binary file | Clear "not found" / "binary — use RAG" message |
| RAG returns nothing | Agent falls back to the Tool (grep / read) and says so |
| LiteLLM chat model down | OpenWebUI surfaces the error to the user (no SP3-specific handling) |

## 7. Security

- The Doc Tool is **read-only** and **jailed** to the mounted roots (realpath containment); search
  uses `ripgrep` with fixed arguments (no shell injection); per-call size/result caps.
- The agent is **shared with all users**, so every user can read all wiki + source content — the
  corpus is intentionally shared (locked decision). Sensitive material must not be placed under the
  configured roots.
- No new public route; OpenWebUI native auth still gates access at `chat.ikeniborn.ru`.

## 8. Testing

- **Doc Tool (unit):** jailing (reject `../` and absolute escapes), `list_docs` / `read_doc` /
  `search_docs` over a fixture tree, size-cap behavior, binary/missing handling.
- **Manual end-to-end (OpenWebUI):** ask a question answerable from the wiki → verify RAG context is
  used, the Tool is callable, and the answer cites pages in the `query.md` format; ask for an exact
  string only present in a source file → verify the Tool grep path.

## 9. Open questions (validate early in implementation)

- **OpenWebUI Tools API.** Confirm the exact Tool definition format (function signatures, metadata,
  how a Tool is installed and bound to a Workspace Model) against the deployed OpenWebUI version.
- **Base chat model.** Which LiteLLM chat model backs the agent (config) — a local model vs an
  `ollama *:cloud` / Anthropic model; trade-off quality vs cost, consistent with SP1's
  configurable-default-cloud stance.
- **PDF/Office in the Tool.** Whether `read_doc` should transparently Docling-extract PDFs/Office for
  live reads, or always defer those to RAG. Default: defer to RAG; revisit if exact-quote reads from
  PDFs are needed.
- **Model/Tool provisioning.** Whether the Workspace Model + Tool are created via the OpenWebUI API
  (scriptable, reproducible) or admin UI; prefer API for repeatable deploys.
