"""Tests for reading info hashes from ``.torrent`` files."""

from __future__ import annotations

import pytest

from qbit_torrent_files_cleaner.torrents import (
    BencodeError,
    TorrentHashes,
    _extract_hashes,
    _parse,
    read_torrent_hashes,
)


def test_reads_v1_infohash(v1_torrent):
    path, infohash = v1_torrent
    hashes = read_torrent_hashes(path)
    assert hashes is not None
    assert hashes.v1 == infohash
    assert hashes.v2 is None
    assert hashes.as_set() == {infohash}


def test_reads_v1_and_v2_for_hybrid(v2_torrent):
    path, v1, v2 = v2_torrent
    hashes = read_torrent_hashes(path)
    assert hashes is not None
    assert hashes.v1 == v1
    assert hashes.v2 == v2
    assert hashes.as_set() == {v1, v2}


def test_hash_is_lowercase(v2_torrent):
    path, _, _ = v2_torrent
    hashes = read_torrent_hashes(path)
    assert hashes is not None
    assert hashes.v1 == hashes.v1.lower()
    assert hashes.v2 == hashes.v2.lower()


def test_missing_file_returns_none(tmp_path):
    assert read_torrent_hashes(tmp_path / "nope.torrent") is None


def test_corrupt_file_returns_none(tmp_path):
    path = tmp_path / "corrupt.torrent"
    path.write_bytes(b"not a torrent")
    assert read_torrent_hashes(path) is None


def test_missing_info_dict_returns_none(tmp_path):
    path = tmp_path / "no-info.torrent"
    path.write_bytes(b"d8:announce4:teste")
    assert read_torrent_hashes(path) is None


def test_as_set_ignores_empty():
    assert TorrentHashes(v1=None, v2=None).as_set() == set()
    assert TorrentHashes(v1="abc", v2=None).as_set() == {"abc"}


def test_permission_error_returns_none(tmp_path, monkeypatch):
    path = tmp_path / "locked.torrent"
    path.write_bytes(b"d4:infod3:foo3:bareee")

    def boom(*_args, **_kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr("pathlib.Path.read_bytes", boom)
    assert read_torrent_hashes(path) is None


def test_parse_roundtrips_nested_structures():
    # d 'a' -> [ i1e i2e ], 'b' -> 'x' e
    value, _ = _parse(b"d1:al i1e i2e e1:b1:xe".replace(b" ", b""), 0)
    assert isinstance(value, dict)
    # list value is stored directly; dict values are (value, start, end) spans
    a_value, _start, _end = value[b"a"]
    assert a_value == [1, 2]


@pytest.mark.parametrize(
    "data",
    [
        b"",  # empty
        b"x",  # invalid token
        b"d",  # unterminated dict
        b"l",  # unterminated list
        b"i123",  # unterminated int
        b"ixe",  # non-numeric int
        b"3abc",  # byte string missing ':'
        b"5:ab",  # byte string longer than data
        b"di3e3:onee",  # non-bytes dict key
        b"1x:a",  # invalid byte-string length
    ],
)
def test_malformed_bencode_raises(data):
    with pytest.raises(BencodeError):
        _parse(data, 0)


def test_extract_hashes_rejects_non_dict_top_level():
    with pytest.raises(BencodeError, match="not a dictionary"):
        _extract_hashes(b"i5e")


def test_extract_hashes_rejects_non_dict_info():
    with pytest.raises(BencodeError, match="'info' is not a dictionary"):
        _extract_hashes(b"d4:infoi5ee")
