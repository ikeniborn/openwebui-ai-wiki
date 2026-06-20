# Deployment

How SP1 is packaged and run: the Python package metadata, the container image, the compose wiring into the existing `minipc-traefik` stack, and the sample config/domain files under `docs/deploy/`. Runtime behavior is in [[cli-and-daemon#CLI]].

## Packaging (pyproject.toml)

`pyproject.toml` declares the `owaw` package (hatchling build, Python ≥ 3.12). Dependencies: `typer`, `pyyaml`, `openai`, `docling`, `watchdog`; `pytest` under the `dev` extra. The `owaw` console script maps to `owaw.cli:app`.

Prompts are shipped as package data via `force-include` (`src/owaw/prompts/*.md` → `owaw/prompts/`), so the wheel install can load them with `importlib.resources` — see [[entity-page-synthesis#Prompt templates]]. Pytest is configured with `pythonpath=["src"]` and `testpaths=["tests"]`.

## Container image (Dockerfile)

The image is `python:3.12-slim`: copy `pyproject.toml` + `src`, `pip install .`, set `OWAW_DATA_DIR=/data`, declare `/data` as a volume, `ENTRYPOINT ["owaw"]` with default `CMD ["watch"]`.

So a bare `docker run` starts the daemon over all configured domains. `OWAW_DATA_DIR=/data` is where `paths.py` resolves the on-disk layout — see [[domain-model#Data layout (paths.py)]]. Other commands run by overriding the command (e.g. `owaw ingest`).

## Compose wiring

`docs/deploy/docker-compose.snippet.yml` adds an internal `owaw` service to the `minipc-traefik` stack — **no Traefik router** (not publicly routed). It restarts unless stopped and joins `proxy-net`.

Volumes: a named `owaw_data` volume at `/data` (wiki + chunks + state, shared with SP2/SP3) and source folders bind-mounted read-only and nested (e.g. `/opt/minipc-docs:/data/sources/minipc-docs:ro`). `extra_hosts` maps `host.docker.internal:host-gateway` so the container reaches LiteLLM on the host. The LLM key is injected via `env_file: ./owaw.conf` (chmod 600, not committed) — see [[llm-client#Constructing the client]].

## Configuration files

Two sample files under `docs/deploy/` show the runtime config shape. `config.sample.yaml` sets the generation model/`base_url`/`api_key_env`, chunking params, `extraction.engine: docling`, and `daemon.debounce_ms`. Parsed by [[domain-model#Configuration (config.py)]].

`domains.sample.yaml` shows one domain (`infra`) with a read-only source path, an `entity_types` entry (a `service` type with cues and `min_mentions_for_page: 2`), and `language_notes` flagging a mostly-Russian corpus (entity names kept verbatim). The domain schema is in [[domain-model#Domain model (domains.py)]]; the language note drives the slug transliteration in [[entity-page-synthesis#Frontmatter and slugs]].
