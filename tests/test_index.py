from owaw.index import rebuild_index


def test_index_lists_pages_sorted(tmp_path):
    (tmp_path / "wiki_infra_b.md").write_text("# B", encoding="utf-8")
    (tmp_path / "wiki_infra_a.md").write_text("# A", encoding="utf-8")
    rebuild_index(tmp_path, domain_name="Infra")
    text = (tmp_path / "_index.md").read_text(encoding="utf-8")
    assert "# Infra — index" in text
    assert text.index("[[wiki_infra_a]]") < text.index("[[wiki_infra_b]]")


def test_index_excludes_itself(tmp_path):
    (tmp_path / "wiki_infra_a.md").write_text("# A", encoding="utf-8")
    rebuild_index(tmp_path, domain_name="Infra")
    rebuild_index(tmp_path, domain_name="Infra")  # idempotent, never lists _index
    text = (tmp_path / "_index.md").read_text(encoding="utf-8")
    assert "[[_index]]" not in text
