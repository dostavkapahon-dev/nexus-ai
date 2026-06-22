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

## Браузерный агент (автономный)

Агент, который **видит окно браузера** на вашем ПК и сам выполняет маркетинговые
и бизнес-задачи словами: «обнови объявление на OLX», «собери цены конкурентов»,
«настрой буст поста в Instagram».

Архитектура:
- **Руки** — `desktop_agent.py` запускается на вашем ПК (реальный Chromium,
  ваши залогиненные сессии).
- **Мозг** — `backend/core/browser_agent.py`: цикл *скриншот → Claude с
  компьютерным зрением → действие* (Anthropic vision + tool use).

Запуск:
```bash
# 1. На вашем ПК — поднять "руки"
pip install websockets playwright && playwright install chromium
python desktop_agent.py --server https://<ваш-сервер> --token <TOKEN>

# 2. Запустить задачу (с сервера/дашборда)
curl -X POST https://<ваш-сервер>/api/desktop/agent/run \
  -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" \
  -d '{"task": "Открой OLX и обнови цену в моём объявлении на 5000", "start_url": "https://www.olx.ua", "max_steps": 25}'
```
Если агенту нужен ввод (пароль, 2FA, оплата) — он остановится со `status:
needs_input` и вопросом. Соблюдайте правила площадок (Meta не любит автоматизацию
личного аккаунта — для рекламы предпочтительнее Marketing API).

## Marketing Director (запуск «через Claude отсюда»)

Главный AI-дирижёр на Claude: ставите бизнес-цель словами — он сам декомпозирует
её и координирует исполнителей (браузерный агент, генерация видео, публикации).

```bash
curl -X POST https://<server>/api/automation/director \
  -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" \
  -d '{"goal": "Запусти на этой неделе 3 Reels по нашей нише и опубликуй в Instagram и VK"}'
```

## Публикации и адаптация

Контент адаптируется под каждую площадку (`PlatformAdapter`) и публикуется
во все каналы ниши одним вызовом — официальный API там, где есть токен, иначе
fallback через браузерного агента:

| Платформа | Способ |
|-----------|--------|
| Telegram  | Bot API |
| Instagram | Graph API → браузер-fallback |
| ВКонтакте | VK API → браузер-fallback |
| YouTube   | браузерный агент (Studio) + поиск трендов через Data API |
| TikTok    | браузерный агент |

```bash
curl -X POST https://<server>/api/automation/publish/<plan_id>   # во все площадки ниши
```

## Генерация видео (Reels / Shorts / TikTok)

Единый эндпоинт с выбором провайдера: **HeyGen** (говорящий аватар),
**HiggsField** (кинематографичный клип), **Runway** (image-to-video).

```bash
curl -X POST https://<server>/api/automation/video \
  -d '{"prompt": "динамичный ролик про доставку еды, неон", "script": "Закажи за 30 минут!", "provider": "auto"}'
```

## AI-провайдеры

Claude (анализ/директор/зрение), GPT-4o (копирайтер), **Gemini 2.0 Flash**
(резерв/эконом), Perplexity (тренды), DeepSeek (эконом). Все ключи — на странице
**Подключения**.

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
