"""Tests for the qBittorrent client wrapper (with the API mocked)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import qbittorrentapi

from qbit_torrent_files_cleaner.client import QBittorrentClient, QBittorrentError
from qbit_torrent_files_cleaner.config import QBittorrentConfig


@pytest.fixture
def patched_api(monkeypatch):
    """Replace ``qbittorrentapi.Client`` with a MagicMock, yielding the instance."""
    instance = MagicMock()
    monkeypatch.setattr(qbittorrentapi, "Client", MagicMock(return_value=instance))
    return instance


def _torrent(category, *, v1=None, v2=None, hash_=None):
    return SimpleNamespace(category=category, infohash_v1=v1, infohash_v2=v2, hash=hash_)


def test_connect_success(patched_api):
    client = QBittorrentClient(QBittorrentConfig())
    client.connect()
    patched_api.auth_log_in.assert_called_once()


def test_connect_login_failed_wrapped(patched_api):
    patched_api.auth_log_in.side_effect = qbittorrentapi.LoginFailed("bad creds")
    client = QBittorrentClient(QBittorrentConfig())
    with pytest.raises(QBittorrentError, match="authenticate"):
        client.connect()


def test_connect_connection_error_wrapped(patched_api):
    patched_api.auth_log_in.side_effect = qbittorrentapi.APIConnectionError("down")
    client = QBittorrentClient(QBittorrentConfig())
    with pytest.raises(QBittorrentError, match="connect"):
        client.connect()


def test_collect_hashes_filters_by_category(patched_api):
    patched_api.torrents_info.return_value = [
        _torrent("movies", v1="AAA"),
        _torrent("tv", v1="BBB"),
        _torrent("other", v1="CCC"),
    ]
    client = QBittorrentClient(QBittorrentConfig())
    result = client.collect_hashes_for_categories(["movies", "tv"])
    assert result == {"aaa", "bbb"}


def test_collect_hashes_includes_v1_and_v2(patched_api):
    patched_api.torrents_info.return_value = [
        _torrent("movies", v1="AAA", v2="DDD", hash_="AAA"),
    ]
    client = QBittorrentClient(QBittorrentConfig())
    result = client.collect_hashes_for_categories(["movies"])
    assert result == {"aaa", "ddd"}


def test_collect_hashes_api_error_wrapped(patched_api):
    patched_api.torrents_info.side_effect = qbittorrentapi.APIError("boom")
    client = QBittorrentClient(QBittorrentConfig())
    with pytest.raises(QBittorrentError, match="list torrents"):
        client.collect_hashes_for_categories(["movies"])


def test_collect_hashes_empty_when_no_match(patched_api):
    patched_api.torrents_info.return_value = [_torrent("other", v1="AAA")]
    client = QBittorrentClient(QBittorrentConfig())
    assert client.collect_hashes_for_categories(["movies"]) == set()
