"""Minimal Radarr/Sonarr (\\*arr) API v3 client.

Radarr and Sonarr share the same v3 API shape for the endpoints we need (queue,
history, command), so one client class serves both; the ``kind`` attribute selects
the few app-specific bits (search command name, "unknown item" query flag, and the
id field in history/queue records).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum
from typing import Any

import requests

from qbit_torrent_files_cleaner.config import ArrInstanceConfig, Config

logger = logging.getLogger(__name__)

# A generous request timeout; \\*arr instances are usually local but may be slow to
# answer a queue page while importing.
_TIMEOUT = 30
_QUEUE_PAGE_SIZE = 200


class ArrError(Exception):
    """Raised when talking to a Radarr/Sonarr instance fails."""


class ArrKind(Enum):
    """Which \\*arr application an :class:`ArrClient` talks to."""

    RADARR = "radarr"
    SONARR = "sonarr"


@dataclass(frozen=True)
class QueueItem:
    """A queue entry, reduced to the fields the tool acts on."""

    id: int
    download_id: str
    title: str


@dataclass(frozen=True)
class HistoryRecord:
    """A history entry identifying the movie/series a download belonged to."""

    movie_id: int | None = None
    series_id: int | None = None
    season_number: int | None = None
    episode_id: int | None = None


class ArrClient:
    """Talks to a single Radarr or Sonarr instance over its v3 API."""

    def __init__(
        self, kind: ArrKind, config: ArrInstanceConfig, *, season_search: bool = False
    ) -> None:
        self.kind = kind
        self.name = kind.value
        self._base_url = config.url.rstrip("/")
        self._season_search = season_search
        self._session = requests.Session()
        self._session.headers.update({"X-Api-Key": config.api_key})
        self._session.verify = config.verify_ssl

    # -- HTTP helpers -------------------------------------------------------

    def _url(self, path: str) -> str:
        return f"{self._base_url}/api/v3/{path.lstrip('/')}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        try:
            response = self._session.request(
                method, self._url(path), params=params, json=json, timeout=_TIMEOUT
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ArrError(f"{self.name}: request to {path} failed: {exc}") from exc
        if not response.content:
            return None
        return response.json()

    # -- Queue --------------------------------------------------------------

    def _iter_queue(self) -> Iterator[dict[str, Any]]:
        include_flag = (
            "includeUnknownMovieItems"
            if self.kind is ArrKind.RADARR
            else "includeUnknownSeriesItems"
        )
        page = 1
        while True:
            params = {"page": page, "pageSize": _QUEUE_PAGE_SIZE, include_flag: "true"}
            payload = self._request("GET", "queue", params=params) or {}
            records: list[dict[str, Any]] = payload.get("records", [])
            yield from records
            # Stop once we've read every record the server reported.
            total = int(payload.get("totalRecords", 0) or 0)
            if not records or page * _QUEUE_PAGE_SIZE >= total:
                break
            page += 1

    def find_queue_item(self, download_id: str) -> QueueItem | None:
        """Find a queue item by its download id (the torrent hash), case-insensitively."""
        wanted = download_id.lower()
        for record in self._iter_queue():
            record_id = str(record.get("downloadId", "") or "").lower()
            if record_id and record_id == wanted:
                return QueueItem(
                    id=int(record["id"]),
                    download_id=record_id,
                    title=str(record.get("title", "") or ""),
                )
        return None

    def delete_queue_item(
        self,
        item_id: int,
        *,
        remove_from_client: bool = True,
        blocklist: bool = True,
        skip_redownload: bool = False,
    ) -> None:
        """Delete a queue item.

        With ``remove_from_client`` the \\*arr tells the download client to remove the
        torrent *and its data*; ``blocklist`` records the release so it is not grabbed
        again; and with ``skip_redownload`` false the \\*arr automatically searches for a
        replacement.
        """
        params = {
            "removeFromClient": str(remove_from_client).lower(),
            "blocklist": str(blocklist).lower(),
            "skipRedownload": str(skip_redownload).lower(),
        }
        self._request("DELETE", f"queue/{item_id}", params=params)

    # -- History + search (imported / seeding torrents) ---------------------

    def find_history_record(self, download_id: str) -> HistoryRecord | None:
        """Find the movie/series a download belonged to via history."""
        payload = self._request("GET", "history", params={"downloadId": download_id})
        if isinstance(payload, dict):
            records: list[dict[str, Any]] = payload.get("records", [])
        else:
            records = payload or []
        for record in records:
            if self.kind is ArrKind.RADARR:
                movie_id = record.get("movieId")
                if movie_id:
                    return HistoryRecord(movie_id=int(movie_id))
            else:
                series_id = record.get("seriesId")
                if series_id:
                    data = record.get("data") or {}
                    season = data.get("seasonNumber") or record.get("seasonNumber")
                    episode_id = record.get("episodeId")
                    return HistoryRecord(
                        series_id=int(series_id),
                        season_number=int(season) if season not in (None, "") else None,
                        episode_id=int(episode_id) if episode_id else None,
                    )
        return None

    def trigger_search(self, record: HistoryRecord) -> None:
        """Trigger a search for a replacement release for a movie/series."""
        command = self._build_search_command(record)
        if command is None:
            logger.warning("%s: no searchable id in history record; skipping search", self.name)
            return
        self._request("POST", "command", json=command)

    def _build_search_command(self, record: HistoryRecord) -> dict[str, Any] | None:
        if self.kind is ArrKind.RADARR:
            if record.movie_id is None:
                return None
            return {"name": "MoviesSearch", "movieIds": [record.movie_id]}

        if record.series_id is None:
            return None
        if self._season_search and record.season_number is not None:
            return {
                "name": "SeasonSearch",
                "seriesId": record.series_id,
                "seasonNumber": record.season_number,
            }
        return {"name": "SeriesSearch", "seriesId": record.series_id}


def build_arr_clients(config: Config) -> list[ArrClient]:
    """Build the enabled Radarr/Sonarr clients from the application config."""
    clients: list[ArrClient] = []
    season_search = config.handle_unregistered.season_search
    if config.radarr.enabled:
        clients.append(ArrClient(ArrKind.RADARR, config.radarr, season_search=season_search))
    if config.sonarr.enabled:
        clients.append(ArrClient(ArrKind.SONARR, config.sonarr, season_search=season_search))
    return clients
