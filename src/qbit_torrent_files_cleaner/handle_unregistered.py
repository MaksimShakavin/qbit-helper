"""Detect tracker-deleted ("unregistered") torrents and get \\*arr to replace them.

When a private tracker's admins delete a topic, the torrent in qBittorrent goes
*unregistered* (the tracker returns an error status with a message like "Torrent not
registered with this tracker"). emonoda cannot help — the topic it would re-download
is gone — and Radarr/Sonarr do not re-grab on their own. This task closes that gap:

* If the dead torrent is still in an \\*arr queue, it deletes the queue item with
  ``removeFromClient + blocklist + redownload`` so the \\*arr removes the torrent and
  its data, blocklists the bad release, and searches for a replacement.
* If the \\*arr already imported it (now just seeding, no queue item), it looks the
  download up in \\*arr history, deletes the torrent + data from qBittorrent, and
  triggers a targeted search.
* Anything that cannot be attributed to a configured \\*arr is only reported.

Removing the torrent from qBittorrent also lets the ``monitor_completed`` task prune
the now-orphaned exported ``.torrent`` file.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from qbit_torrent_files_cleaner.arr import ArrClient
from qbit_torrent_files_cleaner.client import QBittorrentClient, TorrentInfo, TrackerInfo
from qbit_torrent_files_cleaner.config import Config

logger = logging.getLogger(__name__)

# qBittorrent tracker status codes (WebUI API).
_TRACKER_STATUS_WORKING = 2
# A tracker that rejected the torrent reports either the generic "not working" (4)
# or, on newer qBittorrent (observed on 5.2.x), a dedicated "not registered" (5).
_TRACKER_STATUS_FAILED = frozenset({4, 5})


@dataclass(frozen=True)
class HandleUnregisteredResult:
    """Summary of a handling run."""

    scanned: int = 0
    unregistered: int = 0
    queue_handled: int = 0
    imported_handled: int = 0
    reported: int = 0


def is_unregistered(trackers: list[TrackerInfo], patterns: list[str]) -> bool:
    """Return True when the tracker entries indicate the torrent was removed.

    Pseudo-trackers (DHT/PeX/LSD, whose url starts with ``**``) are ignored. A torrent
    counts as unregistered only when no real tracker is working *and* at least one
    reports a not-working status with a message matching a configured pattern — so a
    tracker that is merely temporarily down does not trigger a deletion.
    """
    real = [tracker for tracker in trackers if not tracker.url.startswith("**")]
    if not real:
        return False
    if any(tracker.status == _TRACKER_STATUS_WORKING for tracker in real):
        return False

    lowered = [pattern.lower() for pattern in patterns]
    for tracker in real:
        if tracker.status not in _TRACKER_STATUS_FAILED:
            continue
        message = tracker.message.lower()
        if any(pattern in message for pattern in lowered):
            return True
    return False


def handle_unregistered(
    config: Config,
    client: QBittorrentClient,
    arr_clients: list[ArrClient],
) -> HandleUnregisteredResult:
    """Find unregistered torrents and drive the \\*arr apps to replace them."""
    if not arr_clients:
        raise ValueError(
            "handle_unregistered requires at least one configured Radarr/Sonarr "
            "instance (set its url and api_key)."
        )

    settings = config.handle_unregistered
    is_dry_run = config.commands.dry

    if settings.categories:
        logger.info("Scanning categories: %s", ", ".join(settings.categories))
    else:
        logger.info("Scanning all categories.")
    if is_dry_run:
        logger.info("Dry run enabled; no torrents will be deleted and no searches triggered.")

    torrents = client.list_torrents(settings.categories)

    scanned = 0
    unregistered = 0
    queue_handled = 0
    imported_handled = 0
    reported = 0

    for torrent in torrents:
        scanned += 1
        trackers = client.get_trackers(torrent.hash)
        if not is_unregistered(trackers, settings.unregistered_patterns):
            continue

        unregistered += 1
        logger.info("Unregistered torrent: %s (%s)", torrent.name, torrent.hash)

        if _handle_via_queue(torrent.infohash_v1, torrent.name, arr_clients, is_dry_run):
            queue_handled += 1
        elif _handle_via_history(torrent, client, arr_clients, is_dry_run):
            imported_handled += 1
        else:
            logger.warning(
                "Unregistered torrent not found in any Radarr/Sonarr queue or history; "
                "leaving it for manual review: %s (%s)",
                torrent.name,
                torrent.hash,
            )
            reported += 1

    logger.info(
        "Done. Scanned %d torrent(s); %d unregistered; %s via queue %d, via history %d; "
        "reported %d.",
        scanned,
        unregistered,
        "would handle" if is_dry_run else "handled",
        queue_handled,
        imported_handled,
        reported,
    )
    return HandleUnregisteredResult(
        scanned=scanned,
        unregistered=unregistered,
        queue_handled=queue_handled,
        imported_handled=imported_handled,
        reported=reported,
    )


def _handle_via_queue(
    torrent_hash: str,
    torrent_name: str,
    arr_clients: list[ArrClient],
    is_dry_run: bool,
) -> bool:
    """Handle a torrent still tracked in an \\*arr queue. Returns True if handled."""
    for arr in arr_clients:
        item = arr.find_queue_item(torrent_hash)
        if item is None:
            continue
        logger.info(
            "%s: %s queue item for %s (blocklist + redownload)",
            arr.name,
            "would delete" if is_dry_run else "deleting",
            torrent_name,
        )
        if not is_dry_run:
            arr.delete_queue_item(item.id)
        return True
    return False


def _handle_via_history(
    torrent: TorrentInfo,
    client: QBittorrentClient,
    arr_clients: list[ArrClient],
    is_dry_run: bool,
) -> bool:
    """Handle an already-imported torrent via \\*arr history. Returns True if handled.

    The \\*arr history is looked up by the v1 info hash (the download id), while the
    qBittorrent deletion is keyed by qBittorrent's own torrent hash.
    """
    for arr in arr_clients:
        record = arr.find_history_record(torrent.infohash_v1)
        if record is None:
            continue
        logger.info(
            "%s: %s imported torrent %s and triggering a replacement search",
            arr.name,
            "would delete + search" if is_dry_run else "deleting + searching",
            torrent.name,
        )
        if not is_dry_run:
            client.delete_torrent(torrent.hash, delete_files=True)
            arr.trigger_search(record)
        return True
    return False
