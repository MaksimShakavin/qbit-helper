"""Thin wrapper around :mod:`qbittorrentapi` for the operations we need."""

from __future__ import annotations

import logging
from collections.abc import Iterable

import qbittorrentapi

from qbit_torrent_files_cleaner.config import QBittorrentConfig

logger = logging.getLogger(__name__)


class QBittorrentError(Exception):
    """Raised when talking to qBittorrent fails in a way we cannot recover from."""


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
