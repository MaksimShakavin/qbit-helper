"""qbit-torrent-files-cleaner: keep a qBittorrent completed directory tidy."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("qbit-torrent-files-cleaner")
except PackageNotFoundError:  # pragma: no cover - not installed (e.g. running from source)
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
