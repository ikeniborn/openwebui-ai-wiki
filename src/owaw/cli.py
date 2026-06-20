"""Typer CLI: init, ingest, rebuild, domain add/list, watch."""
from __future__ import annotations

import typer

from owaw import paths
from owaw.config import load_config
from owaw.domains import Domain, add_domain, load_domains
from owaw.ingest import ingest_domain, rebuild_domain
from owaw.index import rebuild_index
from owaw.llm import LLM

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


if __name__ == "__main__":
    app()
