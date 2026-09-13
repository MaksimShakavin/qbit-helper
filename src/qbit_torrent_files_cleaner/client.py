"""Thin wrapper around :mod:`qbittorrentapi` for the operations we need."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass

import qbittorrentapi

from qbit_torrent_files_cleaner.config import QBittorrentConfig

logger = logging.getLogger(__name__)


class QBittorrentError(Exception):
    """Raised when talking to qBittorrent fails in a way we cannot recover from."""


@dataclass(frozen=True)
class TorrentInfo:
    """The subset of a torrent's fields the tool cares about.

    ``hash`` is the v1 info hash when available (this is what Radarr/Sonarr use as
    the download id), falling back to whatever qBittorrent reports as ``hash``.
    """

    hash: str
    name: str
    category: str
    state: str


@dataclass(frozen=True)
class TrackerInfo:
    """A single tracker entry reported by qBittorrent for a torrent."""

    url: str
    status: int
    message: str


class QBittorrentClient:
    """Connects to qBittorrent and reports the info hashes it is tracking."""

    def __init__(self, config: QBittorrentConfig) -> None:
        self._client = qbittorrentapi.Client(
            host=config.host,
            username=config.user,
            password=config.password,
            VERIFY_WEBUI_CERTIFICATE=config.verify_ssl,
        )

    def connect(self) -> None:
        """Authenticate with the qBittorrent Web API."""
        try:
            self._client.auth_log_in()
        except qbittorrentapi.LoginFailed as exc:
            raise QBittorrentError(
                "Failed to authenticate with qBittorrent; check the username and password."
            ) from exc
        except qbittorrentapi.APIConnectionError as exc:
            raise QBittorrentError(
                "Failed to connect to qBittorrent; check the host address and that it is running."
            ) from exc
        except qbittorrentapi.APIError as exc:
            raise QBittorrentError(f"Unexpected qBittorrent API error: {exc}") from exc

    def collect_hashes_for_categories(self, categories: Iterable[str]) -> set[str]:
        """Return the set of v1 and v2 info hashes for torrents in the given categories.

        Both hash variants are included so hybrid and BitTorrent v2 torrents match
        their ``.torrent`` files regardless of which hash the file advertises. All
        hashes are lower-cased for case-insensitive comparison.
        """
        wanted = set(categories)
        try:
            torrents = self._client.torrents_info()
        except qbittorrentapi.APIError as exc:
            raise QBittorrentError(f"Failed to list torrents from qBittorrent: {exc}") from exc

        hashes: set[str] = set()
        for torrent in torrents:
            if torrent.category not in wanted:
                continue
            for value in (
                getattr(torrent, "infohash_v1", None),
                getattr(torrent, "infohash_v2", None),
                getattr(torrent, "hash", None),
            ):
                if value:
                    hashes.add(str(value).lower())
        return hashes

    def list_torrents(self, categories: Iterable[str] | None = None) -> list[TorrentInfo]:
        """Return torrents, optionally restricted to the given categories.

        When ``categories`` is empty or ``None`` every torrent is returned. Hashes
        are lower-cased so they compare cleanly against Radarr/Sonarr download ids.
        """
        wanted = set(categories or ())
        try:
            torrents = self._client.torrents_info()
        except qbittorrentapi.APIError as exc:
            raise QBittorrentError(f"Failed to list torrents from qBittorrent: {exc}") from exc

        result: list[TorrentInfo] = []
        for torrent in torrents:
            category = getattr(torrent, "category", "") or ""
            if wanted and category not in wanted:
                continue
            torrent_hash = (
                getattr(torrent, "infohash_v1", None) or getattr(torrent, "hash", None) or ""
            )
            result.append(
                TorrentInfo(
                    hash=str(torrent_hash).lower(),
                    name=str(getattr(torrent, "name", "") or ""),
                    category=str(category),
                    state=str(getattr(torrent, "state", "") or ""),
                )
            )
        return result

    def get_trackers(self, torrent_hash: str) -> list[TrackerInfo]:
        """Return the tracker entries qBittorrent reports for a torrent."""
        try:
            trackers = self._client.torrents_trackers(torrent_hash=torrent_hash)
        except qbittorrentapi.APIError as exc:
            raise QBittorrentError(f"Failed to read trackers for {torrent_hash}: {exc}") from exc

        result: list[TrackerInfo] = []
        for tracker in trackers:
            result.append(
                TrackerInfo(
                    url=str(getattr(tracker, "url", "") or ""),
                    status=int(getattr(tracker, "status", 0) or 0),
                    message=str(getattr(tracker, "msg", "") or ""),
                )
            )
        return result

    def delete_torrent(self, torrent_hash: str, *, delete_files: bool = True) -> None:
        """Remove a torrent from qBittorrent, optionally deleting its data."""
        try:
            self._client.torrents_delete(
                delete_files=delete_files,
                torrent_hashes=torrent_hash,
            )
        except qbittorrentapi.APIError as exc:
            raise QBittorrentError(f"Failed to delete torrent {torrent_hash}: {exc}") from exc
