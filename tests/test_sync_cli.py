from typer.testing import CliRunner

import owaw.cli as cli_mod
from owaw.cli import app
from owaw.sync import SyncResult

runner = CliRunner()


def test_sync_command_runs_reconcile_and_prints_counts(monkeypatch, tmp_path):
    monkeypatch.setenv("OWAW_DATA_DIR", str(tmp_path))

    class FakeEngine:
        def reconcile(self):
            return SyncResult(added=3, deleted=1, unchanged=5)

    monkeypatch.setattr(cli_mod, "_sync_engine", lambda: FakeEngine())
    result = runner.invoke(app, ["sync"])
    assert result.exit_code == 0
    assert "+3" in result.stdout and "-1" in result.stdout and "=5" in result.stdout


def test_sync_command_errors_clearly_without_openwebui_config(monkeypatch, tmp_path):
    monkeypatch.setenv("OWAW_DATA_DIR", str(tmp_path))
    (tmp_path / "config.yaml").write_text(
        "generation:\n  model: m\n  base_url: u\n", encoding="utf-8"
    )
    result = runner.invoke(app, ["sync"])
    assert result.exit_code != 0
    assert "openwebui" in result.stdout.lower()
