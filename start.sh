#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="${WGGBOT_IMAGE:-wggbot:latest}"
LIVE_CONTAINER="${WGGBOT_CONTAINER:-wggbot-live}"
DEV_CONTAINER="${WGGBOT_DEV_CONTAINER:-wggbot-dev}"
HOST_PORT="${WGGBOT_PORT:-32401}"
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${PROJECT_ROOT}/.env"
COOKIE_FILE="${PROJECT_ROOT}/cookies.txt"

build_image() {
    docker build --pull -t "${IMAGE_NAME}" -f "${PROJECT_ROOT}/Dockerfile" "${PROJECT_ROOT}"
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

case "${1:-start}" in
    build)
        build_image
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
    *)
        echo "Usage: ./start.sh [build|start|dev|stop]" >&2
        exit 2
        ;;
esac
