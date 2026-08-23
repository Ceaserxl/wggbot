#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="${WGGBOT_IMAGE:-wggbot:latest}"
CONTAINER_NAME="${WGGBOT_CONTAINER:-wggbot-live}"
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${PROJECT_ROOT}/.env"
DATA_DIR="${PROJECT_ROOT}/data"
COOKIE_FILE="${PROJECT_ROOT}/cookies.txt"

build_image() {
    docker build --pull -t "${IMAGE_NAME}" -f "${PROJECT_ROOT}/Dockerfile" "${PROJECT_ROOT}"
}

stop_container() {
    docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
}

start_container() {
    if [[ ! -f "${ENV_FILE}" ]]; then
        echo "Missing ${ENV_FILE}; copy .env.example and configure it first." >&2
        exit 1
    fi
    if [[ "$(id -u)" == "0" ]]; then
        install -d -m 0770 -o 10001 -g 10001 "${DATA_DIR}"
        if [[ -f "${COOKIE_FILE}" ]]; then
            chown 10001:10001 "${COOKIE_FILE}"
            chmod 0600 "${COOKIE_FILE}"
        fi
    else
        mkdir -p "${DATA_DIR}"
        chmod 0777 "${DATA_DIR}"
    fi
    if ! docker image inspect "${IMAGE_NAME}" >/dev/null 2>&1; then
        build_image
    fi
    stop_container
    docker run -d \
        --name "${CONTAINER_NAME}" \
        --restart unless-stopped \
        --init \
        --env-file "${ENV_FILE}" \
        --read-only \
        --cap-drop ALL \
        --security-opt no-new-privileges:true \
        --tmpfs /tmp:rw,nosuid,noexec,size=256m \
        -p "127.0.0.1:32401:8080" \
        -v "${PROJECT_ROOT}:/app:ro" \
        -v "${DATA_DIR}:/app/data:rw" \
        "${IMAGE_NAME}"
}

case "${1:-start}" in
    build)
        build_image
        ;;
    start)
        start_container
        ;;
    stop)
        stop_container
        ;;
    *)
        echo "Usage: ./start.sh [build|start|stop]" >&2
        exit 2
        ;;
esac
