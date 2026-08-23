# WGGBot

WGGBot is a modular Discord bot for voice playback, local Ollama prompts, and optional ComfyUI
image generation. Modules can be enabled, disabled, or reloaded while the Discord process remains
online.

## Current modules

| Module | Default | Commands | Purpose |
| --- | --- | --- | --- |
| `musicplayer` | enabled | `/music ...` | Search, URLs, playlists, queues, voice controls, and optional Spotify matching |
| `ollama` | enabled | `/ollama ...` | Prompt and inspect a configured Ollama server |
| `stablediffusion` | disabled | `/imagine` | Generate through the bundled ComfyUI workflow when explicitly enabled |

`discord.Intents.all()` is intentional. Enable the corresponding privileged intents for the bot in
the Discord Developer Portal.

## Setup

The supported runtime is Docker on Python 3.13. Source is mounted into the container at `/app`; it
is not copied into the application image.

```bash
cp .env.example .env
# Edit .env and set LIVE_DISCORD_TOKEN (and BETA_DISCORD_TOKEN when used).
./start.sh build
./start.sh
```

Lifecycle commands:

```bash
./start.sh build  # build/pull dependencies
./start.sh        # replace and start wggbot-live with LIVE_DISCORD_TOKEN
./start.sh dev    # replace and start wggbot-dev with BETA_DISCORD_TOKEN
./start.sh stop   # stop and remove both live and development containers
```

Live and development runs are mutually exclusive because Discord permits only one active session
per bot token and both use the same local health port. Development module state is isolated in
ignored `data-dev/`; production continues to use `data/`.

The container runs as a non-root user with a read-only root filesystem, no Linux capabilities, and
`no-new-privileges`. Its health endpoint is bound to `127.0.0.1:32401` on the host. Docker checks
`/ready`; readiness requires an active Discord connection.

## Migrating the old configuration

For an installation that still has `settings.ini`, run this once before starting the new image:

```bash
python scripts/migrate_settings.py
```

It transfers current values—including the existing Discord tokens—into ignored `.env`, sets mode
`0600`, and removes the migrated token keys from `settings.ini`. It never prints token values.

## Live module management

These commands are restricted to the Discord application owner:

- `/modules list`
- `/modules enable name`
- `/modules disable name`
- `/modules reload name`

State is persisted atomically in `data/modules.json`. Enabling or reloading also synchronizes the
application-command tree. A failed module load is reported as `error` in `/modules list` and the
health response; it does not masquerade as a successful initialization.

Stable Diffusion is deliberately disabled on a fresh installation. Configure `COMFYUI_URL`, then
run `/modules enable stablediffusion` when it should become available.

## Music player

Use `/music play` with search text, a supported media URL, a playlist URL, or an optional Spotify
track/album/playlist URL. The player uses one queue worker per Discord guild. Only that worker
advances playback, including after a skip, which prevents overlapping consumers and timing races.
FFmpeg output is normalized to 48 kHz stereo for Discord voice.

Commands include:

- `play`, `now`, `queue`, and `history`
- `pause`, `resume`, `skip`, `stop`, and `disconnect`
- `clear`, `remove`, `move`, and `shuffle`
- `volume`, `repeat`, and `sources`

Users must be in the bot's voice channel to control active playback. Play requests have per-user,
per-guild cooldowns, and queue/playlist sizes are bounded by configuration.

### YouTube subscription cookie

Export the subscription cookie as a Netscape-format cookie file and place it at the ignored path
configured by `YTDLP_COOKIE_FILE` (default `/app/cookies.txt`). When run as root, `start.sh` secures
the default file to mode `0600` under the container user's ownership. The bot passes it through
yt-dlp's `cookiefile` option. `/music sources` reports only whether the file is mounted; it never
exposes its contents.

### Spotify behavior

Set `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` to enable Spotify links. The bot retrieves track
metadata through Spotify's client-credentials API, then searches for a playable version through
yt-dlp. It does not claim to stream Spotify subscription audio, which Spotify does not provide to
Discord bots. Playlist and album metadata are paged up to `MUSIC_MAX_PLAYLIST`.

yt-dlp-supported sources such as YouTube, SoundCloud, Bandcamp, and direct media URLs can be used
without Spotify credentials. Actual availability remains subject to each source and its terms.

## Configuration

All supported keys and defaults are documented in `.env.example`. Important controls include:

- `WGGBOT_DEBUG`: chooses the beta token when true
- `SYNC_COMMANDS`: synchronize global application commands during startup
- `OLLAMA_URL` and `OLLAMA_MODEL`
- `COMFYUI_URL`
- `MUSIC_MAX_QUEUE`, `MUSIC_MAX_PLAYLIST`, `MUSIC_IDLE_TIMEOUT`, and `MUSIC_DEFAULT_VOLUME`
- `YTDLP_COOKIE_FILE`

Do not commit `.env`, cookies, runtime `data`, or logs.

## Development and verification

Generate locks from the concise input files with a compatible lock environment:

```bash
pip-compile --generate-hashes --strip-extras -o requirements.lock requirements.in
pip-compile --generate-hashes --strip-extras -o requirements-dev.lock requirements-dev.in
```

Install and validate:

```bash
python -m pip install --require-hashes -r requirements-dev.lock
ruff check .
ruff format --check .
mypy bot.py core modules
shellcheck start.sh
python -m pytest
pip-audit -r requirements.lock
docker build -t wggbot:test .
```

CI runs the same lint, format, type, shell, test, dependency-audit, and container-build gates. Logs
go to stdout for Docker to manage and no longer clear previous files during import or startup.
