"""Tests for the CLI entry point."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from qbit_torrent_files_cleaner import cli
from qbit_torrent_files_cleaner.handle_unregistered import HandleUnregisteredResult


@pytest.fixture
def patch_client(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(cli, "QBittorrentClient", MagicMock(return_value=client))
    return client


def _write_config(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_no_commands_enabled_is_noop(tmp_path, patch_client):
    path = _write_config(tmp_path, "commands:\n  monitor_completed: false\n")
    assert cli.main(["--config", str(path)]) == 0
    patch_client.connect.assert_not_called()


def test_runs_monitor_completed(tmp_path, monkeypatch, patch_client):
    completed = tmp_path / "completed"
    completed.mkdir()
    path = _write_config(
        tmp_path,
        f"""
commands:
  dry: true
  monitor_completed: true
monitor_completed:
  completed_dir: {completed}
  categories: [movies]
""",
    )
    called = MagicMock()
    monkeypatch.setattr(cli, "monitor_completed", called)

    assert cli.main(["--config", str(path)]) == 0
    patch_client.connect.assert_called_once()
    called.assert_called_once()


def test_missing_config_returns_2(tmp_path, patch_client):
    assert cli.main(["--config", str(tmp_path / "nope.yaml")]) == 2


def test_qbittorrent_error_returns_1(tmp_path, monkeypatch, patch_client):
    completed = tmp_path / "completed"
    completed.mkdir()
    path = _write_config(
        tmp_path,
        f"""
commands:
  monitor_completed: true
monitor_completed:
  completed_dir: {completed}
  categories: [movies]
""",
    )
    patch_client.connect.side_effect = cli.QBittorrentError("cannot connect")
    assert cli.main(["--config", str(path)]) == 1


def test_config_validation_error_returns_2(tmp_path, monkeypatch, patch_client):
    path = _write_config(
        tmp_path,
        """
commands:
  monitor_completed: true
monitor_completed:
  completed_dir: /nonexistent/dir
  categories: [movies]
""",
    )
    assert cli.main(["--config", str(path)]) == 2


def test_runs_handle_unregistered(tmp_path, monkeypatch, patch_client):
    path = _write_config(
        tmp_path,
        """
commands:
  handle_unregistered: true
radarr:
  url: http://radarr:7878
  api_key: key
""",
    )
    called = MagicMock(return_value=HandleUnregisteredResult(scanned=1))
    monkeypatch.setattr(cli, "handle_unregistered", called)
    monkeypatch.setattr(cli, "build_arr_clients", MagicMock(return_value=["client"]))

    assert cli.main(["--config", str(path)]) == 0
    patch_client.connect.assert_called_once()
    called.assert_called_once()


def test_handle_unregistered_errors_exit_nonzero(tmp_path, monkeypatch, patch_client):
    path = _write_config(
        tmp_path,
        """
commands:
  handle_unregistered: true
radarr:
  url: http://radarr:7878
  api_key: key
""",
    )
    monkeypatch.setattr(
        cli, "handle_unregistered", MagicMock(return_value=HandleUnregisteredResult(errors=2))
    )
    monkeypatch.setattr(cli, "build_arr_clients", MagicMock(return_value=["client"]))

    assert cli.main(["--config", str(path)]) == 1


def test_arr_error_returns_1(tmp_path, monkeypatch, patch_client):
    path = _write_config(
        tmp_path,
        """
commands:
  handle_unregistered: true
radarr:
  url: http://radarr:7878
  api_key: key
""",
    )
    monkeypatch.setattr(cli, "build_arr_clients", MagicMock(return_value=["client"]))
    monkeypatch.setattr(cli, "handle_unregistered", MagicMock(side_effect=cli.ArrError("boom")))
    assert cli.main(["--config", str(path)]) == 1


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
