# WGGBot — Discord Bot (Chat + Images)

Multi-feature Discord bot with:
- OpenAI (ChatGPT / DALL·E) *(optional)*
- Stable Diffusion WebUI API *(optional)*

---

## Quick Start

    git clone https://github.com/Ceaserxl/WGGBot.git
    cd WGGBot
    cp .env.example .env            # fill this in
    chmod +x ./dbot
    ./dbot install                  # creates venv, installs deps, installs global "dbot"
    dbot start                      # run bot in a screen session

**Common commands**

    dbot start       # start bot (detached screen)
    dbot stop        # stop bot
    dbot restart     # stop + start
    dbot log         # tail the log
    dbot attach      # attach to the screen session
    dbot venv        # open a subshell with the venv active
    dbot export      # write requirements.txt from current venv

---

## Environment (.env)

Create `.env` (or edit after copying from `.env.example`):

    # Discord
    LIVE_DISCORD_TOKEN=
    BETA_DISCORD_TOKEN=

    # Optional services
    OPENAI_API_KEY=
    SD_API_URL=
    OLLAMA_IP=
    OLLAMA_CHANNEL_ID=
    OLLAMA_LIVE_CHANNEL_ID=

    # App / model (optional defaults)
    APP_URL=
    CHATGPT_MODEL=gpt-4.1-nano

> Keep `.env` out of git. Commit a sanitized `.env.example`.

---

## Requirements

- Python 3.10+ (recommended)
- `screen` (for background sessions)
- Stable Diffusion WebUI API *(optional, if using SD features)*
- OpenAI API key *(optional, if using ChatGPT/DALL·E)*

Ubuntu/Debian:

    sudo apt update
    sudo apt install -y python3 python3-venv screen

---

## Manual Setup (if not using `dbot install`)

    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    python main.py

---

## Tips

- Update deps later:

      dbot venv
      pip install --upgrade -r requirements.txt
      dbot export

- If `dbot` command not found:

      echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc

---

## Features

- **Chat** via OpenAI (if configured)
- **Image generation** via Stable Diffusion (if configured)
- **Live/Beta tokens** for staging vs production
- **One-command lifecycle** with `dbot` (start/stop/restart/log/attach/venv/export)
