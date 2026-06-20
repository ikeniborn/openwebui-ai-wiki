"""Typer CLI: init, ingest, rebuild, domain add/list, watch."""
from __future__ import annotations

import typer

from owaw import paths
from owaw.config import load_config
from owaw.domains import Domain, add_domain, load_domains
from owaw.ingest import ingest_domain, rebuild_domain
from owaw.index import rebuild_index
from owaw.knowledge import OpenWebUIKnowledgeClient
from owaw.llm import LLM
from owaw.sync import SyncEngine
from owaw.syncstate import SyncState

app = typer.Typer(help="openwebui-ai-wiki engine (SP1)")
domain_app = typer.Typer(help="Manage domains")
app.add_typer(domain_app, name="domain")


def _get_domain(domain_id: str) -> Domain:
    for d in load_domains(paths.domains_path()):
        if d.id == domain_id:
            return d
    raise typer.BadParameter(f"unknown domain: {domain_id}")


def _llm() -> LLM:
    cfg = load_config(paths.config_path())
    return LLM.from_config(cfg.generation)


def _sync_engine() -> SyncEngine:
    cfg = load_config(paths.config_path())
    if cfg.openwebui is None:
        raise typer.BadParameter("no 'openwebui' section in config.yaml; required for sync")
    client = OpenWebUIKnowledgeClient.from_config(cfg.openwebui, model=cfg.embedding.model)
    state = SyncState.load(paths.sync_state_path(cfg.openwebui.collection))
    return SyncEngine(client, state, paths.chunks_dir())


@domain_app.command("add")
def domain_add(
    id: str = typer.Option(...),
    name: str = typer.Option(...),
    wiki_folder: str = typer.Option(...),
    source: list[str] = typer.Option(..., help="Source path (repeatable)"),
):
    add_domain(
        Domain(id=id, name=name, wiki_folder=wiki_folder, source_paths=list(source), entity_types=[]),
        paths.domains_path(),
    )
    typer.echo(f"added domain '{id}'")


@domain_app.command("list")
def domain_list():
    for d in load_domains(paths.domains_path()):
        typer.echo(f"{d.id}\t{d.name}\t{len(d.source_paths)} source(s)")


@app.command()
def init(domain: str = typer.Option(...)):
    d = _get_domain(domain)
    paths.ensure_dirs(d.id)
    rebuild_index(paths.wiki_dir(d.id), d.name)
    typer.echo(f"initialised domain '{d.id}' at {paths.wiki_dir(d.id)}")


@app.command()
def ingest(domain: str = typer.Option(None, help="Domain id; omit for all")):
    domains = [_get_domain(domain)] if domain else load_domains(paths.domains_path())
    llm = _llm()
    cfg = load_config(paths.config_path())
    total = 0
    for d in domains:
        n = ingest_domain(llm, d, chunking=cfg.chunking)
        typer.echo(f"{d.id}: processed {n} file(s)")
        total += n
    typer.echo(f"done: {total} file(s)")


@app.command()
def rebuild(domain: str = typer.Option(...)):
    d = _get_domain(domain)
    cfg = load_config(paths.config_path())
    n = rebuild_domain(_llm(), d, chunking=cfg.chunking)
    typer.echo(f"rebuilt '{d.id}': {n} file(s)")


@app.command()
def watch(domain: str = typer.Option(None, help="Domain id; omit for all")):
    import time
    from owaw import paths as _paths
    from owaw.daemon import watch as watch_domain

    domains = [_get_domain(domain)] if domain else load_domains(_paths.domains_path())
    cfg = load_config(_paths.config_path())
    llm = _llm()

    def make_handler(d):
        def _on_change(_paths_changed):
            n = ingest_domain(llm, d, chunking=cfg.chunking)
            typer.echo(f"[watch] {d.id}: reingested, {n} file(s) changed")
        return _on_change

    observers = [watch_domain(d, cfg.debounce_ms, make_handler(d)) for d in domains]
    typer.echo(f"watching {len(domains)} domain(s); Ctrl-C to stop")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        for o in observers:
            o.stop()
        for o in observers:
            o.join()


@app.command()
def sync():
    """One-shot: full reconcile of the OpenWebUI collection against chunks/."""
    try:
        engine = _sync_engine()
    except typer.BadParameter as exc:
        typer.echo(f"Error: {exc}", err=False)
        raise typer.Exit(code=1)
    res = engine.reconcile()
    typer.echo(f"synced: +{res.added} -{res.deleted} ={res.unchanged}")


@app.command("sync-watch")
def sync_watch():
    """Daemon: reconcile on start, then sync on every chunks/ change (debounced)."""
    import time
    from owaw.daemon import watch_paths

    cfg = load_config(paths.config_path())
    engine = _sync_engine()
    res = engine.reconcile()
    typer.echo(f"[sync-watch] startup reconcile: +{res.added} -{res.deleted} ={res.unchanged}")

    cdir = paths.chunks_dir()
    cdir.mkdir(parents=True, exist_ok=True)

    def _on_change(_changed):
        r = engine.sync()
        typer.echo(f"[sync-watch] synced: +{r.added} -{r.deleted}")

    observer = watch_paths([str(cdir)], cfg.sync.debounce_ms, _on_change)
    typer.echo(f"[sync-watch] watching {cdir}; Ctrl-C to stop")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    app()
