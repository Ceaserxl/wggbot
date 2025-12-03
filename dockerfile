FROM python:3.13-slim

WORKDIR /app
COPY . /app

# -----------------------------------------
# System deps
# -----------------------------------------
RUN apt-get update -y
RUN apt-get install -y --no-install-recommends locales
RUN apt-get install -y --no-install-recommends ca-certificates
RUN apt-get install -y --no-install-recommends ffmpeg
RUN apt-get install -y --no-install-recommends curl
RUN apt-get install -y --no-install-recommends wget
RUN apt-get install -y --no-install-recommends gnupg
RUN apt-get install -y --no-install-recommends screen
RUN apt-get install -y --no-install-recommends xz-utils

# Locale
RUN sed -i 's/^# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen
RUN locale-gen en_US.UTF-8
RUN update-ca-certificates

# Clean
RUN rm -rf /var/lib/apt/lists/*

# -----------------------------------------
# Python deps
# -----------------------------------------
RUN pip install --upgrade pip
RUN pip install -r /app/requirements.txt

# -----------------------------------------
# Playwright
# -----------------------------------------
RUN playwright install
RUN playwright install-deps

# -----------------------------------------
# Locale exports
# -----------------------------------------
ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8

# -----------------------------------------
# Entry command (same as your compose file)
# -----------------------------------------
CMD ["python", "/app/bot.py"]