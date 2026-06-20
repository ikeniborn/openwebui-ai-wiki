# openwebui-ai-wiki

Server-side AI wiki engine + documentation agent for **OpenWebUI**.

Builds and maintains a structured wiki (domains, entities, cross-linked pages) from
configurable document sources, embeds it with a multilingual model, and exposes a shared
**Doc Agent** inside OpenWebUI that answers questions over the wiki and the live source files.

> Lineage: a Python, server-side reimagining of [`obsidian-ai-wiki`](../obsidian-ai-wiki)
> (an Obsidian plugin). That project is used as a **reference spec** — its prompts
> (`prompts/*.md`), chunking algorithm (`src/page-similarity.ts`), and phase logic — not as
> reused code. This project is a clean Python rewrite targeting the OpenWebUI/LiteLLM stack.

This folder is intended to become its **own standalone repository** later.

## Architecture — three subsystems

| # | Subsystem | Responsibility | Depends on |
|---|---|---|---|
| **SP1** | Wiki engine | Domains (sources → wiki), entity extraction, page generation/maintenance, Docling extraction for PDF/Office, section-aware chunking (port of `page-similarity`: section + summary + intra/inter-section overlap) | — |
| **SP2** | Embedding + sync | Chunks → bge-m3 embeddings (via LiteLLM) → one OpenWebUI Knowledge collection; autosync on change (inotify); deletions; hash manifest | SP1 |
| **SP3** | OpenWebUI agent | Doc Tool (live `read`/`list`/`search`, jailed read-only to source roots) + Workspace Model (ported `query.md` prompt + Knowledge + Tool), shared to all users | SP2 |

Each subsystem gets its own spec → plan → implementation cycle. Brainstorming order: SP1 first.

## Locked decisions

- **Engine strategy:** Z — rewrite the wiki engine in **Python** in the OpenWebUI stack
  (obsidian-ai-wiki = reference, not a dependency).
- **Embedding model:** configurable, default **bge-m3** (chosen for the Russian corpus);
  served via LiteLLM `/v1/embeddings`.
- **PDF/Office extraction:** **Docling**.
- **Knowledge granularity / sync trigger:** single Knowledge collection, **inotify**-driven autosync.
- **Agent retrieval:** hybrid — OpenWebUI RAG (semantic) + Tool (precise live file read).
- **Audience:** shared agent for all OpenWebUI users.
- **Sources:** configurable set of multiple folders, arbitrary nesting depth.
- **Host stack:** lives in the existing `minipc-traefik` deployment; no new public route
  (served via the existing `chat.ikeniborn.ru`).

## Status

- SP1 — implemented and merged to `master` (engine `src/owaw/`, tests, `docs/wiki/`).
- SP2 — design spec drafted (`docs/superpowers/specs/2026-06-20-sp2-embedding-sync-design.md`).
- SP3 — design spec drafted (`docs/superpowers/specs/2026-06-20-sp3-openwebui-agent-design.md`).
