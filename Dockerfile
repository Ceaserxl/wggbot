FROM python:3.13.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src

RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates curl ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 wggbot \
    && useradd --uid 10001 --gid wggbot --no-create-home --home-dir /app wggbot

WORKDIR /app
COPY requirements.lock /tmp/requirements.lock
RUN python -m pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock

USER wggbot
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl --fail --silent http://127.0.0.1:8080/ready >/dev/null || exit 1
CMD ["python", "-m", "wggbot"]

FROM runtime AS development

USER root
COPY requirements-dev.lock /tmp/requirements-dev.lock
RUN apt-get update \
    && apt-get install --no-install-recommends -y shellcheck \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir --require-hashes -r /tmp/requirements-dev.lock
USER wggbot

FROM runtime AS production
