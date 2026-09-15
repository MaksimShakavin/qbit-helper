"""Tests for the unregistered-torrent handling task."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from qbit_torrent_files_cleaner.arr import ArrError, HistoryRecord, QueueItem
from qbit_torrent_files_cleaner.client import QBittorrentError, TorrentInfo, TrackerInfo
from qbit_torrent_files_cleaner.config import CommandConfig, Config, HandleUnregisteredConfig
from qbit_torrent_files_cleaner.handle_unregistered import handle_unregistered, is_unregistered

DEAD = TrackerInfo(
    url="http://tracker", status=4, message="Torrent not registered with this tracker"
)
# qBittorrent 5.2.x reports a dedicated "not registered" status 5 (observed live).
DEAD_STATUS_5 = TrackerInfo(url="http://tracker", status=5, message="Torrent not registered")
WORKING = TrackerInfo(url="http://tracker", status=2, message="Working")
DHT = TrackerInfo(url="** [DHT] **", status=0, message="")


# -- is_unregistered ---------------------------------------------------------


def test_unregistered_true_for_matching_not_working_tracker():
    assert is_unregistered([DEAD], ["torrent not registered"]) is True


def test_unregistered_true_for_status_5_not_registered():
    assert is_unregistered([DEAD_STATUS_5], ["torrent not registered"]) is True


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


def _torrent(hash_="abc", name="Show S01", category="tv", infohash_v1=None):
    return TorrentInfo(
        hash=hash_,
        infohash_v1=infohash_v1 if infohash_v1 is not None else hash_,
        name=name,
        category=category,
        state="stalledUP",
    )


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


def test_history_path_searches_before_deleting():
    # The replacement search must be triggered before the destructive delete, so a
    # failed search never leaves a torrent deleted with no replacement ordered.
    arr = _arr()
    arr.find_history_record.return_value = HistoryRecord(series_id=5)
    client = _client([_torrent()], [DEAD])

    manager = MagicMock()
    manager.attach_mock(arr.trigger_search, "trigger_search")
    manager.attach_mock(client.delete_torrent, "delete_torrent")

    handle_unregistered(_config(dry=False), client, [arr])

    assert [call[0] for call in manager.mock_calls] == ["trigger_search", "delete_torrent"]


def test_history_search_failure_leaves_torrent_undeleted():
    arr = _arr()
    arr.find_history_record.return_value = HistoryRecord(series_id=5)
    arr.trigger_search.side_effect = ArrError("sonarr down")
    client = _client([_torrent()], [DEAD])

    result = handle_unregistered(_config(dry=False), client, [arr])

    client.delete_torrent.assert_not_called()
    assert result.imported_handled == 0
    assert result.errors == 1


def test_imported_queue_item_routes_to_history_search():
    # A queue item whose grab already imported (only still seeding) cannot be
    # blocklisted/redownloaded by a queue delete, so it must fall through to the history
    # path: an explicit replacement search, then delete. No queue delete happens.
    arr = _arr()
    arr.find_queue_item.return_value = QueueItem(
        id=7, download_id="abc", title="Show", tracked_download_state="imported"
    )
    arr.find_history_record.return_value = HistoryRecord(series_id=5)
    client = _client([_torrent()], [DEAD])

    result = handle_unregistered(_config(dry=False), client, [arr])

    arr.delete_queue_item.assert_not_called()
    arr.trigger_search.assert_called_once()
    client.delete_torrent.assert_called_once_with("abc", delete_files=True)
    assert result.queue_handled == 0
    assert result.imported_handled == 1


def test_downloading_queue_item_still_uses_queue_path():
    # A still-downloading grab is handled in place (blocklist + redownload), not routed
    # to history.
    arr = _arr()
    arr.find_queue_item.return_value = QueueItem(
        id=7, download_id="abc", title="Show", tracked_download_state="downloading"
    )
    client = _client([_torrent()], [DEAD])

    result = handle_unregistered(_config(dry=False), client, [arr])

    arr.delete_queue_item.assert_called_once_with(7)
    client.delete_torrent.assert_not_called()
    assert result.queue_handled == 1


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


def test_hybrid_torrent_uses_v1_hash_for_arr_and_client_hash_for_delete():
    # v2/hybrid torrent: qBittorrent's own hash differs from the v1 info hash the
    # *arr stores as the download id. Arr lookups must use v1; the qBittorrent
    # deletion must use qBittorrent's hash (else it 404s).
    arr = _arr()
    arr.find_history_record.return_value = HistoryRecord(series_id=5)
    torrent = _torrent(hash_="qbhash", infohash_v1="v1hash")
    client = _client([torrent], [DEAD])

    handle_unregistered(_config(dry=False), client, [arr])

    arr.find_queue_item.assert_called_once_with("v1hash")
    arr.find_history_record.assert_called_once_with("v1hash")
    client.delete_torrent.assert_called_once_with("qbhash", delete_files=True)


def test_one_torrent_failure_does_not_abort_the_batch():
    # First torrent's queue delete fails; the run must log/count it and still handle
    # the second torrent rather than aborting.
    arr = _arr()
    arr.find_queue_item.return_value = QueueItem(id=7, download_id="abc", title="Show")
    arr.delete_queue_item.side_effect = [ArrError("boom"), None]
    client = _client([_torrent(name="first"), _torrent(name="second")], [DEAD])

    result = handle_unregistered(_config(dry=False), client, [arr])

    assert result.scanned == 2
    assert result.unregistered == 2
    assert result.errors == 1
    assert result.queue_handled == 1  # the second torrent still handled


def test_tracker_fetch_failure_is_isolated():
    client = _client([_torrent()], None)
    client.get_trackers.side_effect = QBittorrentError("trackers unavailable")

    result = handle_unregistered(_config(dry=False), client, [_arr()])

    assert result.errors == 1
    assert result.unregistered == 0


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
