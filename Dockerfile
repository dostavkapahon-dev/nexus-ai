# NEXUS AI — образ для 24/7-хостинга (Oracle Always Free ARM/AMD и любой Docker-хост).
# Внутри: FastAPI + планировщик + Telegram-бот + серверный браузер (Playwright).
# Мультиарх: работает и на ARM64 (Oracle Ampere), и на x86_64.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers \
    # DB и профиль браузера — в /data (том), чтобы переживали перезапуски.
    DATABASE_URL=sqlite+aiosqlite:////data/nexus.db \
    NEXUS_BROWSER_PROFILE=/data/browser_session \
    NEXUS_SERVER_BROWSER=1 \
    NEXUS_BROWSER_HEADLESS=1 \
    PORT=8000

WORKDIR /app

# ffmpeg нужен для сборки видео/субтитров; остальные системные либы ставит playwright.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

# Сначала зависимости — лучше кэшируется.
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install -r /app/backend/requirements.txt \
    && python -m playwright install --with-deps chromium

# Затем код (backend + собранный frontend/dist).
COPY . /app

RUN mkdir -p /data
VOLUME ["/data"]

WORKDIR /app/backend
EXPOSE 8000

# shell-форма, чтобы подставился $PORT.
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
