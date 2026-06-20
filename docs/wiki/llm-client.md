# LLM client

`llm.py` is the single transport to the generation LLM over LiteLLM's OpenAI-compatible API, with a JSON-object guarantee. Both synthesis phases depend on it — see [[entity-page-synthesis#Entity extraction (entities.py)]]. It is the only SP1 module that performs LLM egress.

## LLM client

`LLM` wraps an OpenAI-compatible client and a model id. `_complete(prompt)` sends a single user message at `temperature=0.2` and returns the message content (or `""`). The class exposes `chat_json` as its public entry point.

The client is OpenAI-protocol but pointed at LiteLLM, so the actual generation backend (a cloud model, Anthropic, ollama `*:cloud`, …) is chosen by config, not code. SP1 only ever calls the chat-completions endpoint; embedding is an SP2 concern — see [[architecture#Three subsystems]].

## Constructing the client

`LLM.from_config(gen)` builds the client from a `GenerationConfig`: it reads the API key from the env var named by `gen.api_key_env` (default `OWAW_LLM_KEY`), constructs `OpenAI(base_url=gen.base_url, api_key=...)`, and uses `gen.model`. The `openai` import is lazy, inside the method.

Keeping the key in an env var (named in config, valued in the environment) means secrets never touch `config.yaml`. The config shape is documented in [[domain-model#Configuration (config.py)]]; deployment wiring in [[deployment#Configuration files]].

## JSON with retry

`chat_json(prompt)` returns a parsed `dict`, repairing one bad response before giving up. It calls `_complete`, parses via `_extract_json`; on `JSONDecodeError`/`ValueError` it re-asks with a repair suffix demanding a single valid JSON object, parses again, and raises `ValueError` if still invalid.

`_extract_json` strips a surrounding ```` ```lang ```` code fence (via `_FENCE_RE`) before `json.loads`, tolerating models that wrap JSON in fences. This mirrors the reference's `parse-with-retry` + `repair-json` behavior and is what makes [[entity-page-synthesis#Prompt templates]] safe to rely on returning structured data.
