# qbit-torrent-files-cleaner

[![CI](https://github.com/MaksimShakavin/qbit-torrent-files-cleaner/actions/workflows/ci.yaml/badge.svg)](https://github.com/MaksimShakavin/qbit-torrent-files-cleaner/actions/workflows/ci.yaml)

A small CLI that keeps a qBittorrent *completed* directory tidy. It scans a
directory of `.torrent` files and removes any whose torrent is no longer present
in qBittorrent under a configured set of categories.

It talks to qBittorrent through the [Web API v2](https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API-(qBittorrent-4.1))
via [`qbittorrent-api`](https://pypi.org/project/qbittorrent-api/) and matches
files by their BitTorrent **v1 (SHA-1)** and **v2 (SHA-256)** info hashes, so
classic, v2, and hybrid torrents are all handled correctly.

## Why this exists

This tool exists for a specific home setup: making \*arr automations behave in the
[rutracker](https://rutracker.org) world. On rutracker, TV shows are published as
season packs — when a new episode airs, the uploader adds it to the *same* pack and
re-creates the torrent. [emonoda](https://github.com/mdevaev/emonoda) catches those
re-created torrents and re-uploads them to qBittorrent, so the season pack stays up
to date automatically.

qbit-torrent-files-cleaner is the housekeeping half of that flow. It prunes qBittorrent's
`FinishedTorrentExportDir`, which is
[append-only by design](https://github.com/qbittorrent/qBittorrent/issues/8486):
qBittorrent never deletes an exported `.torrent` when its torrent is removed. That
directory is exactly what emonoda watches (its `torrents_dir`), but `emupdate` only
*updates* files, never prunes them — so stale `.torrent` files (from \*arr upgrades
or deletions) would accumulate forever and emonoda would waste a rutracker lookup on
each dead torrent. qbit-torrent-files-cleaner keeps the export feed in sync with the live torrent
set so emonoda only processes torrents that are still in the client.

For a real-world deployment of this qBittorrent → qbit-torrent-files-cleaner → emonoda flow, see
the [homelab README](https://github.com/MaksimShakavin/flux-homelab/blob/main/kubernetes/apps/default/qbittorrent/README.md).

## How it works

For each `*.torrent` file in `monitor_completed.completed_dir`:

1. The file's v1/v2 info hashes are computed from the exact bytes of its `info`
   dictionary.
2. If either hash matches a torrent in qBittorrent under one of the configured
   `categories`, the file is kept.
3. Otherwise the file is considered orphaned and removed (or, in dry-run mode,
   just logged).

## Installation

```bash
pip install git+https://github.com/MaksimShakavin/qbit-torrent-files-cleaner.git
```

Or, from a clone:

```bash
pip install -e ".[dev]"   # dev extras for tests, linting, type checking
```

## Usage

```bash
qbit-torrent-files-cleaner --config /path/to/config.yaml
```

Options:

- `--config PATH` — path to the YAML config (default: `/config/config.yaml`).
- `--log-level {DEBUG,INFO,WARNING,ERROR}` — verbosity (default: `INFO`).
- `--version` — print the version and exit.

## Configuration

See [`config.example.yaml`](./config.example.yaml) for a documented example.

```yaml
commands:
  dry: true # log only, delete nothing — flip to false when ready
  monitor_completed: true

qbittorrent:
  host: "http://localhost:8080"
  user: "admin"
  password: "adminadmin"
  verify_ssl: false

monitor_completed:
  completed_dir: "/downloads/completed"
  categories:
    - movies
    - tv
```

> **Tip:** leave `commands.dry: true` for the first run and check the logs before
> letting the tool delete anything.

## Development

```bash
pip install -e ".[dev]"
pytest              # run the test suite
ruff check src tests
ruff format src tests
mypy                # strict type checking
```

## Packaging

Container images are built and published from a downstream
[home-operations/containers](https://github.com/home-operations/containers)-style
fork, which clones this repository at a release tag and installs it. Releases and
tags are cut automatically by [release-please](https://github.com/googleapis/release-please)
on merges to `main`, so the container Renovate config can track new GitHub
releases of this repo.

## License

MIT
