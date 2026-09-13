"""Tests for logging configuration (text and JSON formats)."""

from __future__ import annotations

import json
import logging

import pytest

from qbit_torrent_files_cleaner.logging_setup import (
    JsonFormatter,
    configure_logging,
)


def _record(**kwargs):
    defaults = {
        "name": "qbit_torrent_files_cleaner.arr",
        "level": logging.INFO,
        "pathname": __file__,
        "lineno": 1,
        "msg": "hello %s",
        "args": ("world",),
        "exc_info": None,
    }
    defaults.update(kwargs)
    return logging.LogRecord(func=None, **defaults)


def test_json_formatter_emits_expected_fields():
    line = JsonFormatter().format(_record())
    payload = json.loads(line)
    assert payload["level"] == "INFO"
    assert payload["logger"] == "qbit_torrent_files_cleaner.arr"
    assert payload["message"] == "hello world"
    assert payload["time"].endswith("+00:00")  # UTC ISO 8601


def test_json_formatter_includes_exception():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = _record(msg="failed", args=(), exc_info=sys.exc_info())
    payload = json.loads(JsonFormatter().format(record))
    assert "ValueError: boom" in payload["exception"]


def test_json_formatter_merges_extra_fields():
    record = _record()
    record.torrent_hash = "abc123"
    payload = json.loads(JsonFormatter().format(record))
    assert payload["torrent_hash"] == "abc123"


def test_configure_logging_json_produces_parseable_line(capsys):
    configure_logging("INFO", "json")
    logging.getLogger("qbit_torrent_files_cleaner.test").info("structured %d", 1)
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)
    assert payload["message"] == "structured 1"
    assert payload["level"] == "INFO"


def test_configure_logging_text_is_not_json(capsys):
    configure_logging("INFO", "text")
    logging.getLogger("qbit_torrent_files_cleaner.test").info("plain")
    out = capsys.readouterr().out.strip()
    assert "plain" in out
    with pytest.raises(json.JSONDecodeError):
        json.loads(out)


def test_configure_logging_replaces_handlers():
    configure_logging("INFO", "text")
    configure_logging("DEBUG", "json")
    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert root.level == logging.DEBUG
