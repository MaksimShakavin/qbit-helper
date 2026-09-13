# qbit-torrent-files-cleaner

[![CI](https://github.com/MaksimShakavin/qbit-torrent-files-cleaner/actions/workflows/ci.yaml/badge.svg)](https://github.com/MaksimShakavin/qbit-torrent-files-cleaner/actions/workflows/ci.yaml)

A small CLI of housekeeping tasks for a qBittorrent + \*arr + rutracker setup:

- **`monitor_completed`** keeps a qBittorrent *completed* directory tidy — it scans a
  directory of `.torrent` files and removes any whose torrent is no longer present in
  qBittorrent under a configured set of categories.
- **`handle_unregistered`** detects torrents the tracker admins have deleted (they go
  *unregistered* in qBittorrent) and gets Radarr/Sonarr to blocklist the dead release
  and grab a replacement.

Each task is toggled independently in the config.

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

## Handling unregistered (tracker-deleted) torrents

This is the one manual step the rest of the flow could not automate. Radarr/Sonarr
grab a release from rutracker into qBittorrent, and emonoda keeps that `.torrent`
fresh as new episodes are added to the *same* forum topic. But sometimes the tracker
admins **delete the topic** (a better release exists, or the uploader broke the
rules). The torrent then goes **unregistered** — the tracker returns an error with a
message like *"Torrent not registered with this tracker"*. emonoda can't fix this (the
topic it would re-download is gone) and the \*arr apps don't re-grab on their own, so
no replacement arrives and, for ongoing series, no new episodes.

`handle_unregistered` closes that gap. For each torrent (optionally limited to the
configured `categories`) it reads the tracker status and, when the torrent is truly
unregistered — no working tracker *and* a not-working tracker whose message matches a
known pattern (so a tracker that is merely temporarily down is left alone) — it:

- **If the download is still in an \*arr queue:** deletes the queue item with
  *remove from client* + *blocklist* + *redownload*. The \*arr removes the torrent and
  its data from qBittorrent, blocklists the bad release, and searches for a
  replacement — the three manual steps in one call.
- **If the \*arr already imported it** (now just seeding, no queue item): looks the
  download up in the \*arr's history to find the movie/series, deletes the torrent and
  its data from qBittorrent, and triggers a targeted search (Radarr: movie search;
  Sonarr: series, or season when `season_search` is on and the season is known).
- **If it belongs to no configured \*arr:** logs a warning and leaves it for you to
  review — it never deletes something it can't attribute to Radarr/Sonarr.

Because the dead torrent leaves qBittorrent, its exported `.torrent` becomes an orphan
that a later `monitor_completed` run prunes, keeping the whole pipeline consistent.
It does **not** touch on-disk data that no torrent references (qbit-manage's "remove
orphans"), which can conflict with emonoda's data layout.

`dry: true` logs exactly what it *would* delete and search without touching anything —
run it that way first.

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
  dry: true # log only, change nothing — flip to false when ready
  monitor_completed: true
  handle_unregistered: false # needs radarr/sonarr configured below

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

handle_unregistered:
  categories: # leave empty to scan every category
    - movies
    - tv
  season_search: false # Sonarr: search the affected season instead of the series

# Only used by handle_unregistered; an instance is used only when url and api_key
# are both set.
radarr:
  url: "http://localhost:7878"
  api_key: ""
sonarr:
  url: "http://localhost:8989"
  api_key: ""
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
