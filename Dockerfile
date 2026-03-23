# ============================================
# Set base image 
# ============================================
FROM python:3.13-slim

# ============================================
# Copy project files
# ============================================
WORKDIR /app

# ============================================
# Install system deps
# ============================================
RUN apt-get update && apt-get install -y \
    php \
    php-fpm \
    php-mysql \
    php-cli \
    nginx \
    curl \
    wget \
    git \
    docker.io \
    ffmpeg \
    openvpn \
    procps \
    xvfb \
    libgl1 \
    libglib2.0-0 \
    libnss3 \
    libxss1 \
    libasound2 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libdrm2 \
    libxshmfence1 \
    libgbm1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libxkbcommon0 \
    libasound2 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------
# Python dependencies
# ---------------------------------------------------
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt