# ── Base Image ────────────────────────────────────────────────
FROM python:3.12-slim

# ── Metadata ──────────────────────────────────────────────────
LABEL maintainer="FA23-BAI-010"
LABEL description="SAMAA TV News Scraper API"

# ── System Dependencies ───────────────────────────────────────
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    unzip \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libgdk-pixbuf2.0-0 \
    libnspr4 \
    libnss3 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libxss1 \
    libxtst6 \
    xdg-utils \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# ── Install Google Chrome Stable ──────────────────────────────
RUN wget -q -O /tmp/chrome.deb \
    https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get update \
    && apt-get install -y /tmp/chrome.deb \
    && rm /tmp/chrome.deb \
    && rm -rf /var/lib/apt/lists/*

# ── Working Directory ─────────────────────────────────────────
WORKDIR /app

# ── Python Dependencies ───────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Download ChromeDriver at build time ───────────────────────
RUN python -c "from webdriver_manager.chrome import ChromeDriverManager; ChromeDriverManager().install()"

# ── Copy App Code ─────────────────────────────────────────────
COPY . .

# ── Expose API Port ───────────────────────────────────────────
EXPOSE 7000

# ── Start Flask Server ────────────────────────────────────────
CMD ["python", "app.py"]