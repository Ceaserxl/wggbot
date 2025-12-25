#!/usr/bin/env bash
set -Eeuo pipefail

# ==========================================================
# CONFIG
# ==========================================================
VENV_PATH="python/linux/venv"
PYTHON_BIN="$VENV_PATH/bin/python"
ACTIVATE="$VENV_PATH/bin/activate"

BOT_SCRIPT="bot.py"
SCREEN_NAME="wggbot"

# ==========================================================
# HELPERS
# ==========================================================
pause() { read -rp "Press ENTER to continue..."; }

require_venv() {
    if [[ ! -f "$ACTIVATE" ]]; then
        echo "❌ Virtualenv not found at $ACTIVATE"
        exit 1
    fi
}

bot_running() {
    pgrep -f "$PYTHON_BIN .*${BOT_SCRIPT}" >/dev/null 2>&1
}

screen_running() {
    screen -list | grep -q "\.${SCREEN_NAME}"
}

start_attached() {
    require_venv

    if bot_running; then
        echo "⚠️ Bot is already running."
        return
    fi

    echo "🚀 Starting bot (attached)..."
    source "$ACTIVATE"
    exec "$PYTHON_BIN" "$BOT_SCRIPT"
}

start_detached() {
    require_venv

    if screen_running || bot_running; then
        echo "⚠️ Bot is already running."
        return
    fi

    echo "🚀 Starting bot (detached, screen '${SCREEN_NAME}')..."
    screen -S "$SCREEN_NAME" -dm bash -lc "
        source '$ACTIVATE' &&
        exec '$PYTHON_BIN' '$BOT_SCRIPT'
    "

    echo "✔ Bot started."
    echo "➡ Attach with: screen -r $SCREEN_NAME"
}

stop_bot() {
    if bot_running; then
        echo "⛔ Stopping bot..."
        pkill -f "$PYTHON_BIN .*${BOT_SCRIPT}" || true
    else
        echo "⚠️ Bot is not running."
    fi

    if screen_running; then
        screen -S "$SCREEN_NAME" -X quit || true
    fi
}

attach_bot() {
    if ! screen_running; then
        echo "❌ No detached session running."
        return
    fi

    screen -r "$SCREEN_NAME"
}

status_bot() {
    if bot_running; then
        echo "✔ Bot is running."
    else
        echo "❌ Bot is not running."
    fi

    if screen_running; then
        echo "📺 Detached screen session exists."
    fi
}

# ==========================================================
# ARG MODE
# ==========================================================
case "${1:-}" in
    -it)
        start_attached
        exit 0
        ;;
    -d)
        start_detached
        exit 0
        ;;
    stop)
        stop_bot
        exit 0
        ;;
    status)
        status_bot
        exit 0
        ;;
esac

# ==========================================================
# MENU MODE (DEFAULT)
# ==========================================================
while true; do
    clear
    echo "======================================="
    echo "        WGG BOT MANAGER (NO DOCKER)"
    echo "======================================="
    echo "[1] Start Bot (attached)"
    echo "[2] Start Bot (detached)"
    echo "[3] Stop Bot"
    echo "[4] Attach to Detached Bot"
    echo "[5] Status"
    echo "[Q] Quit"
    echo "---------------------------------------"
    read -rp "Select an option: " choice

    case "${choice,,}" in
        1) start_attached ; pause ;;
        2) start_detached ; pause ;;
        3) stop_bot ; pause ;;
        4) attach_bot ; pause ;;
        5) status_bot ; pause ;;
        q) exit 0 ;;
    esac
done
