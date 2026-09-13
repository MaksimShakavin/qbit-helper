"""Logging configuration: human-readable text or line-delimited JSON.

The JSON format emits one object per line with ``time``/``level``/``logger``/
``message`` fields so log processors can parse it natively and filter on a real
``level`` field rather than a regex over a text blob. Any structured fields
attached with ``logger.info(..., extra=...)`` are merged into the object too.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

TEXT = "text"
JSON = "json"
FORMATS = (TEXT, JSON)

_TEXT_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_TEXT_DATEFMT = "%Y-%m-%d %H:%M:%S"

# Standard ``LogRecord`` attributes; everything else on a record is a custom
# ``extra`` field worth emitting.
_RESERVED = frozenset(
    logging.makeLogRecord({}).__dict__.keys() | {"message", "asctime", "taskName"}
)


class JsonFormatter(logging.Formatter):
    """Format a record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "time": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload.setdefault(key, value)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str, log_format: str) -> None:
    """Install a stdout handler in the requested format on the root logger."""
    handler = logging.StreamHandler(sys.stdout)
    if log_format == JSON:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(fmt=_TEXT_FORMAT, datefmt=_TEXT_DATEFMT))

    root = logging.getLogger()
    for existing in root.handlers[:]:
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(getattr(logging, level))

    # These libraries are noisy at INFO; only surface their warnings and errors.
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("qbittorrentapi").setLevel(logging.WARNING)
