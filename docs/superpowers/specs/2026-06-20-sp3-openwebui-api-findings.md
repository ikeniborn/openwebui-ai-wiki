# SP3 — OpenWebUI Tools/Models/Knowledge API Findings (Spike)

- **Date:** 2026-06-20
- **Spike for:** SP3 provisioner (Task 5)
- **OpenWebUI version:** `0.9.6` (image `ghcr.io/open-webui/open-webui:main`, confirmed via
  `docker exec minipc-traefik-openwebui cat /app/package.json`)
- **Sources:** live deployed container source under `/app/backend/open_webui/`
  - `routers/tools.py`, `routers/models.py`, `routers/knowledge.py`
  - `models/tools.py`, `models/models.py`, `models/access_grants.py`
  - `utils/middleware.py`, `utils/automations.py`, `routers/openai.py`

---

## 1. Tool endpoints

### 1.1 Create tool

```
POST /api/v1/tools/create
Authorization: Bearer <API_KEY>
Content-Type: application/json

{
  "id":      "doc_tool",          // must be a valid Python identifier (isidentifier()); lowercased server-side
  "name":    "Doc Tool",
  "content": "<full Python source>",   // server exec's it to derive specs; load_tool_module_by_id()
  "meta": {
    "description": "...",
    "manifest":    {}             // optional; server overwrites with parsed frontmatter
  },
  "access_grants": [...]          // see §4
}
```

**Delta from seed:** seed said `access_grants` — **confirmed correct**. No `specs` field in the
request form (`ToolForm`); server derives specs from `content` via `get_tool_specs()` and stores
them itself. `meta.manifest` is also derived by the server (frontmatter parse); caller may omit it.

**Idempotency note:** endpoint returns `400 ID_TAKEN` if the id already exists — not a 409. The
provisioner must check existence first via `GET /api/v1/tools/id/{id}` (returns 404 when absent)
and branch to update.

### 1.2 Update tool

```
POST /api/v1/tools/id/{id}/update
Authorization: Bearer <API_KEY>
Content-Type: application/json

{
  "id":      "doc_tool",
  "name":    "Doc Tool",
  "content": "<full Python source>",
  "meta":    { "description": "..." },
  "access_grants": [...]
}
```

**Delta from seed:** seed hypothesized this path — **confirmed correct**. Same `ToolForm` shape as
create. `specs` and `meta.manifest` are re-derived server-side on every update.

### 1.3 Update tool valves (admin-level, server-side)

```
POST /api/v1/tools/id/{id}/valves/update
Authorization: Bearer <API_KEY>
Content-Type: application/json

{
  "WIKI_ROOT": "/data/wiki",
  "SOURCES_ROOT": "/data/sources"
}
```

Body is a flat dict of valve key→value pairs (the `Valves` Pydantic model's fields). Server
validates them through `Valves(**form_data)`. `None` values are stripped before validation.

**Delta from seed:** seed said `POST .../valves/update` with a flat dict body — **confirmed
correct**. No wrapper key; the dict IS the body.

### 1.4 Update tool access separately (optional)

A dedicated endpoint exists for access-only updates without re-sending content:

```
POST /api/v1/tools/id/{id}/access/update
Authorization: Bearer <API_KEY>
Content-Type: application/json

{ "access_grants": [...] }
```

This is useful for a two-step upsert: content first, then grants. Not in the seed — new finding.

---

## 2. Model endpoints

### 2.1 Create workspace model

```
POST /api/v1/models/create
Authorization: Bearer <API_KEY>
Content-Type: application/json

{
  "id":            "doc-agent",
  "base_model_id": "litellm/gpt-4o",
  "name":          "Doc Agent",
  "meta": {
    "description": "...",
    "toolIds":  ["doc_tool"],
    "knowledge": [
      { "id": "<knowledge-collection-id>", "name": "ai-wiki", "type": "collection" }
    ]
  },
  "params": {
    "system":            "<system prompt text>",
    "function_calling":  "native"
  },
  "access_grants": [...],
  "is_active": true
}
```

**Field name findings (critical):**

| Field | Status | Notes |
|-------|--------|-------|
| `meta.toolIds` | **camelCase confirmed** | `automations.py:238` `model.get('info',{}).get('meta',{}).get('toolIds', [])`. The comment says "The frontend does this in Chat.svelte (model.info.meta.toolIds)". snake_case `tool_ids` is the per-request chat metadata field, not the stored model meta field. |
| `meta.knowledge` | **list of dicts confirmed** | Each item: `{"id": "<cid>", "name": "...", "type": "collection"}`. Legacy items have `collection_name` (single) or `collection_names` (multi) instead of `id` — do NOT use those; they trigger legacy-fallback paths. |
| `params.system` | **confirmed** | `openai.py:1092` `system = params.pop('system', None)` → `apply_system_prompt_to_body()`. Stored in `ModelParams` (extra='allow'). |
| `params.function_calling` | **confirmed** | `"native"` enables OpenAI-native tool calling; `"default"` or absent uses OpenWebUI's proxy function-calling template. |

**Idempotency:** returns `400 MODEL_ID_TAKEN` if id already exists. Check existence first via
`GET /api/v1/models/model?id={id}` (returns 404 when absent).

### 2.2 Update workspace model

```
POST /api/v1/models/model/update
Authorization: Bearer <API_KEY>
Content-Type: application/json

{
  "id":            "doc-agent",
  "base_model_id": "litellm/gpt-4o",
  "name":          "Doc Agent",
  "meta":    { ... },
  "params":  { ... },
  "access_grants": [...],
  "is_active": true
}
```

**Delta from seed:** seed said this path and `ModelForm` shape — **confirmed correct**.

### 2.3 Get model (existence check)

```
GET /api/v1/models/model?id=doc-agent
Authorization: Bearer <API_KEY>
```

Note: path uses a query parameter, not a path segment, to allow `/` in model ids. Returns 404 when
not found.

---

## 3. Knowledge endpoint

### 3.1 List collections (resolve id by name)

```
GET /api/v1/knowledge/
Authorization: Bearer <API_KEY>
```

Returns a list of knowledge objects. Each has `id` and `name`. Match by `name` to obtain `id`.
This is the pattern already established in `src/owaw/knowledge.py:77`.

**Delta from seed:** confirmed — no changes needed.

---

## 4. Access control field: `access_grants` (list, NOT `access_control` dict)

OpenWebUI 0.9.6 uses `access_grants` — a **flat list** of grant objects. The old `access_control`
dict schema (`null` = public, `{}` = private) is a legacy representation that the server converts
internally via `access_control_to_grants()`. The API surface accepts ONLY `access_grants` in
`ToolForm` and `ModelForm`.

### Public-read representation (wildcard grant)

```json
[
  {
    "principal_type": "user",
    "principal_id":   "*",
    "permission":     "read"
  }
]
```

**How to read it:** `principal_id: "*"` is the wildcard; `principal_type: "user"` with `"*"` means
"all users". The `id` field in a grant object is optional in requests (server assigns a UUID if
absent); `resource_type` and `resource_id` are also server-assigned from context.

### Private (owner-only) representation

```json
[]
```

An empty list means no grants → owner-only access.

### Both representations side by side

| Intent | `access_grants` list |
|--------|----------------------|
| Public read | `[{"principal_type":"user","principal_id":"*","permission":"read"}]` |
| Private | `[]` |
| Group read | `[{"principal_type":"group","principal_id":"<group-id>","permission":"read"}]` |

**OLD style (do NOT send):**
```json
// access_control (old dict form — not accepted by ToolForm/ModelForm):
null           // was public
{}             // was private
```

The conversion functions `access_control_to_grants` and `grants_to_access_control` exist for the
server's own internal backward-compat logic (DB migration, frontend bridge). The provisioner must
always send the new list form.

---

## 5. Native function-calling and knowledge auto-injection

**Finding (definitive, from `utils/middleware.py:2488`):**

```python
if model_knowledge and metadata.get('params', {}).get('function_calling') != 'native':
    # ... inject knowledge files as RAG context
```

When `params.function_calling == "native"`, **knowledge auto-injection is DISABLED**. The model
does NOT automatically receive RAG context from the attached Knowledge collection. The same guard
applies to folder knowledge, web search, memory, image generation, and code interpreter.

**Implication for SP3's system prompt:**

The Doc Agent SHOULD NOT use `params.function_calling = "native"` if it relies on OpenWebUI's
automatic RAG injection from the attached `ai-wiki` knowledge collection. Native mode means the
model receives tool definitions via the OpenAI `tools` array and must call them itself — no
auto-inject happens.

**Recommended setting:** omit `params.function_calling` (or set to `"default"`). This enables:
- Automatic RAG injection from `meta.knowledge` items on each user query.
- OpenWebUI's built-in tool proxy for the Doc Tool (non-native calling via template).

Use `"native"` only if the base model reliably supports OpenAI function calling AND the Doc Tool is
written to be called as a native function (not just a Python class with docstring methods). For the
current Doc Tool design (class with `__user__`/`__event_emitter__` injections), non-native mode
is simpler and safer.

---

## 6. Authentication

All endpoints require:

```
Authorization: Bearer <API_KEY>
```

API key corresponds to an admin user. Non-admin users can create tools/models only if granted the
`workspace.tools` / `workspace.models` permission, but the provisioner runs as admin, so this
distinction is irrelevant for SP3.

---

## 7. Deltas for Task 5

The following are concrete changes the provisioner code (Task 5) and its MockTransport tests must
adopt relative to the seed hypotheses:

1. **`meta.toolIds` not `meta.tool_ids`** — the model meta field that attaches tools is camelCase
   `toolIds` (a list of tool id strings). Using snake_case `tool_ids` inside `meta` would silently
   store a field that the server ignores. Confirmed from `automations.py:238`.

2. **`access_grants` is a LIST, not a dict** — the seed was correct on the field name but the
   representation is a flat list of grant dicts (`[{principal_type, principal_id, permission}]`),
   not the old `access_control` dict. Public-read = `[{"principal_type":"user","principal_id":"*",
   "permission":"read"}]`. Private = `[]`. The `id` field per grant can be omitted (server adds
   UUID).

3. **No `specs` in ToolForm** — do not send `specs` in the tool create/update body. The server
   derives and stores specs itself from `content`. Sending it would be silently ignored (not in
   `ToolForm` schema) but is unnecessary.

4. **Existence check before create** — both tool and model create return `400` (not `409`) on
   duplicate id. The provisioner must issue `GET /api/v1/tools/id/{id}` (→404 when absent) and
   `GET /api/v1/models/model?id={id}` (→404 when absent) before deciding create vs update.

5. **Do NOT use `params.function_calling = "native"` for the Doc Agent** — native mode disables
   OpenWebUI's automatic knowledge RAG injection, which is the primary retrieval path for the Doc
   Agent. Leave `function_calling` absent or `"default"`.

6. **Knowledge item shape** — use `{"id": "<cid>", "name": "ai-wiki", "type": "collection"}`.
   Do NOT use the legacy `collection_name` key; it is a fallback that bypasses the current access-
   control check path.

7. **Tool valves body is a flat dict** — `POST .../valves/update` body is directly
   `{"KEY": "value", ...}`, not wrapped in `{"valves": {...}}`. Confirmed from router source.

8. **Seed item confirmed with no delta:** tool create path `POST /api/v1/tools/create`, tool update
   path `POST /api/v1/tools/id/{id}/update`, model create `POST /api/v1/models/create`, model
   update `POST /api/v1/models/model/update`, knowledge list `GET /api/v1/knowledge/`,
   `params.system` for system prompt, `Authorization: Bearer` header.
