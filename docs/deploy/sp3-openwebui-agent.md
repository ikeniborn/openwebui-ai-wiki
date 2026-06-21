# SP3 — OpenWebUI Doc Agent — Deployment

The Doc Agent is a shared OpenWebUI Workspace Model plus a read-only Doc Tool. It reuses
`chat.ikeniborn.ru` (no new route) and the SP2 `ai-wiki` Knowledge collection. API shapes are
recorded in [`../superpowers/specs/2026-06-20-sp3-openwebui-api-findings.md`](../superpowers/specs/2026-06-20-sp3-openwebui-api-findings.md)
(OpenWebUI 0.9.6).

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

One-shot, idempotent (re-run to update — the provisioner checks existence and updates in place):

```bash
docker compose run --rm owaw owui-provision
```

This upserts the `wiki_docs` Tool (with valves set from `doc_roots`), resolves the `ai-wiki`
collection, and upserts the public `ai-wiki-agent` Workspace Model (ported system prompt +
attached knowledge + attached tool). The model is left in OpenWebUI's **default** function-calling
mode (NOT `native`): native mode disables automatic knowledge/RAG injection, which is the Doc
Agent's primary retrieval path.

## 4. Manual end-to-end checklist

- [ ] In OpenWebUI, the **Doc Agent** model is visible to a non-admin user (shared/public works).
- [ ] Ask a conceptual question answerable from the wiki → the answer is grounded in auto-injected
      RAG context and cites pages as `[[wikilinks]]` in the `query.md` format. (If answers ignore
      the wiki, confirm the model is NOT in native function-calling mode — see the Task 4 findings.)
- [ ] Ask for an exact string only in a source file → the agent calls `search_docs` and returns the file:line.
- [ ] Read a known page via the tool → `read_doc` returns its content.
- [ ] Request a path outside the roots (e.g. `read_doc("../../etc/passwd")`) → the tool refuses with
      an "escapes the configured roots" message.
