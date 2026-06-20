from owaw.frontmatter import split_frontmatter, entity_slug, page_stem


def test_split_frontmatter_present():
    doc = "---\nwiki_status: stub\n---\n# Title\n\nbody"
    fm, body = split_frontmatter(doc)
    assert fm["wiki_status"] == "stub"
    assert body == "# Title\n\nbody"


def test_split_frontmatter_absent():
    fm, body = split_frontmatter("# Title\n\nbody")
    assert fm == {}
    assert body == "# Title\n\nbody"


def test_entity_slug_ascii_snake():
    assert entity_slug("Neural Networks") == "neural_networks"
    assert entity_slug("host.docker.internal") == "host_docker_internal"
    assert entity_slug("CPU/GPU split") == "cpu_gpu_split"


def test_page_stem():
    assert page_stem("infra", "Neural Networks") == "wiki_infra_neural_networks"
