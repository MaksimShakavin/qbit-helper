"""Tests for the unregistered-torrent handling task."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from qbit_torrent_files_cleaner.arr import HistoryRecord, QueueItem
from qbit_torrent_files_cleaner.client import TorrentInfo, TrackerInfo
from qbit_torrent_files_cleaner.config import CommandConfig, Config, HandleUnregisteredConfig
from qbit_torrent_files_cleaner.handle_unregistered import handle_unregistered, is_unregistered

DEAD = TrackerInfo(
    url="http://tracker", status=4, message="Torrent not registered with this tracker"
)
WORKING = TrackerInfo(url="http://tracker", status=2, message="Working")
DHT = TrackerInfo(url="** [DHT] **", status=0, message="")


# -- is_unregistered ---------------------------------------------------------


def test_unregistered_true_for_matching_not_working_tracker():
    assert is_unregistered([DEAD], ["torrent not registered"]) is True


def test_unregistered_false_when_a_tracker_is_working():
    assert is_unregistered([WORKING, DEAD], ["torrent not registered"]) is False


def test_unregistered_false_when_message_does_not_match():
    tracker = TrackerInfo(url="http://t", status=4, message="tracker is down")
    assert is_unregistered([tracker], ["unregistered torrent"]) is False


def test_unregistered_false_with_only_pseudo_trackers():
    assert is_unregistered([DHT], ["unregistered torrent"]) is False


# -- handle_unregistered -----------------------------------------------------


def _config(*, dry, categories=()):
    return Config(
        commands=CommandConfig(dry=dry, handle_unregistered=True),
        handle_unregistered=HandleUnregisteredConfig(
            categories=list(categories),
            unregistered_patterns=["torrent not registered"],
        ),
    )


def _client(torrents, trackers):
    client = MagicMock()
    client.list_torrents.return_value = torrents
    client.get_trackers.return_value = trackers
    return client


def _arr(name="radarr"):
    arr = MagicMock()
    arr.name = name
    arr.find_queue_item.return_value = None
    arr.find_history_record.return_value = None
    return arr


def _torrent(hash_="abc", name="Show S01", category="tv"):
    return TorrentInfo(hash=hash_, name=name, category=category, state="stalledUP")


def test_requires_an_arr_client():
    with pytest.raises(ValueError, match="at least one"):
        handle_unregistered(_config(dry=True), _client([], []), [])


def test_registered_torrent_is_skipped():
    client = _client([_torrent()], [WORKING])
    result = handle_unregistered(_config(dry=False), client, [_arr()])
    assert result.unregistered == 0
    assert result.scanned == 1


def test_queue_path_deletes_queue_item():
    arr = _arr()
    arr.find_queue_item.return_value = QueueItem(id=7, download_id="abc", title="Show")
    client = _client([_torrent()], [DEAD])

    result = handle_unregistered(_config(dry=False), client, [arr])

    arr.delete_queue_item.assert_called_once_with(7)
    client.delete_torrent.assert_not_called()
    assert result.queue_handled == 1
    assert result.unregistered == 1


def test_history_path_deletes_torrent_and_searches():
    arr = _arr()
    arr.find_history_record.return_value = HistoryRecord(series_id=5)
    client = _client([_torrent()], [DEAD])

    result = handle_unregistered(_config(dry=False), client, [arr])

    client.delete_torrent.assert_called_once_with("abc", delete_files=True)
    arr.trigger_search.assert_called_once()
    arr.delete_queue_item.assert_not_called()
    assert result.imported_handled == 1


def test_reports_when_not_in_any_arr():
    client = _client([_torrent()], [DEAD])
    result = handle_unregistered(_config(dry=False), client, [_arr()])
    assert result.reported == 1
    client.delete_torrent.assert_not_called()


def test_dry_run_makes_no_mutating_calls():
    arr = _arr()
    arr.find_queue_item.return_value = QueueItem(id=7, download_id="abc", title="Show")
    client = _client([_torrent()], [DEAD])

    result = handle_unregistered(_config(dry=True), client, [arr])

    arr.delete_queue_item.assert_not_called()
    client.delete_torrent.assert_not_called()
    arr.trigger_search.assert_not_called()
    assert result.queue_handled == 1  # still counted as "would handle"


def test_queue_preferred_over_history():
    arr = _arr()
    arr.find_queue_item.return_value = QueueItem(id=7, download_id="abc", title="Show")
    arr.find_history_record.return_value = HistoryRecord(series_id=5)
    client = _client([_torrent()], [DEAD])

    result = handle_unregistered(_config(dry=False), client, [arr])

    arr.delete_queue_item.assert_called_once()
    arr.find_history_record.assert_not_called()
    assert result.queue_handled == 1
    assert result.imported_handled == 0
