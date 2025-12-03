FROM python:3.13-slim

# -----------------------------------------
# System deps
# -----------------------------------------
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
        locales \
        ca-certificates \
        ffmpeg \
        curl \
        wget \
        gnupg \
        screen \
        xz-utils && \
    sed -i 's/^# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen && \
    locale-gen en_US.UTF-8 && \
    update-ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --upgrade pip && \
    pip install -r requirements.txt && \
    playwright install-deps && \
    playwright install && \
ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8

WORKDIR /app

# Copy project files into image
COPY . /app
