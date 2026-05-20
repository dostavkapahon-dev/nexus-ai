# NEXUS AI — Автоматизация контента

Мультиагентная система для автоматического создания и публикации контента.

## Агенты
- **NicheAnalyst** — анализирует нишу и аудиторию
- **ViralHunter** — ищет вирусные паттерны
- **Strategist** — создаёт 30-дневный план
- **Copywriter** — пишет посты (GPT-4o)
- **Reviewer** — проверяет качество
- **VoiceAdapter** — адаптирует под стиль автора
- **VisualCreator** — генерирует изображения (Pollinations.ai)
- **PlatformAdapter** — адаптирует под платформы

## Локальный запуск

```bash
# Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env  # заполни ключи
uvicorn main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

## Деплой на Render.com
1. Fork этот репозиторий
2. New Web Service → Connect repo
3. Render автоматически найдёт `render.yaml`
4. Добавь env vars в настройках сервиса

## Стек
- **Backend**: Python 3.11 + FastAPI + SQLite + APScheduler
- **Frontend**: React 18 + Vite + TailwindCSS
- **AI**: Claude (Anthropic) + GPT-4o (OpenAI) + Gemini (Google)
- **Hosting**: Render.com (free tier)
