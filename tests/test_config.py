"""Tests for configuration loading and validation."""

from __future__ import annotations

import pytest

from qbit_torrent_files_cleaner.config import (
    DEFAULT_UNREGISTERED_PATTERNS,
    Config,
    ConfigError,
)


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


def test_handle_unregistered_defaults(tmp_path):
    path = _write(tmp_path, "")
    config = Config.load(path)
    assert config.commands.handle_unregistered is False
    assert config.handle_unregistered.categories == []
    assert config.handle_unregistered.unregistered_patterns == DEFAULT_UNREGISTERED_PATTERNS
    assert config.handle_unregistered.season_search is False
    assert config.radarr.enabled is False
    assert config.sonarr.enabled is False


def test_handle_unregistered_full_config(tmp_path):
    path = _write(
        tmp_path,
        """
commands:
  handle_unregistered: true
handle_unregistered:
  categories: [movies, tv]
  unregistered_patterns: ["dead"]
  season_search: true
radarr:
  url: http://radarr:7878/
  api_key: rkey
sonarr:
  url: http://sonarr:8989
  api_key: skey
  verify_ssl: true
""",
    )
    config = Config.load(path)
    assert config.commands.handle_unregistered is True
    assert config.handle_unregistered.categories == ["movies", "tv"]
    assert config.handle_unregistered.unregistered_patterns == ["dead"]
    assert config.handle_unregistered.season_search is True
    # Trailing slash is trimmed so URL joins are clean.
    assert config.radarr.url == "http://radarr:7878"
    assert config.radarr.enabled is True
    assert config.sonarr.enabled is True
    assert config.sonarr.verify_ssl is True


def test_arr_disabled_without_api_key(tmp_path):
    path = _write(tmp_path, "radarr:\n  url: http://radarr:7878\n")
    config = Config.load(path)
    assert config.radarr.enabled is False


def test_handle_unregistered_categories_wrong_type_raises(tmp_path):
    path = _write(tmp_path, "handle_unregistered:\n  categories: movies\n")
    with pytest.raises(ConfigError, match=r"handle_unregistered\.categories must be a list"):
        Config.load(path)


def test_unregistered_patterns_wrong_type_raises(tmp_path):
    path = _write(tmp_path, "handle_unregistered:\n  unregistered_patterns: nope\n")
    with pytest.raises(ConfigError, match="unregistered_patterns must be a list"):
        Config.load(path)
