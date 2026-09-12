"""Tests for configuration loading and validation."""

from __future__ import annotations

import pytest

from qbit_torrent_files_cleaner.config import Config, ConfigError


def _write(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_defaults_when_sections_absent(tmp_path):
    path = _write(tmp_path, "commands:\n  monitor_completed: true\n")
    config = Config.load(path)
    assert config.commands.monitor_completed is True
    assert config.commands.dry is True  # defaults to safe
    assert config.qbittorrent.host == "http://localhost:8080"
    assert config.monitor_completed.categories == []


def test_full_config(tmp_path):
    path = _write(
        tmp_path,
        """
commands:
  dry: false
  monitor_completed: true
qbittorrent:
  host: https://qb.example:8080
  user: admin
  password: secret
  verify_ssl: true
monitor_completed:
  completed_dir: /downloads/completed
  categories:
    - movies
    - tv
""",
    )
    config = Config.load(path)
    assert config.commands.dry is False
    assert config.qbittorrent.host == "https://qb.example:8080"
    assert config.qbittorrent.user == "admin"
    assert config.qbittorrent.verify_ssl is True
    assert config.monitor_completed.completed_dir == "/downloads/completed"
    assert config.monitor_completed.categories == ["movies", "tv"]


def test_legacy_disable_ssl_true_means_no_verify(tmp_path):
    path = _write(tmp_path, "qbittorrent:\n  disable_ssl: true\n")
    config = Config.load(path)
    assert config.qbittorrent.verify_ssl is False


def test_legacy_disable_ssl_false_means_verify(tmp_path):
    path = _write(tmp_path, "qbittorrent:\n  disable_ssl: false\n")
    config = Config.load(path)
    assert config.qbittorrent.verify_ssl is True


def test_verify_ssl_takes_precedence_over_disable_ssl(tmp_path):
    path = _write(tmp_path, "qbittorrent:\n  disable_ssl: true\n  verify_ssl: true\n")
    config = Config.load(path)
    assert config.qbittorrent.verify_ssl is True


def test_missing_file_raises(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        Config.load(tmp_path / "absent.yaml")


def test_invalid_yaml_raises(tmp_path):
    path = _write(tmp_path, "commands: [unclosed\n")
    with pytest.raises(ConfigError, match="Invalid YAML"):
        Config.load(path)


def test_non_mapping_top_level_raises(tmp_path):
    path = _write(tmp_path, "- just\n- a\n- list\n")
    with pytest.raises(ConfigError, match="mapping"):
        Config.load(path)


def test_section_wrong_type_raises(tmp_path):
    path = _write(tmp_path, "qbittorrent: not-a-mapping\n")
    with pytest.raises(ConfigError, match="must be a mapping"):
        Config.load(path)


def test_categories_wrong_type_raises(tmp_path):
    path = _write(tmp_path, "monitor_completed:\n  categories: movies\n")
    with pytest.raises(ConfigError, match="categories must be a list"):
        Config.load(path)


def test_empty_file_uses_defaults(tmp_path):
    path = _write(tmp_path, "")
    config = Config.load(path)
    assert config.commands.monitor_completed is False
