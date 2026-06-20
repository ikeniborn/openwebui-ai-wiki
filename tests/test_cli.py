from typer.testing import CliRunner
import owaw.cli as cli_mod
from owaw.cli import app
from owaw.domains import Domain, load_domains

runner = CliRunner()


def test_domain_add_and_list(tmp_path, monkeypatch):
    monkeypatch.setenv("OWAW_DATA_DIR", str(tmp_path))
    r = runner.invoke(app, ["domain", "add", "--id", "infra", "--name", "Infra",
                            "--wiki-folder", "infra", "--source", str(tmp_path / "src")])
    assert r.exit_code == 0, r.output
    assert load_domains(tmp_path / "domains.yaml")[0].id == "infra"
    r2 = runner.invoke(app, ["domain", "list"])
    assert "infra" in r2.output


def test_init_creates_dirs_and_index(tmp_path, monkeypatch):
    monkeypatch.setenv("OWAW_DATA_DIR", str(tmp_path))
    runner.invoke(app, ["domain", "add", "--id", "infra", "--name", "Infra",
                        "--wiki-folder", "infra", "--source", str(tmp_path / "src")])
    r = runner.invoke(app, ["init", "--domain", "infra"])
    assert r.exit_code == 0, r.output
    assert (tmp_path / "wiki" / "infra" / "_index.md").exists()


def test_ingest_invokes_domain_driver(tmp_path, monkeypatch):
    monkeypatch.setenv("OWAW_DATA_DIR", str(tmp_path))
    runner.invoke(app, ["domain", "add", "--id", "infra", "--name", "Infra",
                        "--wiki-folder", "infra", "--source", str(tmp_path / "src")])
    seen = {}
    monkeypatch.setattr(cli_mod, "ingest_domain",
                        lambda llm, domain, **k: seen.__setitem__("id", domain.id) or 3)
    monkeypatch.setattr(cli_mod.LLM, "from_config", classmethod(lambda cls, gen: object()))
    (tmp_path / "config.yaml").write_text(
        "generation:\n  model: m\n  base_url: u\n", encoding="utf-8")
    r = runner.invoke(app, ["ingest", "--domain", "infra"])
    assert r.exit_code == 0, r.output
    assert seen["id"] == "infra"
    assert "3" in r.output
