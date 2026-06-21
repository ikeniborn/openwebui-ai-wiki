# OpenWebUI agent

SP3 of three — the shared "Doc Agent" inside OpenWebUI. One subsystem of three (see [[architecture#Three subsystems]]); depends on the populated collection from [[embedding-and-sync#OpenWebUI Knowledge client (knowledge.py)]].

## OpenWebUI agent

A shared OpenWebUI Workspace Model with a read-only, jailed filesystem Tool over the mounted wiki + sources, the ported `query.md` system prompt, and the SP2 `ai-wiki` Knowledge collection attached for RAG. It is the **hybrid** retrieval surface: semantic RAG plus live file reads, provisioned reproducibly by a tested API client.

## Doc Tool (owui/doc_tool.py)

A **self-contained single-file** OpenWebUI Python Tool (stdlib + pydantic only — no `owaw` imports, enforced by a test, because OpenWebUI stores and exec's the file standalone). It gives the agent three read-only methods: `search_docs(query)`, `read_doc(path)`, `list_docs(path)`. Retrieval is **pure-Python** (`rglob` + `re`, literal `re.escape` patterns) — no `ripgrep`, so no extra binary is needed in the OpenWebUI container.

## Jail and caps (owui/doc_tool.py)

All three surfaces are jailed by **realpath containment**: `_resolve_within` collapses a path with `Path.resolve()` and rejects it unless it stays under a configured root, so `../` traversal, absolute escape, and symlink escape all fail. `search_docs` applies the same `_contained` check per file, so an in-root symlink to an external file cannot leak its content. `read_doc` enforces a byte cap (truncates with a marker), refuses binary files (null-byte scan), and defers PDF/Office to RAG. Roots and caps are set via the Tool's pydantic `Valves`.

## Provisioner (owui/provision.py)

`OpenWebUIProvisioner` is the **only** SP3 OpenWebUI API egress — it mirrors the httpx retry/backoff style of [[embedding-and-sync#OpenWebUI Knowledge client (knowledge.py)]] (retry on transport errors + 5xx; 4xx raises). `provision_agent(ow, agent)` orchestrates: `upsert_tool` (full Python source in `content`, public `access_grants`), `set_tool_valves` (roots/caps from config), `resolve_collection_id` (match the `ai-wiki` name to its id), and `upsert_model`. Create-vs-update is decided by a GET existence check (`_exists`), since a duplicate id returns an ambiguous 400.

## Workspace Model (owui/provision.py)

`upsert_model` builds OpenWebUI's `ModelForm`: `base_model_id` (the wrapped LiteLLM chat model), `params.system` (the ported prompt), `meta.toolIds` attaching the Doc Tool, `meta.knowledge` attaching the `ai-wiki` collection as `{id, name, type:"collection"}`, and a public-read `access_grants` wildcard so all users see it. It deliberately omits `params.function_calling: "native"` — native mode disables OpenWebUI's automatic knowledge (RAG) injection, the agent's primary retrieval path. The exact 0.9.6 API shapes are recorded in the spike findings under `docs/superpowers/specs/`.

## System prompt (prompts/agent_query.md)

The Doc Agent persona, shipped as package data and read by the provisioner via `importlib.resources`. It is ported from the reference `obsidian-ai-wiki/prompts/query.md`: answer strictly from the wiki, cite source pages as wiki-links, and follow the strict formatting rules (fenced code with language tags, lists over inline enumerations, tables for tabular data). It instructs the agent to use both RAG and the Doc Tool, preferring `search_docs`/`read_doc` for exact values and current folder state.

## Configuration (config.py)

`AgentConfig` extends the shared config — see [[domain-model#Configuration (config.py)]] — and is `None` when the `agent:` section is absent. Fields: `base_model` (required), `model_id`/`model_name`, `tool_id`/`tool_name`, `doc_roots` (the in-container mount paths the Tool jails to), `max_read_bytes`, `max_results`, and `public`. The OpenWebUI base URL, collection name, and API token env var are reused from the SP2 `OpenWebUIConfig`; the token value stays in the environment, never the file.

## CLI and deployment (cli.py)

`owaw owui-provision` loads the config, guards the `openwebui`/`agent` sections, and runs `provision_agent` — one idempotent command, re-runnable to update. See [[cli-and-daemon#CLI]]. Deployment adds read-only mounts of `wiki/` and the source roots into the existing OpenWebUI container (no new public route; OpenWebUI's native auth gates access at `chat.ikeniborn.ru`) and runs the provision command once. The mount layout and a manual end-to-end checklist live under `docs/deploy/` — see [[deployment#Compose wiring]].
