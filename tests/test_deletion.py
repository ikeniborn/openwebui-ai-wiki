from pathlib import Path
import owaw.ingest as ingest_mod
from owaw.ingest import ingest_domain
from owaw.domains import Domain
from owaw.entities import Entity
from owaw.pages import WikiPage
from owaw.chunkstore import ChunkStore
from owaw import paths


def _domain(src_dir):
    return Domain(id="infra", name="Infra", wiki_folder="infra",
                  source_paths=[str(src_dir)], entity_types=[])


def _stub_phases(monkeypatch, source_stem):
    monkeypatch.setattr(ingest_mod, "extract_entities",
                        lambda llm, d, text: [Entity(name="Traefik")])
    monkeypatch.setattr(ingest_mod, "synthesize_pages",
                        lambda llm, d, text, stem, ents, existing, today: [
                            WikiPage(
                                path="wiki_infra_traefik.md",
                                content=f"---\nwiki_sources: [\"[[{source_stem}]]\"]\n"
                                        f"wiki_status: stub\n---\n# Traefik\n\nbody",
                                annotation="a")])


def test_deleting_only_source_prunes_page_and_chunks(tmp_path, monkeypatch):
    monkeypatch.setenv("OWAW_DATA_DIR", str(tmp_path / "data"))
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    src = src_dir / "doc.md"
    src.write_text("# Doc", encoding="utf-8")
    _stub_phases(monkeypatch, "doc")

    assert ingest_domain(llm=object(), domain=_domain(src_dir)) == 1
    page = paths.wiki_dir("infra") / "wiki_infra_traefik.md"
    assert page.exists()
    assert ChunkStore(paths.chunks_path("infra"), domain="infra").read_all()

    src.unlink()  # delete the only source
    ingest_domain(llm=object(), domain=_domain(src_dir))  # reconcile prunes the orphan
    assert not page.exists()
    assert ChunkStore(paths.chunks_path("infra"), domain="infra").read_all() == []
