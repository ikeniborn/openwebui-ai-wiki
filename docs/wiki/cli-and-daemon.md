# CLI and daemon

The two runtime entry points: the Typer CLI (`cli.py`) for one-shot and admin commands, and the inotify daemon (`daemon.py`) for continuous autosync. Both drive [[ingest-pipeline#Ingest pipeline]] over configured domains.

## CLI

`cli.py` builds a Typer app `owaw` (exposed as the `owaw` console script). Commands resolve domains from `domains.yaml` and build the LLM lazily from config. `_get_domain(id)` raises a `BadParameter` for unknown ids; `_llm()` constructs the client from `load_config(...).generation`.

| Command | Purpose |
|---|---|
| `init --domain <id>` | `ensure_dirs` + `rebuild_index` — materialize a domain's wiki structure |
| `ingest [--domain <id>]` | One-shot incremental ingest; all domains when omitted |
| `rebuild --domain <id>` | Full re-ingest (drop + regenerate) of one domain |
| `domain add` | Append a domain to `domains.yaml` (id/name/wiki_folder/source repeatable) |
| `domain list` | Print each domain's id, name, source count |
| `watch [--domain <id>]` | Run the daemon over one or all domains |

`ingest` and `rebuild` read `chunking` from config and delegate to `ingest_domain`/`rebuild_domain`. Domain CRUD goes through [[domain-model#domains.yaml persistence]].

## Watch command

`watch` wires each domain to the daemon. It builds the LLM and config once, then for each domain registers an on-change handler that re-runs `ingest_domain` and echoes how many files changed. It starts one observer per domain and blocks in a 1-second sleep loop until Ctrl-C, then stops and joins every observer.

The handler closure captures its domain (`make_handler(d)`) so distinct domains reingest independently. The debounce window comes from `cfg.debounce_ms`.

## Daemon (daemon.py)

`daemon.py` watches each domain's `source_paths` via `watchdog` (inotify) and coalesces bursts before reingesting. `watch(domain, debounce_ms, on_change)` creates a `Debouncer`, schedules a recursive handler on every source root, starts the `Observer`, and returns it for the caller to stop/join.

`_Handler.on_any_event` forwards non-directory events into the debouncer. Work is serialized per domain (one observer per domain), so concurrent page writes within a domain can't race — consistent with the per-domain manifest in [[ingest-pipeline#Idempotency and crash recovery]].

## Debouncer

`Debouncer(delay_ms, on_flush)` collects a unique set of changed paths and fires `on_flush` after `delay_ms` of quiet, or immediately via `flush_now()`. It is deliberately timer-free for tests: `flush_now` can be called directly to flush without waiting.

`add(item)` adds to the pending set and (re)arms a daemon `threading.Timer`; each new event cancels and restarts the timer, so a burst of edits collapses into one reingest. The lock guards the pending set and timer across the watcher thread and the timer thread.
