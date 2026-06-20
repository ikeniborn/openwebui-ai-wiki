from pathlib import Path
import owaw.ingest as ingest_mod
from owaw.ingest import iter_source_files, ingest_domain
from owaw.domains import Domain


def _domain(src_dir):
    return Domain(id="infra", name="Infra", wiki_folder="infra",
                  source_paths=[str(src_dir)], entity_types=[])


def test_iter_source_files_recurses(tmp_path):
    (tmp_path / "a.md").write_text("a", encoding="utf-8")
    nested = tmp_path / "deep" / "deeper"
    nested.mkdir(parents=True)
    (nested / "b.md").write_text("b", encoding="utf-8")
    files = sorted(p.name for p in iter_source_files(_domain(tmp_path)))
    assert files == ["a.md", "b.md"]


def test_ingest_domain_processes_each_changed_file(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.md").write_text("a", encoding="utf-8")
    (src / "b.md").write_text("b", encoding="utf-8")

    processed = []
    monkeypatch.setattr(ingest_mod, "ingest_file",
                        lambda llm, d, f, *a, **k: processed.append(f.name) or True)
    monkeypatch.setenv("OWAW_DATA_DIR", str(tmp_path / "data"))

    n = ingest_domain(llm=object(), domain=_domain(src))
    assert n == 2
    assert sorted(processed) == ["a.md", "b.md"]
