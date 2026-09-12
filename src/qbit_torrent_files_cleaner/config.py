"""Configuration loading and validation for qbit-torrent-files-cleaner."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigError(Exception):
    """Raised when the configuration file is missing or invalid."""


@dataclass(frozen=True)
class CommandConfig:
    """Toggles that decide which actions run and whether they are simulated."""

    dry: bool = True
    monitor_completed: bool = False


@dataclass(frozen=True)
class QBittorrentConfig:
    """Connection settings for the qBittorrent Web API."""

    host: str = "http://localhost:8080"
    user: str = ""
    password: str = ""
    verify_ssl: bool = False


@dataclass(frozen=True)
class MonitorCompletedConfig:
    """Settings for the completed-directory cleanup task."""

    completed_dir: str = ""
    categories: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Config:
    """Top-level application configuration."""

    commands: CommandConfig = field(default_factory=CommandConfig)
    qbittorrent: QBittorrentConfig = field(default_factory=QBittorrentConfig)
    monitor_completed: MonitorCompletedConfig = field(default_factory=MonitorCompletedConfig)

    @classmethod
    def load(cls, config_file: str | Path) -> Config:
        """Load configuration from a YAML file, filling in defaults for absent keys."""
        path = Path(config_file)
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise ConfigError(f"Config file not found: {path}") from exc
        except OSError as exc:
            raise ConfigError(f"Could not read config file {path}: {exc}") from exc

        try:
            data = yaml.safe_load(raw) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"Invalid YAML in config file {path}: {exc}") from exc

        if not isinstance(data, dict):
            raise ConfigError(f"Config file {path} must contain a YAML mapping at the top level.")

        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Config:
        """Build a :class:`Config` from a plain dictionary, validating the shape."""
        commands = _section(data, "commands")
        qbittorrent = _section(data, "qbittorrent")
        monitor = _section(data, "monitor_completed")

        categories = monitor.get("categories", [])
        if not isinstance(categories, list):
            raise ConfigError("monitor_completed.categories must be a list.")

        return cls(
            commands=CommandConfig(
                dry=bool(commands.get("dry", True)),
                monitor_completed=bool(commands.get("monitor_completed", False)),
            ),
            qbittorrent=QBittorrentConfig(
                host=str(qbittorrent.get("host", "http://localhost:8080")),
                user=str(qbittorrent.get("user", "")),
                password=str(qbittorrent.get("password", "")),
                # `disable_ssl` (legacy) is kept as an alias for backwards compatibility.
                verify_ssl=_verify_ssl(qbittorrent),
            ),
            monitor_completed=MonitorCompletedConfig(
                completed_dir=str(monitor.get("completed_dir", "")),
                categories=[str(category) for category in categories],
            ),
        )


def _section(data: dict[str, Any], key: str) -> dict[str, Any]:
    """Return a mapping section from the config, tolerating an absent or null value."""
    value = data.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"Config section '{key}' must be a mapping.")
    return value


def _verify_ssl(qbittorrent: dict[str, Any]) -> bool:
    """Resolve SSL verification, honouring the legacy ``disable_ssl`` key.

    ``verify_ssl`` takes precedence when present; otherwise ``disable_ssl: true``
    (the old semantics) maps to ``verify_ssl: false``.
    """
    if "verify_ssl" in qbittorrent:
        return bool(qbittorrent["verify_ssl"])
    if "disable_ssl" in qbittorrent:
        return not bool(qbittorrent["disable_ssl"])
    return False
