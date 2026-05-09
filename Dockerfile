FROM python:3.12-slim-bookworm

LABEL maintainer="FA23-BAI-010"
LABEL description="SAMAA TV Scraper - FA23-BAI-010"

ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Install system deps + Chrome
RUN apt-get update && apt-get install -y \
    wget gnupg curl unzip xvfb libnss3 libgconf-2-4 libxi6 libatk1.0-0 \
    libatk-bridge2.0-0 libcups2 libxcomposite1 libxdamage1 libxrandr2 \
    libasound2 libpangocairo-1.0-0 libgtk-3-0 fonts-liberation xdg-utils \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    python -c "import nltk; nltk.download('punkt', quiet=True); nltk.download('punkt_tab', quiet=True); nltk.download('stopwords', quiet=True)"

COPY . .

EXPOSE 7000

CMD ["python", "app.py"]
