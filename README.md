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

## AI-провайдеры и распределение задач

**Claude — главный мозг.** Он держит цель, декомпозирует её и раздаёт текстовые
подзадачи дешёвым исполнителям через инструмент `delegate`, а сам пишет только
план, критику и отчёт. В системный промпт попадают лишь исполнители, у которых
есть ключ, поэтому шаг не тратится на заведомо недоступного провайдера.

| Исполнитель | Модель | $/1k токенов | Под что |
|-------------|--------|--------------|---------|
| `nvidia`     | подбирается из каталога NVIDIA | **0 (кредиты)** | Llama / Nemotron / Qwen / DeepSeek-R1 на GPU NVIDIA |
| `gemini`     | gemini-2.0-flash | 0.0001 | черновики, большие объёмы, зрение |
| `deepseek`   | deepseek-chat    | 0.00014 | рассуждения, структура, редактура |
| `perplexity` | sonar-pro        | 0.003  | свежие факты и тренды со ссылками |
| `claude`     | claude-sonnet-4-6| 0.003  | сложный анализ, когда остальные не справились |
| `openai`     | gpt-4o           | 0.005  | чистовой копирайтинг, живой тон |

```bash
curl -s https://<server>/api/automation/executors -H "Authorization: Bearer <TOKEN>"
# кто дирижёр, кто дефолтный исполнитель, у кого есть ключ

curl -X POST https://<server>/api/automation/delegate -H "Authorization: Bearer <TOKEN>" \
  -d '{"executor": "nvidia", "task": "3 хука для рилса про доставку"}'
```

### Бесплатные модели через NVIDIA

[build.nvidia.com](https://build.nvidia.com/settings/api-keys) отдаёт 100+ открытых
моделей на своих GPU по OpenAI-совместимому API. Регистрация — только email,
без карты: 1000 кредитов сразу, лимит 40 запросов/мин, ключ `nvapi-` живёт
6 месяцев. Вставьте его в **Подключения → NVIDIA NIM** (или `NVIDIA_API_KEY`).

Конкретная модель не зашита: каталог NVIDIA меняется, поэтому псевдоним
`nvidia-free` на первом вызове спрашивает `/v1/models` и берёт лучшую доступную
(Llama 3.3 70B → Nemotron → Qwen → DeepSeek-R1 → Gemma). Стоимость пишется
нулевой — расходуются кредиты NVIDIA, а не деньги, — поэтому в цепочке фолбэка
NVIDIA стоит первой, раньше всех платных.

Все ключи — на странице **Подключения**.

## Как запустить проект

### Быстрый старт (одна команда)
```bash
./start.sh            # backend :8000 + frontend :5173
./start.sh back       # только backend
./start.sh front      # только frontend
```
Скрипт сам создаст venv, поставит зависимости и `.env` из примера.
Дальше: открой http://localhost:5173 → **Ключи API** → вставь ключи → **Дирижёр**.

### Вручную
```bash
# 1. Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env        # заполни ключи (или вводи их в UI → Ключи API)
uvicorn main:app --reload --port 8000

# 2. Frontend (в другом терминале)
cd frontend
npm install
npm run dev                    # http://localhost:5173

# 3. (опц.) Браузерный агент на твоём ПК
pip install websockets playwright && playwright install chromium
python desktop_agent.py --server http://localhost:8000 --token <NEXUS_TOKEN>
```

### Деплой на Render.com
1. Fork репозитория → New Web Service → Connect repo
2. Render найдёт `render.yaml` автоматически
3. В **Environment** добавь ключи (или вводи их в UI → Ключи API после старта)

## Настройки

- **Ключи API** (страница Подключения / `/connections`) — все интеграции: AI,
  публикации (Telegram/Instagram/VK/YouTube), видео (HeyGen/HiggsField/Runway),
  токен браузерного агента. Хранятся в БД, в браузер возвращается только маска.
- **Профиль** — режим AI (`economy`/`premium`), активная нейросеть, Google Drive.
- **Агенты** (`/prompts`) — редактирование системных промптов и моделей агентов.

## Стек
- **Backend**: Python 3.11 + FastAPI + SQLite + APScheduler
- **Frontend**: React 18 + Vite + TailwindCSS
- **AI**: Claude (анализ/директор/зрение) + GPT-4o (копирайтер) + Gemini 2.0 +
  Perplexity + DeepSeek
- **Видео**: HeyGen (аватары) · HiggsField (клипы) · Runway · ElevenLabs (озвучка)
- **Автоматизация**: браузерный агент (Playwright) + Marketing Director
- **Hosting**: Render.com (free tier)
