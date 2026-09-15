"""Command-line entry point for qbit-torrent-files-cleaner."""

from __future__ import annotations

import argparse
import logging
import os
from collections.abc import Sequence

from qbit_torrent_files_cleaner import __version__
from qbit_torrent_files_cleaner.arr import ArrError, build_arr_clients
from qbit_torrent_files_cleaner.client import QBittorrentClient, QBittorrentError
from qbit_torrent_files_cleaner.config import Config, ConfigError
from qbit_torrent_files_cleaner.handle_unregistered import handle_unregistered
from qbit_torrent_files_cleaner.logging_setup import FORMATS, TEXT, configure_logging
from qbit_torrent_files_cleaner.monitor_completed import monitor_completed

logger = logging.getLogger("qbit_torrent_files_cleaner")

DEFAULT_CONFIG_PATH = "/config/config.yaml"
LOG_FORMAT_ENV = "QBIT_CLEANER_LOG_FORMAT"


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser."""
    parser = argparse.ArgumentParser(
        prog="qbit-torrent-files-cleaner",
        description="Keep a qBittorrent completed directory tidy.",
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to the YAML config file (default: {DEFAULT_CONFIG_PATH}).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO).",
    )
    parser.add_argument(
        "--log-format",
        default=os.environ.get(LOG_FORMAT_ENV, TEXT),
        choices=list(FORMATS),
        help=(
            "Log output format: 'text' for humans, 'json' for line-delimited JSON "
            f"suited to log shippers (default: text, or ${LOG_FORMAT_ENV})."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run qbit-torrent-files-cleaner. Returns a process exit code."""
    args = build_parser().parse_args(argv)
    configure_logging(args.log_level, args.log_format)

    try:
        config = Config.load(args.config)
    except ConfigError as exc:
        logger.error("%s", exc)
        return 2

    if not (config.commands.monitor_completed or config.commands.handle_unregistered):
        logger.info("No commands enabled in config; nothing to do.")
        return 0

    unregistered_result = None
    try:
        client = QBittorrentClient(config.qbittorrent)
        client.connect()
        if config.commands.monitor_completed:
            monitor_completed(config, client)
        if config.commands.handle_unregistered:
            unregistered_result = handle_unregistered(config, client, build_arr_clients(config))
    except (QBittorrentError, ArrError) as exc:
        logger.error("%s", exc)
        return 1
    except ValueError as exc:
        logger.error("%s", exc)
        return 2
    except Exception:
        logger.exception("Unexpected error")
        return 1

    if unregistered_result is not None and unregistered_result.errors:
        logger.error(
            "handle_unregistered finished with %d error(s); see the log above.",
            unregistered_result.errors,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
