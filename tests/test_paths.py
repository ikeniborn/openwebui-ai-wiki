from pathlib import Path
from owaw import paths


def test_data_dir_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("OWAW_DATA_DIR", str(tmp_path))
    assert paths.data_dir() == tmp_path


def test_layout_helpers(monkeypatch, tmp_path):
    monkeypatch.setenv("OWAW_DATA_DIR", str(tmp_path))
    assert paths.domains_path() == tmp_path / "domains.yaml"
    assert paths.config_path() == tmp_path / "config.yaml"
    assert paths.wiki_dir("infra") == tmp_path / "wiki" / "infra"
    assert paths.chunks_path("infra") == tmp_path / "chunks" / "infra.jsonl"
    assert paths.manifest_path("infra") == tmp_path / "state" / "manifest_infra.json"


def test_ensure_dirs_creates_tree(monkeypatch, tmp_path):
    monkeypatch.setenv("OWAW_DATA_DIR", str(tmp_path))
    paths.ensure_dirs("infra")
    assert (tmp_path / "wiki" / "infra").is_dir()
    assert (tmp_path / "chunks").is_dir()
    assert (tmp_path / "state").is_dir()


def test_chunks_dir_and_sync_state_path(monkeypatch, tmp_path):
    monkeypatch.setenv("OWAW_DATA_DIR", str(tmp_path))
    from owaw import paths
    assert paths.chunks_dir() == tmp_path / "chunks"
    assert paths.sync_state_path("ai-wiki") == tmp_path / "state" / "sync_ai-wiki.json"
