# Development workflow

How to build, test, and run `owaw` locally, plus the documentation-maintenance loop that keeps `docs/wiki/` current. This is the contributor/agent-facing complement to the architecture pages; runtime command semantics live in [[cli-and-daemon#CLI]] and packaging in [[deployment#Packaging (pyproject.toml)]].

## Build and install

The project uses a hatchling build and targets Python ≥ 3.12. Develop against the in-repo virtualenv at `.venv/`, installing the package editable with the `dev` extra so tests and the `owaw` console script resolve.

```bash
.venv/bin/pip install -e ".[dev]"
```

Dependencies and the `owaw = owaw.cli:app` entry point are declared in `pyproject.toml` — see [[deployment#Packaging (pyproject.toml)]].

## Testing

The suite is fast (~65 tests, ~0.2s) and deterministic: the LLM transport and Docling are lazy-imported, so unit tests exercise the core without network or heavy extraction deps. There is no separate lint step configured.

```bash
.venv/bin/python -m pytest -q                          # full suite
.venv/bin/python -m pytest tests/test_chunking.py      # single file
.venv/bin/python -m pytest tests/test_ingest.py::test_name -q   # single test
```

Pytest is configured with `pythonpath=["src"]` and `testpaths=["tests"]` (in `pyproject.toml`), so imports resolve from `src/` without install. The deterministic-core design comes from the lazy imports described in [[ingest-pipeline#Text extraction]] and [[llm-client#LLM client]].

## Running the engine

The `owaw` CLI drives one-shot and admin commands; the daemon drives continuous autosync. Both operate over domains from `domains.yaml` and resolve artifacts under `$OWAW_DATA_DIR` (default `./data`). Full command table and daemon behavior: [[cli-and-daemon#CLI]].

```bash
owaw init --domain <id>      # materialize a domain's wiki structure
owaw ingest [--domain <id>]  # one-shot incremental ingest
owaw rebuild --domain <id>   # full drop + regenerate
owaw watch [--domain <id>]   # inotify daemon (default container CMD)
```

A bare `docker run` starts `owaw watch` over all domains — container wiring is in [[deployment#Container image (Dockerfile)]].

## Documentation maintenance

`docs/wiki/` is the authoritative architecture knowledge base, maintained via the **iwiki** skills, not by hand-editing the index. Start a task by querying the wiki for the relevant module before reading code; the pages encode the locked decisions and implementation deltas in [[architecture#Locked decisions]].

After any change to functionality, architecture, or behavior, regenerate the affected page with `iwiki:iwiki-ingest <changed-source>` and run `/iwiki-lint` (no broken `[[refs]]`, no orphan/stale pages) before finishing. Skip only pure formatting/typo changes. Always drive iwiki through its skills — never guess engine subcommands.
