import pytest
from pathlib import Path
from owaw.pages import synthesize_pages, write_page, read_existing_pages, WikiPage
from owaw.domains import Domain, EntityType
from owaw.entities import Entity


class StubLLM:
    def __init__(self, obj):
        self._obj = obj
        self.prompt = None

    def chat_json(self, prompt):
        self.prompt = prompt
        return self._obj


def _domain():
    return Domain(id="infra", name="Infra", wiki_folder="infra", source_paths=[],
                  entity_types=[EntityType(type="service", description="d", extraction_cues=[])])


def test_synthesize_returns_pages():
    llm = StubLLM({"reasoning": "r", "pages": [
        {"path": "wiki_infra_traefik.md",
         "content": "---\nwiki_status: stub\n---\n# Traefik\n\n## Role\nproxy",
         "annotation": "Traefik reverse proxy. Terms: ingress, tls."},
    ]})
    pages = synthesize_pages(llm, _domain(), "src body", "minipc-docs",
                             [Entity(name="Traefik", type="service")], existing_pages=[])
    assert pages == [WikiPage(
        path="wiki_infra_traefik.md",
        content="---\nwiki_status: stub\n---\n# Traefik\n\n## Role\nproxy",
        annotation="Traefik reverse proxy. Terms: ingress, tls.",
    )]


def test_prompt_includes_entities_and_existing():
    llm = StubLLM({"reasoning": "r", "pages": []})
    synthesize_pages(llm, _domain(), "src", "minipc-docs",
                     [Entity(name="Traefik")], existing_pages=[
                         WikiPage(path="wiki_infra_traefik.md", content="old", annotation="a")])
    assert "Traefik" in llm.prompt
    assert "old" in llm.prompt
    assert "minipc-docs" in llm.prompt


def test_write_and_read_page_roundtrip(tmp_path):
    page = WikiPage(path="wiki_infra_traefik.md",
                    content="---\nwiki_status: stub\n---\n# Traefik\n\nbody", annotation="a")
    write_page(tmp_path, page)
    on_disk = (tmp_path / "wiki_infra_traefik.md").read_text(encoding="utf-8")
    assert on_disk == page.content
    existing = read_existing_pages(tmp_path, ["wiki_infra_traefik", "wiki_infra_absent"])
    assert len(existing) == 1
    assert existing[0].path == "wiki_infra_traefik.md"
    assert existing[0].content == page.content


def test_write_page_rejects_path_escape(tmp_path):
    bad = WikiPage(path="../outside.md", content="x", annotation="a")
    with pytest.raises(ValueError, match="escapes"):
        write_page(tmp_path, bad)
