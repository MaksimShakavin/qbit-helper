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


def _torrent(category, *, v1=None, v2=None, hash_=None, name="", state=""):
    return SimpleNamespace(
        category=category, infohash_v1=v1, infohash_v2=v2, hash=hash_, name=name, state=state
    )


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


def test_list_torrents_filters_by_category(patched_api):
    patched_api.torrents_info.return_value = [
        _torrent("movies", v1="AAA", hash_="AAA", name="A", state="up"),
        _torrent("other", v1="BBB", hash_="BBB"),
    ]
    client = QBittorrentClient(QBittorrentConfig())
    result = client.list_torrents(["movies"])
    assert len(result) == 1
    assert result[0].hash == "aaa"
    assert result[0].name == "A"
    assert result[0].category == "movies"
    assert result[0].state == "up"


def test_list_torrents_all_when_no_categories(patched_api):
    patched_api.torrents_info.return_value = [
        _torrent("movies", v1="AAA", hash_="AAA"),
        _torrent("other", v1="BBB", hash_="BBB"),
    ]
    client = QBittorrentClient(QBittorrentConfig())
    assert {t.hash for t in client.list_torrents()} == {"aaa", "bbb"}


def test_list_torrents_hash_is_client_hash_v1_is_infohash(patched_api):
    # v2/hybrid torrent: qBittorrent's own hash differs from the v1 info hash.
    # ``hash`` (used for WebUI calls) must be qBittorrent's hash; ``infohash_v1``
    # (used for *arr download-id matching) must be the v1 hash.
    patched_api.torrents_info.return_value = [_torrent("movies", v1="AAA", hash_="ZZZ")]
    client = QBittorrentClient(QBittorrentConfig())
    result = client.list_torrents(["movies"])[0]
    assert result.hash == "zzz"
    assert result.infohash_v1 == "aaa"


def test_list_torrents_v1_falls_back_to_client_hash(patched_api):
    # Legacy v1-only torrent reports no separate infohash_v1: fall back to hash.
    patched_api.torrents_info.return_value = [_torrent("movies", v1=None, hash_="ZZZ")]
    client = QBittorrentClient(QBittorrentConfig())
    result = client.list_torrents(["movies"])[0]
    assert result.hash == "zzz"
    assert result.infohash_v1 == "zzz"


def test_list_torrents_api_error_wrapped(patched_api):
    patched_api.torrents_info.side_effect = qbittorrentapi.APIError("boom")
    client = QBittorrentClient(QBittorrentConfig())
    with pytest.raises(QBittorrentError, match="list torrents"):
        client.list_torrents(["movies"])


def test_get_trackers_maps_fields(patched_api):
    patched_api.torrents_trackers.return_value = [
        SimpleNamespace(url="http://t", status=4, msg="unregistered torrent"),
    ]
    client = QBittorrentClient(QBittorrentConfig())
    trackers = client.get_trackers("abc")
    assert trackers[0].url == "http://t"
    assert trackers[0].status == 4
    assert trackers[0].message == "unregistered torrent"


def test_get_trackers_api_error_wrapped(patched_api):
    patched_api.torrents_trackers.side_effect = qbittorrentapi.APIError("boom")
    client = QBittorrentClient(QBittorrentConfig())
    with pytest.raises(QBittorrentError, match="trackers"):
        client.get_trackers("abc")


def test_delete_torrent_calls_api(patched_api):
    client = QBittorrentClient(QBittorrentConfig())
    client.delete_torrent("abc", delete_files=True)
    patched_api.torrents_delete.assert_called_once_with(delete_files=True, torrent_hashes="abc")


def test_delete_torrent_api_error_wrapped(patched_api):
    patched_api.torrents_delete.side_effect = qbittorrentapi.APIError("boom")
    client = QBittorrentClient(QBittorrentConfig())
    with pytest.raises(QBittorrentError, match="delete torrent"):
        client.delete_torrent("abc")
