"""Shared test fixtures and bencode helpers."""

from __future__ import annotations

import hashlib

import pytest


def bencode(value: object) -> bytes:
    """Minimal bencode encoder used to build torrent fixtures."""
    if isinstance(value, bool):  # guard: bool is an int subclass
        raise TypeError("bool is not bencodable")
    if isinstance(value, int):
        return b"i" + str(value).encode() + b"e"
    if isinstance(value, bytes):
        return str(len(value)).encode() + b":" + value
    if isinstance(value, str):
        return bencode(value.encode())
    if isinstance(value, list):
        return b"l" + b"".join(bencode(item) for item in value) + b"e"
    if isinstance(value, dict):
        items = b"".join(bencode(key) + bencode(val) for key, val in sorted(value.items()))
        return b"d" + items + b"e"
    raise TypeError(f"cannot bencode {type(value)!r}")


def make_v1_torrent(name: str = "example") -> tuple[bytes, str]:
    """Return ``(file_bytes, infohash_v1)`` for a classic v1 torrent."""
    info = {
        b"name": name.encode(),
        b"piece length": 16384,
        b"pieces": b"\x00" * 20,
        b"length": 12345,
    }
    info_bytes = bencode(info)
    infohash = hashlib.sha1(info_bytes).hexdigest()
    file_bytes = bencode({b"announce": b"http://tracker.example", b"info": info})
    return file_bytes, infohash


def make_v2_torrent(name: str = "example-v2") -> tuple[bytes, str, str]:
    """Return ``(file_bytes, infohash_v1, infohash_v2)`` for a hybrid torrent."""
    info = {
        b"name": name.encode(),
        b"piece length": 16384,
        b"meta version": 2,
        b"file tree": {name.encode(): {b"": {b"length": 500, b"pieces root": b"\x01" * 32}}},
        b"pieces": b"\x00" * 20,
        b"length": 500,
    }
    info_bytes = bencode(info)
    infohash_v1 = hashlib.sha1(info_bytes).hexdigest()
    infohash_v2 = hashlib.sha256(info_bytes).hexdigest()
    file_bytes = bencode({b"info": info})
    return file_bytes, infohash_v1, infohash_v2


@pytest.fixture
def v1_torrent(tmp_path):
    """Write a v1 torrent to a temp dir; yield ``(path, infohash)``."""
    data, infohash = make_v1_torrent()
    path = tmp_path / "v1.torrent"
    path.write_bytes(data)
    return path, infohash


@pytest.fixture
def v2_torrent(tmp_path):
    """Write a hybrid torrent to a temp dir; yield ``(path, v1, v2)``."""
    data, v1, v2 = make_v2_torrent()
    path = tmp_path / "v2.torrent"
    path.write_bytes(data)
    return path, v1, v2
