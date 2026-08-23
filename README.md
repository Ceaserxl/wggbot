# WGGBot

WGGBot is a focused Discord music bot with interactive playback controls, paginated queues, media
search, playlists, and optional Spotify metadata matching.

## Music experience

`/music play` accepts search text, supported media URLs, playlists, and Spotify track, album, or
playlist links. Responses use Discord embeds with track artwork and queue metadata. The bot posts a
new now-playing card for each track with direct controls for:

- pause or resume;
- skip;
- open queue; and
- stop playback.

`/music queue` opens an eight-track page with first, previous, next, and last-page buttons. The same
menu also exposes skip, shuffle, and clear actions. Playback actions require the user to be in the
bot's voice channel; queue browsing does not.

The remaining commands cover direct queue and player management:

- `now`, `queue`, `history`, and `sources`;
- `pause`, `resume`, `skip`, `stop`, and `disconnect`;
- `clear`, `remove`, `move`, and `shuffle`; and
- `volume` and `repeat`.

## Project structure

```text
src/wggbot/
├── __main__.py          container and local entrypoint
├── app.py               Discord application lifecycle
├── health.py            container readiness server
├── logging.py           stdout logging and secret redaction
├── settings.py          typed environment configuration
└── music/
    ├── cog.py           slash commands and orchestration
    ├── models.py        track data model
    ├── player.py        per-server queue and voice worker
    ├── presentation.py  embeds and display formatting
    ├── resolver.py      yt-dlp and Spotify media resolution
    └── ui.py            buttons and queue pagination
tests/                   focused unit and interaction-contract tests
scripts/                 one-time operational utilities
```

The bot uses one queue worker per Discord server. Only that worker advances playback, including
after a skip, preventing overlapping queue consumers. FFmpeg output is normalized to Discord's
48 kHz stereo PCM contract.

## Setup and lifecycle

The supported runtime is Docker on Python 3.13. Source is mounted read-only into the container at
`/app`; the application image only contains system and locked Python dependencies.

```bash
cp .env.example .env
# Set LIVE_DISCORD_TOKEN and BETA_DISCORD_TOKEN.
./start.sh build
./start.sh dev
```

Lifecycle commands:

```bash
./start.sh build  # build or refresh the dependency image
./start.sh        # start wggbot-live with LIVE_DISCORD_TOKEN
./start.sh dev    # start wggbot-dev with BETA_DISCORD_TOKEN
./start.sh stop   # stop and remove either bot container
```

Live and development runs are mutually exclusive because both use the local health port. The
container runs as a non-root user with a read-only root filesystem, no Linux capabilities, and
`no-new-privileges`. Readiness is available at `http://127.0.0.1:32401/ready` and requires an active
Discord connection.

Enable all requested privileged intents for the application in the Discord Developer Portal;
`discord.Intents.all()` is an intentional bot requirement.

## Configuration

All supported keys and defaults are listed in `.env.example`. The primary controls are:

- `WGGBOT_DEBUG`, which selects the beta token when true;
- `SYNC_COMMANDS`, which synchronizes global application commands at startup;
- `MUSIC_MAX_QUEUE`, `MUSIC_MAX_PLAYLIST`, `MUSIC_IDLE_TIMEOUT`, and
  `MUSIC_DEFAULT_VOLUME`; and
- `YTDLP_COOKIE_FILE`, `SPOTIFY_CLIENT_ID`, and `SPOTIFY_CLIENT_SECRET`.

Do not commit `.env`, browser cookies, logs, or runtime data.

### YouTube subscription cookie

Export a Netscape-format cookie file to the ignored path configured by `YTDLP_COOKIE_FILE` (default
`/app/cookies.txt`). When run as root, `start.sh` secures the default file to mode `0600` under the
container user's ownership. `/music sources` reports whether the file is mounted without exposing
its contents.

### Spotify behavior

Spotify credentials enable metadata lookup. Spotify tracks are matched to a playable source
through yt-dlp; the bot does not claim to stream Spotify subscription audio. Playlist and album
metadata are paged up to `MUSIC_MAX_PLAYLIST`.

## Legacy migration

An installation that still has `settings.ini` can transfer its bot and music settings once:

```bash
PYTHONPATH=src python scripts/migrate_settings.py
```

The script writes ignored `.env` with mode `0600`, removes migrated secrets from `settings.ini`,
and never prints token values.

## Development and verification

Install and run the same checks used by CI:

```bash
python -m pip install --require-hashes -r requirements-dev.lock
ruff check .
ruff format --check .
mypy src/wggbot
shellcheck start.sh
python -m pytest
pip-audit -r requirements.lock
docker build -t wggbot:test .
```

Generate dependency locks from the concise inputs with a compatible lock environment:

```bash
pip-compile --generate-hashes --strip-extras -o requirements.lock requirements.in
pip-compile --generate-hashes --strip-extras -o requirements-dev.lock requirements-dev.in
```
