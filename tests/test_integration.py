from pathlib import Path
import owaw.ingest as ingest_mod
from owaw.ingest import ingest_domain
from owaw.domains import Domain
from owaw.entities import Entity
from owaw.pages import WikiPage
from owaw.chunkstore import ChunkStore
from owaw import paths

FIXTURES = Path(__file__).parent / "fixtures" / "sources"


def test_end_to_end_produces_wiki_and_chunks(tmp_path, monkeypatch):
    monkeypatch.setenv("OWAW_DATA_DIR", str(tmp_path / "data"))
    domain = Domain(id="infra", name="Infra", wiki_folder="infra",
                    source_paths=[str(FIXTURES)], entity_types=[])

    monkeypatch.setattr(ingest_mod, "extract_entities",
                        lambda llm, d, text: [Entity(name="Traefik", type=None)])

    def fake_pages(llm, d, text, stem, ents, existing, today):
        body = ("---\nwiki_sources: [\"[[intro]]\"]\nwiki_status: stub\n---\n"
                "# Traefik\n\n## Role\nTLS termination and routing.")
        return [WikiPage(path="wiki_infra_traefik.md", content=body,
                         annotation="Traefik reverse proxy. Terms: tls, routing, ingress.")]

    monkeypatch.setattr(ingest_mod, "synthesize_pages", fake_pages)

    n = ingest_domain(llm=object(), domain=domain)
    assert n == 1

    page = paths.wiki_dir("infra") / "wiki_infra_traefik.md"
    assert page.exists()
    assert "TLS termination" in page.read_text(encoding="utf-8")
    assert (paths.wiki_dir("infra") / "_index.md").exists()

    rows = ChunkStore(paths.chunks_path("infra"), domain="infra").read_all()
    kinds = {r["kind"] for r in rows}
    assert kinds == {"summary", "section"}
    summary = next(r for r in rows if r["kind"] == "summary")
    assert summary["embed_text"].startswith("Traefik reverse proxy")
    section = next(r for r in rows if r["kind"] == "section")
    assert section["embed_text"].startswith("Traefik reverse proxy")  # annotation prepended
    assert "## Role" in section["embed_text"]


def test_second_run_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("OWAW_DATA_DIR", str(tmp_path / "data"))
    domain = Domain(id="infra", name="Infra", wiki_folder="infra",
                    source_paths=[str(FIXTURES)], entity_types=[])
    monkeypatch.setattr(ingest_mod, "extract_entities", lambda *a, **k: [Entity(name="Traefik")])
    monkeypatch.setattr(ingest_mod, "synthesize_pages",
                        lambda llm, d, text, stem, ents, existing, today: [
                            WikiPage(path="wiki_infra_traefik.md",
                                     content="---\nwiki_status: stub\n---\n# Traefik\n\nbody",
                                     annotation="a")])
    assert ingest_domain(llm=object(), domain=domain) == 1
    assert ingest_domain(llm=object(), domain=domain) == 0  # nothing changed
