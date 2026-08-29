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

## Operator-only emoji administration

Emoji administration is deliberately not exposed as a Discord command. A local CLI lets an
operator—or Codex acting for the operator—discover servers, create restorable backups, add emoji
images, remove or rename exact emojis, and restore missing emojis. It uses the same live bot token
by default; place `--beta` before the subcommand to use the beta bot instead.

Start by discovering the server IDs available to the bot, then inspect or back up one server:

```bash
./start.sh emojis servers
./start.sh emojis list --guild SERVER_ID
./start.sh emojis backup --guild SERVER_ID
./start.sh emojis backup-all
./start.sh emojis verify --from .emoji-backups/SERVER_ID/TIMESTAMP
```

Mutation commands are previews unless both `--apply` and an explicit Discord audit-log reason are
provided. Every applied mutation first creates a full server emoji backup and aborts if that safety
backup fails.

```bash
# Preview and then add one image (the name must be 2-32 letters, numbers, or underscores).
./start.sh emojis add --guild SERVER_ID emojis/new.png --name new_emoji
./start.sh emojis add --guild SERVER_ID emojis/new.png --name new_emoji \
  --apply --reason "Requested emoji upload"

# A directory is added recursively. Numeric filename prefixes are removed and punctuation becomes _.
./start.sh emojis add --guild SERVER_ID emojis/pepe_emojis

# Exact name or numeric emoji ID may be used. An ambiguous name must be replaced with an ID.
./start.sh emojis rename --guild SERVER_ID --emoji old_name --name new_name
./start.sh emojis remove --guild SERVER_ID --emoji EMOJI_ID

# Preview restoration of missing, non-managed emojis from a generated backup.
./start.sh emojis restore --guild SERVER_ID --from .emoji-backups/SERVER_ID/TIMESTAMP
```

Backups are stored under ignored `.emoji-backups/SERVER_ID/TIMESTAMP/` and contain the original
PNG/GIF assets plus a versioned `manifest.json` with IDs, names, role restrictions, byte counts,
and SHA-256 hashes. Restore verifies each asset before uploading it. Cross-server restores are
rejected unless `--allow-cross-server` is explicitly supplied. The bot needs Discord's Create Guild
Expressions permission for additions and Manage Guild Expressions permission for emojis it did not
create.

For a reviewed whole-collection reorganization, `scripts/organize_emoji_collection.py` converts the
standalone review gallery into `emojis/organization-plan.json`, a server dump, organized local
folders, and `emojis/catalog.csv`. `scripts/sync_emoji_plan.py` validates every planned name, asset,
hash, duplicate disposition, live emoji ID, and current per-type capacity before doing anything.
It is a dry run unless `--apply --reason` is supplied, creates one full safety backup before the
first mutation, and can safely resume a partially completed plan by ID and final name.

```bash
python scripts/sync_emoji_plan.py --plan emojis/organization-plan.json
python scripts/sync_emoji_plan.py --plan emojis/organization-plan.json \
  --apply --reason "Owner approved reviewed emoji reorganization"
```

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
./start.sh test   # run lint, type, shell, test, coverage, and dependency-audit checks
./start.sh        # start wggbot-live with LIVE_DISCORD_TOKEN
./start.sh dev    # start wggbot-dev with BETA_DISCORD_TOKEN
./start.sh stop   # stop and remove either bot container
./start.sh emojis # run the operator-only emoji administration CLI
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

Run the complete check suite in the project's development image:

```bash
./start.sh test
```

Or install and run the same checks directly in a compatible Python 3.13 environment:

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
