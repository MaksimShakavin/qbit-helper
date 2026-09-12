"""Remove orphaned ``.torrent`` files from a completed directory."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from qbit_torrent_files_cleaner.client import QBittorrentClient
from qbit_torrent_files_cleaner.config import Config
from qbit_torrent_files_cleaner.torrents import read_torrent_hashes

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MonitorResult:
    """Summary of a cleanup run."""

    processed: int = 0
    removed: int = 0
    skipped: int = 0


def monitor_completed(config: Config, client: QBittorrentClient) -> MonitorResult:
    """Delete ``.torrent`` files whose torrent is no longer tracked in a wanted category.

    A file is kept when either of its info hashes (v1 or v2) is present in
    qBittorrent under one of the configured categories. When ``commands.dry`` is
    true nothing is deleted; the actions that *would* be taken are logged instead.
    """
    settings = config.monitor_completed
    is_dry_run = config.commands.dry

    completed_dir = Path(settings.completed_dir)
    if not settings.completed_dir:
        raise ValueError("monitor_completed.completed_dir is not configured.")
    if not completed_dir.is_dir():
        raise ValueError(f"Completed directory does not exist: {completed_dir}")
    if not settings.categories:
        raise ValueError("monitor_completed.categories is empty; refusing to run.")

    logger.info("Collecting torrents for categories: %s", ", ".join(settings.categories))
    known_hashes = client.collect_hashes_for_categories(settings.categories)
    logger.info("qBittorrent is tracking %d matching info hashes", len(known_hashes))

    if is_dry_run:
        logger.info("Dry run enabled; no files will be deleted.")

    processed = 0
    removed = 0
    skipped = 0

    for torrent_file in sorted(completed_dir.glob("*.torrent")):
        processed += 1
        hashes = read_torrent_hashes(torrent_file)
        if hashes is None:
            logger.warning("Skipping unreadable torrent file: %s", torrent_file.name)
            skipped += 1
            continue

        if hashes.as_set() & known_hashes:
            continue

        logger.info("Removing orphaned torrent file: %s", torrent_file.name)
        if not is_dry_run:
            try:
                torrent_file.unlink()
            except OSError as exc:
                logger.error("Failed to remove %s: %s", torrent_file.name, exc)
                skipped += 1
                continue
        removed += 1

    logger.info(
        "Done. Processed %d file(s); %s %d; skipped %d.",
        processed,
        "would remove" if is_dry_run else "removed",
        removed,
        skipped,
    )
    return MonitorResult(processed=processed, removed=removed, skipped=skipped)
