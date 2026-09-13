"""Tests for the Radarr/Sonarr API client (with HTTP mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests

from qbit_torrent_files_cleaner import arr
from qbit_torrent_files_cleaner.arr import ArrClient, ArrError, ArrKind, HistoryRecord
from qbit_torrent_files_cleaner.config import ArrInstanceConfig, Config, HandleUnregisteredConfig


@pytest.fixture
def session(monkeypatch):
    """Replace ``requests.Session`` with a MagicMock, yielding the instance."""
    instance = MagicMock()
    monkeypatch.setattr(arr.requests, "Session", MagicMock(return_value=instance))
    return instance


def _response(payload=None):
    response = MagicMock()
    response.raise_for_status.return_value = None
    if payload is None:
        response.content = b""
    else:
        response.content = b"{}"
        response.json.return_value = payload
    return response


def _radarr(**overrides):
    config = ArrInstanceConfig(url="http://radarr:7878", api_key="key", **overrides)
    return ArrClient(ArrKind.RADARR, config)


def _sonarr(*, season_search=False, **overrides):
    config = ArrInstanceConfig(url="http://sonarr:8989", api_key="key", **overrides)
    return ArrClient(ArrKind.SONARR, config, season_search=season_search)


def test_find_queue_item_matches_download_id_case_insensitively(session):
    session.request.return_value = _response(
        {"records": [{"id": 7, "downloadId": "ABCDEF", "title": "A Movie"}], "totalRecords": 1}
    )
    client = _radarr()
    item = client.find_queue_item("abcdef")
    assert item is not None
    assert item.id == 7
    assert item.title == "A Movie"


def test_find_queue_item_returns_none_when_absent(session):
    session.request.return_value = _response(
        {"records": [{"id": 1, "downloadId": "OTHER"}], "totalRecords": 1}
    )
    assert _radarr().find_queue_item("abcdef") is None


def test_find_queue_item_paginates(session):
    page1 = _response(
        {"records": [{"id": i, "downloadId": f"H{i}"} for i in range(200)], "totalRecords": 201}
    )
    page2 = _response({"records": [{"id": 200, "downloadId": "TARGET"}], "totalRecords": 201})
    session.request.side_effect = [page1, page2]
    item = _radarr().find_queue_item("target")
    assert item is not None
    assert item.id == 200


def test_delete_queue_item_sends_expected_params(session):
    session.request.return_value = _response()
    _radarr().delete_queue_item(7)
    _, kwargs = session.request.call_args
    assert kwargs["params"] == {
        "removeFromClient": "true",
        "blocklist": "true",
        "skipRedownload": "false",
    }


def test_find_history_record_radarr(session):
    session.request.return_value = _response({"records": [{"movieId": 42}]})
    record = _radarr().find_history_record("abc")
    assert record == HistoryRecord(movie_id=42)


def test_find_history_record_queries_uppercased_download_id(session):
    # *arr stores the info hash upper-cased and its history downloadId filter is
    # case-sensitive, so the lookup must upper-case the (lower-cased) hash.
    session.request.return_value = _response({"records": [{"movieId": 42}]})
    _radarr().find_history_record("abcdef123")
    _, kwargs = session.request.call_args
    assert kwargs["params"] == {"downloadId": "ABCDEF123"}


def test_find_history_record_sonarr_reads_season(session):
    session.request.return_value = _response(
        {"records": [{"seriesId": 5, "episodeId": 9, "data": {"seasonNumber": 3}}]}
    )
    record = _sonarr().find_history_record("abc")
    assert record == HistoryRecord(series_id=5, season_number=3, episode_id=9)


def test_trigger_search_radarr_movies_search(session):
    session.request.return_value = _response({})
    _radarr().trigger_search(HistoryRecord(movie_id=42))
    _, kwargs = session.request.call_args
    assert kwargs["json"] == {"name": "MoviesSearch", "movieIds": [42]}


def test_trigger_search_sonarr_series_search_by_default(session):
    session.request.return_value = _response({})
    _sonarr().trigger_search(HistoryRecord(series_id=5, season_number=3))
    _, kwargs = session.request.call_args
    assert kwargs["json"] == {"name": "SeriesSearch", "seriesId": 5}


def test_trigger_search_sonarr_season_search_when_enabled(session):
    session.request.return_value = _response({})
    _sonarr(season_search=True).trigger_search(HistoryRecord(series_id=5, season_number=3))
    _, kwargs = session.request.call_args
    assert kwargs["json"] == {"name": "SeasonSearch", "seriesId": 5, "seasonNumber": 3}


def test_trigger_search_without_id_is_noop(session):
    _sonarr().trigger_search(HistoryRecord())
    session.request.assert_not_called()


def test_request_error_wrapped(session):
    session.request.side_effect = requests.RequestException("boom")
    with pytest.raises(ArrError, match="request to"):
        _radarr().find_queue_item("abc")


def _config(*, radarr_key="", sonarr_key="", season_search=False):
    return Config(
        handle_unregistered=HandleUnregisteredConfig(season_search=season_search),
        radarr=ArrInstanceConfig(url="http://radarr:7878", api_key=radarr_key),
        sonarr=ArrInstanceConfig(url="http://sonarr:8989", api_key=sonarr_key),
    )


def test_build_arr_clients_only_enabled(session):
    clients = arr.build_arr_clients(_config(radarr_key="key"))
    assert [client.kind for client in clients] == [ArrKind.RADARR]


def test_build_arr_clients_both(session):
    clients = arr.build_arr_clients(_config(radarr_key="a", sonarr_key="b"))
    assert [client.kind for client in clients] == [ArrKind.RADARR, ArrKind.SONARR]


def test_build_arr_clients_none_when_unconfigured(session):
    assert arr.build_arr_clients(_config()) == []
