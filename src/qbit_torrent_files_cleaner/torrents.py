"""Reading BitTorrent v1/v2 info hashes from ``.torrent`` files.

The info hash is derived from the *exact original bytes* of the ``info``
dictionary, so it matches what qBittorrent reports regardless of whether the
file was canonically encoded. Both the v1 (SHA-1) and v2 (SHA-256) hashes are
returned; a hybrid torrent exposes both, a classic torrent only v1, and a
BitTorrent v2 torrent only v2.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


class BencodeError(ValueError):
    """Raised when a ``.torrent`` file cannot be parsed as bencode."""


@dataclass(frozen=True)
class TorrentHashes:
    """The v1 and v2 info hashes advertised by a ``.torrent`` file."""

    v1: str | None = None
    v2: str | None = None

    def as_set(self) -> set[str]:
        """Return the non-empty hashes as a set for membership checks."""
        return {value for value in (self.v1, self.v2) if value}


def read_torrent_hashes(torrent_file: str | Path) -> TorrentHashes | None:
    """Read the v1/v2 info hashes from a ``.torrent`` file.

    Returns ``None`` when the file cannot be read or parsed; the reason is logged
    so a single bad file never aborts a cleanup run.
    """
    path = Path(torrent_file)
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        logger.warning("Torrent file not found: %s", path)
        return None
    except OSError as exc:
        logger.warning("Could not read torrent file %s: %s", path, exc)
        return None

    try:
        return _extract_hashes(data)
    except BencodeError as exc:
        logger.warning("Failed to parse torrent file %s: %s", path, exc)
        return None


def _extract_hashes(data: bytes) -> TorrentHashes | None:
    """Extract v1/v2 info hashes from the raw bytes of a ``.torrent`` file."""
    root, _ = _parse(data, 0)
    if not isinstance(root, dict):
        raise BencodeError("top level of torrent is not a dictionary")

    info_span = root.get(b"info")
    if info_span is None:
        raise BencodeError("torrent has no 'info' dictionary")

    info, start, end = info_span
    if not isinstance(info, dict):
        raise BencodeError("'info' is not a dictionary")

    info_bytes = data[start:end]
    v1 = hashlib.sha1(info_bytes).hexdigest()
    v2: str | None = None
    meta_version = info.get(b"meta version")
    # Dict values are stored as ``(value, start, end)`` spans; unwrap the value.
    if meta_version is not None and meta_version[0] == 2:
        v2 = hashlib.sha256(info_bytes).hexdigest()

    if v1 is None and v2 is None:  # pragma: no cover - v1 is always computed
        return None
    return TorrentHashes(v1=v1, v2=v2)


# --- Minimal bencode reader -------------------------------------------------
#
# Unlike a general decoder this reader also records, for every dictionary value,
# the byte span it occupies in the source. That lets us hash the ``info`` value
# byte-for-byte instead of re-encoding it.

# A parsed dict maps keys to ``(value, start, end)`` triples.
_DictSpans = dict[bytes, tuple[object, int, int]]


def _parse(data: bytes, pos: int) -> tuple[object, int]:
    """Parse one bencode value starting at ``pos``; return ``(value, next_pos)``."""
    if pos >= len(data):
        raise BencodeError("unexpected end of data")

    prefix = data[pos : pos + 1]
    if prefix == b"d":
        return _parse_dict(data, pos)
    if prefix == b"l":
        return _parse_list(data, pos)
    if prefix == b"i":
        return _parse_int(data, pos)
    if prefix.isdigit():
        return _parse_bytes(data, pos)
    raise BencodeError(f"invalid token {prefix!r} at position {pos}")


def _parse_dict(data: bytes, pos: int) -> tuple[_DictSpans, int]:
    pos += 1  # consume 'd'
    result: _DictSpans = {}
    while data[pos : pos + 1] != b"e":
        if pos >= len(data):
            raise BencodeError("unterminated dictionary")
        key, pos = _parse(data, pos)
        if not isinstance(key, bytes):
            raise BencodeError("dictionary key is not a byte string")
        value_start = pos
        value, pos = _parse(data, pos)
        result[key] = (value, value_start, pos)
    return result, pos + 1  # consume 'e'


def _parse_list(data: bytes, pos: int) -> tuple[list[object], int]:
    pos += 1  # consume 'l'
    result: list[object] = []
    while data[pos : pos + 1] != b"e":
        if pos >= len(data):
            raise BencodeError("unterminated list")
        value, pos = _parse(data, pos)
        result.append(value)
    return result, pos + 1  # consume 'e'


def _parse_int(data: bytes, pos: int) -> tuple[int, int]:
    end = data.find(b"e", pos)
    if end == -1:
        raise BencodeError("unterminated integer")
    try:
        value = int(data[pos + 1 : end])
    except ValueError as exc:
        raise BencodeError(f"invalid integer at position {pos}") from exc
    return value, end + 1


def _parse_bytes(data: bytes, pos: int) -> tuple[bytes, int]:
    colon = data.find(b":", pos)
    if colon == -1:
        raise BencodeError("invalid byte string: missing ':'")
    try:
        length = int(data[pos:colon])
    except ValueError as exc:
        raise BencodeError(f"invalid byte-string length at position {pos}") from exc
    start = colon + 1
    end = start + length
    if end > len(data):
        raise BencodeError("byte string exceeds available data")
    return data[start:end], end
