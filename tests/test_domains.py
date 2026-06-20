import pytest
from owaw.domains import (
    Domain, EntityType, validate_domain_id, load_domains, save_domains, add_domain,
)


def test_validate_domain_id():
    assert validate_domain_id("infra-1") is None
    assert validate_domain_id("") is not None
    assert validate_domain_id("bad id") is not None


def test_roundtrip_save_load(tmp_path):
    d = Domain(
        id="infra", name="Infra", wiki_folder="infra",
        source_paths=["/data/sources/a"],
        entity_types=[EntityType(type="service", description="a daemon",
                                 extraction_cues=["unit", "port"], min_mentions_for_page=2,
                                 wiki_subfolder="services")],
        language_notes="Russian corpus.",
    )
    p = tmp_path / "domains.yaml"
    save_domains([d], p)
    loaded = load_domains(p)
    assert loaded == [d]


def test_load_missing_returns_empty(tmp_path):
    assert load_domains(tmp_path / "nope.yaml") == []


def test_add_domain_rejects_duplicate(tmp_path):
    p = tmp_path / "domains.yaml"
    d = Domain(id="infra", name="Infra", wiki_folder="infra", source_paths=[], entity_types=[])
    add_domain(d, p)
    with pytest.raises(ValueError, match="exists"):
        add_domain(d, p)
