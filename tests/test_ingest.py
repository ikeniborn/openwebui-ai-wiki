from pathlib import Path
import owaw.ingest as ingest_mod
from owaw.ingest import ingest_file
from owaw.domains import Domain, EntityType
from owaw.entities import Entity
from owaw.pages import WikiPage
from owaw.manifest import Manifest
from owaw.chunkstore import ChunkStore


class StubLLM:
    def chat_json(self, prompt):  # not used — phases are monkeypatched
        raise AssertionError("LLM should be stubbed at phase level")


def _domain(src_dir):
    return Domain(id="infra", name="Infra", wiki_folder="infra",
                  source_paths=[str(src_dir)],
                  entity_types=[EntityType(type="service", description="d", extraction_cues=[])])


def test_ingest_file_writes_page_index_and_chunks(tmp_path, monkeypatch):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    src = src_dir / "doc.md"
    src.write_text("# Doc\n\n## Role\nTraefik proxies traffic.", encoding="utf-8")

    wiki_dir = tmp_path / "wiki" / "infra"
    wiki_dir.mkdir(parents=True)
    chunks = ChunkStore(tmp_path / "chunks" / "infra.jsonl", domain="infra")
    manifest = Manifest.load(tmp_path / "manifest.json")

    monkeypatch.setattr(ingest_mod, "extract_entities",
                        lambda llm, d, text: [Entity(name="Traefik", type="service")])
    monkeypatch.setattr(ingest_mod, "synthesize_pages",
                        lambda llm, d, text, stem, ents, existing, today: [
                            WikiPage(path="wiki_infra_traefik.md",
                                     content="---\nwiki_status: stub\n---\n# Traefik\n\n## Role\nproxy",
                                     annotation="Traefik proxy. Terms: ingress.")])

    changed = ingest_file(StubLLM(), _domain(src_dir), src, wiki_dir, chunks, manifest)

    assert changed is True
    assert (wiki_dir / "wiki_infra_traefik.md").exists()
    assert (wiki_dir / "_index.md").exists()
    rows = chunks.read_all()
    assert {r["page_id"] for r in rows} == {"wiki_infra_traefik"}
    assert any(r["kind"] == "summary" for r in rows)
    assert manifest.is_changed(src) is False  # marked processed


def test_ingest_file_skips_unchanged(tmp_path, monkeypatch):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    src = src_dir / "doc.md"
    src.write_text("# Doc", encoding="utf-8")
    wiki_dir = tmp_path / "wiki" / "infra"
    wiki_dir.mkdir(parents=True)
    chunks = ChunkStore(tmp_path / "chunks" / "infra.jsonl", domain="infra")
    manifest = Manifest.load(tmp_path / "manifest.json")
    manifest.mark(src)  # pretend already processed

    called = {"n": 0}
    monkeypatch.setattr(ingest_mod, "extract_entities",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1) or [])

    changed = ingest_file(StubLLM(), _domain(src_dir), src, wiki_dir, chunks, manifest)
    assert changed is False
    assert called["n"] == 0  # phases not invoked
