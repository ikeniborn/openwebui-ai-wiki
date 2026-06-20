from owaw.entities import extract_entities, Entity
from owaw.domains import Domain, EntityType


class StubLLM:
    def __init__(self, obj):
        self._obj = obj
        self.prompt = None

    def chat_json(self, prompt):
        self.prompt = prompt
        return self._obj


def _domain():
    return Domain(
        id="infra", name="Infra", wiki_folder="infra", source_paths=[],
        entity_types=[EntityType(type="service", description="a daemon",
                                 extraction_cues=["unit"], min_mentions_for_page=1)],
        language_notes="Russian corpus.",
    )


def test_extract_entities_parses_records():
    llm = StubLLM({"reasoning": "r", "entities": [
        {"name": "Traefik", "type": "service", "context_snippet": "reverse proxy"},
        {"name": "Loki"},
    ]})
    ents = extract_entities(llm, _domain(), "source body")
    assert ents == [
        Entity(name="Traefik", type="service", context_snippet="reverse proxy"),
        Entity(name="Loki", type=None, context_snippet=None),
    ]


def test_prompt_includes_domain_and_source():
    llm = StubLLM({"reasoning": "r", "entities": []})
    extract_entities(llm, _domain(), "THE SOURCE TEXT")
    assert "Infra" in llm.prompt
    assert "service" in llm.prompt
    assert "THE SOURCE TEXT" in llm.prompt
    assert "Russian corpus." in llm.prompt


def test_empty_entities_yields_empty_list():
    llm = StubLLM({"reasoning": "r", "entities": []})
    assert extract_entities(llm, _domain(), "x") == []
