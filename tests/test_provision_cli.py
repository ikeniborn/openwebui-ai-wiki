from typer.testing import CliRunner

from owaw.cli import app

runner = CliRunner()

_CONFIG = (
    "generation:\n  model: m\n  base_url: u\n"
    "openwebui:\n  base_url: http://owui:8080\n  collection: ai-wiki\n"
    "agent:\n  base_model: gpt-4o\n"
)


def test_owui_provision_calls_provisioner(tmp_path, monkeypatch):
    monkeypatch.setenv("OWAW_DATA_DIR", str(tmp_path))
    (tmp_path / "config.yaml").write_text(_CONFIG, encoding="utf-8")

    called = {}

    def fake_provision(ow, agent, **kw):
        called["ok"] = (ow.collection, agent.base_model)
        return {"tool_id": "wiki_docs", "model_id": "ai-wiki-agent", "collection_id": "cid"}

    monkeypatch.setattr("owaw.owui.provision.provision_agent", fake_provision)
    r = runner.invoke(app, ["owui-provision"])
    assert r.exit_code == 0, r.output
    assert called["ok"] == ("ai-wiki", "gpt-4o")
    assert "ai-wiki-agent" in r.output


def test_owui_provision_errors_without_agent(tmp_path, monkeypatch):
    monkeypatch.setenv("OWAW_DATA_DIR", str(tmp_path))
    (tmp_path / "config.yaml").write_text(
        "generation:\n  model: m\n  base_url: u\n"
        "openwebui:\n  base_url: http://owui:8080\n  collection: ai-wiki\n",
        encoding="utf-8",
    )
    r = runner.invoke(app, ["owui-provision"])
    assert r.exit_code == 1
    assert "agent" in r.output
