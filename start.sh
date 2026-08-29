#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="${WGGBOT_IMAGE:-wggbot:latest}"
DEV_IMAGE_NAME="${WGGBOT_DEV_IMAGE:-wggbot:development}"
LIVE_CONTAINER="${WGGBOT_CONTAINER:-wggbot-live}"
DEV_CONTAINER="${WGGBOT_DEV_CONTAINER:-wggbot-dev}"
HOST_PORT="${WGGBOT_PORT:-32401}"
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${PROJECT_ROOT}/.env"
COOKIE_FILE="${PROJECT_ROOT}/cookies.txt"
EMOJI_BACKUP_DIR="${WGGBOT_EMOJI_BACKUP_DIR:-${PROJECT_ROOT}/.emoji-backups}"

build_image() {
    docker build --pull -t "${IMAGE_NAME}" -f "${PROJECT_ROOT}/Dockerfile" "${PROJECT_ROOT}"
}

build_dev_image() {
    docker build --pull --target development -t "${DEV_IMAGE_NAME}" \
        -f "${PROJECT_ROOT}/Dockerfile" "${PROJECT_ROOT}"
}

run_tests() {
    build_dev_image
    docker run --rm \
        --init \
        --read-only \
        --cap-drop ALL \
        --security-opt no-new-privileges:true \
        --tmpfs /tmp:rw,nosuid,size=512m \
        --env XDG_CACHE_HOME=/tmp/cache \
        --env COVERAGE_FILE=/tmp/.coverage \
        -v "${PROJECT_ROOT}:/app:ro" \
        "${DEV_IMAGE_NAME}" \
        sh -c 'ruff check --no-cache . && ruff format --no-cache --check . && mypy --cache-dir /tmp/mypy src/wggbot && shellcheck start.sh && pytest -p no:cacheprovider && pip-audit --disable-pip -r requirements.lock'
}

stop_container() {
    local container_name="$1"
    docker rm -f "${container_name}" >/dev/null 2>&1 || true
}

stop_all() {
    stop_container "${LIVE_CONTAINER}"
    stop_container "${DEV_CONTAINER}"
}

start_container() {
    local container_name="$1"
    local debug_mode="$2"

    if [[ ! -f "${ENV_FILE}" ]]; then
        echo "Missing ${ENV_FILE}; copy .env.example and configure it first." >&2
        exit 1
    fi
    if [[ "$(id -u)" == "0" ]]; then
        if [[ -f "${COOKIE_FILE}" ]]; then
            chown 10001:10001 "${COOKIE_FILE}"
            chmod 0600 "${COOKIE_FILE}"
        fi
    fi
    if ! docker image inspect "${IMAGE_NAME}" >/dev/null 2>&1; then
        build_image
    fi
    stop_all
    docker run -d \
        --name "${container_name}" \
        --restart unless-stopped \
        --init \
        --env-file "${ENV_FILE}" \
        --env "WGGBOT_DEBUG=${debug_mode}" \
        --read-only \
        --cap-drop ALL \
        --security-opt no-new-privileges:true \
        --tmpfs /tmp:rw,nosuid,noexec,size=256m \
        -p "127.0.0.1:${HOST_PORT}:8080" \
        -v "${PROJECT_ROOT}:/app:ro" \
        "${IMAGE_NAME}"
}

run_emoji_admin() {
    if [[ ! -f "${ENV_FILE}" ]]; then
        echo "Missing ${ENV_FILE}; copy .env.example and configure it first." >&2
        exit 1
    fi
    if ! docker image inspect "${IMAGE_NAME}" >/dev/null 2>&1; then
        build_image
    fi
    mkdir -p "${EMOJI_BACKUP_DIR}"
    if [[ "$(id -u)" == "0" ]]; then
        chown 10001:10001 "${EMOJI_BACKUP_DIR}"
        chmod 0750 "${EMOJI_BACKUP_DIR}"
    elif [[ ! -w "${EMOJI_BACKUP_DIR}" ]]; then
        echo "Emoji backup directory is not writable: ${EMOJI_BACKUP_DIR}" >&2
        exit 1
    fi

    docker run --rm \
        --init \
        --env-file "${ENV_FILE}" \
        --read-only \
        --cap-drop ALL \
        --security-opt no-new-privileges:true \
        --tmpfs /tmp:rw,nosuid,noexec,size=64m \
        -v "${PROJECT_ROOT}:/app:ro" \
        -v "${EMOJI_BACKUP_DIR}:/backups:rw" \
        "${IMAGE_NAME}" \
        python -m wggbot.emoji_admin --backup-root /backups "$@"
}

case "${1:-start}" in
    build)
        build_image
        ;;
    test)
        run_tests
        ;;
    start)
        start_container "${LIVE_CONTAINER}" false
        ;;
    dev)
        start_container "${DEV_CONTAINER}" true
        ;;
    stop)
        stop_all
        ;;
    emoji|emojis)
        shift
        run_emoji_admin "$@"
        ;;
    *)
        echo "Usage: ./start.sh [build|test|start|dev|stop|emojis ...]" >&2
        exit 2
        ;;
esac
