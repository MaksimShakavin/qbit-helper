"""Tests for the completed-directory cleanup logic."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from qbit_torrent_files_cleaner.config import (
    CommandConfig,
    Config,
    MonitorCompletedConfig,
    QBittorrentConfig,
)
from qbit_torrent_files_cleaner.monitor_completed import monitor_completed

from .conftest import make_v1_torrent


def _config(completed_dir, *, dry, categories=("movies",)):
    return Config(
        commands=CommandConfig(dry=dry, monitor_completed=True),
        qbittorrent=QBittorrentConfig(),
        monitor_completed=MonitorCompletedConfig(
            completed_dir=str(completed_dir),
            categories=list(categories),
        ),
    )


def _client(known_hashes):
    client = MagicMock()
    client.collect_hashes_for_categories.return_value = set(known_hashes)
    return client


def _write_torrent(directory, filename):
    data, infohash = make_v1_torrent(name=filename)
    (directory / filename).write_bytes(data)
    return infohash


def test_removes_orphan_and_keeps_known(tmp_path):
    keep_hash = _write_torrent(tmp_path, "keep.torrent")
    _write_torrent(tmp_path, "orphan.torrent")
    config = _config(tmp_path, dry=False)

    result = monitor_completed(config, _client({keep_hash}))

    assert result.processed == 2
    assert result.removed == 1
    assert (tmp_path / "keep.torrent").exists()
    assert not (tmp_path / "orphan.torrent").exists()


def test_dry_run_deletes_nothing(tmp_path):
    _write_torrent(tmp_path, "keep.torrent")
    _write_torrent(tmp_path, "orphan.torrent")
    config = _config(tmp_path, dry=True)

    result = monitor_completed(config, _client(set()))

    assert result.processed == 2
    assert result.removed == 2  # would-remove count
    assert (tmp_path / "keep.torrent").exists()
    assert (tmp_path / "orphan.torrent").exists()


def test_ignores_non_torrent_files(tmp_path):
    _write_torrent(tmp_path, "keep.torrent")
    (tmp_path / "note.txt").write_text("hello")
    config = _config(tmp_path, dry=False)

    result = monitor_completed(config, _client(set()))

    assert result.processed == 1
    assert (tmp_path / "note.txt").exists()


def test_unreadable_torrent_is_skipped_not_removed(tmp_path):
    (tmp_path / "broken.torrent").write_bytes(b"not bencode")
    config = _config(tmp_path, dry=False)

    result = monitor_completed(config, _client(set()))

    assert result.processed == 1
    assert result.removed == 0
    assert result.skipped == 1
    assert (tmp_path / "broken.torrent").exists()


def test_missing_directory_raises(tmp_path):
    config = _config(tmp_path / "does-not-exist", dry=True)
    with pytest.raises(ValueError, match="does not exist"):
        monitor_completed(config, _client(set()))


def test_empty_completed_dir_setting_raises(tmp_path):
    config = _config("", dry=True)
    with pytest.raises(ValueError, match="completed_dir"):
        monitor_completed(config, _client(set()))


def test_empty_categories_raises(tmp_path):
    config = _config(tmp_path, dry=True, categories=())
    with pytest.raises(ValueError, match="categories is empty"):
        monitor_completed(config, _client(set()))
