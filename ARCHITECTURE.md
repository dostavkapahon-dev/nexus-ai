# ARCHITECTURE — NEXUS AI / Pakhon Studio

Обновлено: 2026-09-03

## Главная цепочка

```
Telegram (основной интерфейс)
   ↓  свободный текст или команда
Cloud Opus — core/marketing_director.py::run_director
   ↓  решает, каких агентов и какие инструменты включить
существующие AI-агенты  (backend/agents/*)
   ↓  когда нужен визуал
HIXIIT — core/hixiit.py
   ↓  сам выбирает тип генерации и модель из доступных в аккаунте
генерация (изображение / видео)
   ↓
результат возвращается в Cloud Opus (поле `media` в результате)
   ↓
Telegram: sendPhoto / sendVideo + inline-кнопки
```

**Сайт не обязателен.** Telegram-бот запускается в `main.py` (lifespan → `start_polling`)
и работает, даже если фронтенд никто не открыл. Фронтенд — дополнительный интерфейс к тем же
функциям через HTTP API.

## Слои

| Слой | Файлы | Роль |
|---|---|---|
| Интерфейс | `core/telegram_bot.py` | Приём задач, отправка результата, кнопки |
| Оркестратор | `core/marketing_director.py` | Cloud Opus: декомпозиция задачи, вызов инструментов |
| Пайплайн | `core/orchestrator.py` | Ниша → анализ → план → генерация → публикация |
| Фабрика | `core/content_factory.py` | Сквозной цикл одного ролика |
| Агенты | `backend/agents/*` | Специализированные исполнители (см. AGENTS.md) |
| Генеративный слой | `core/hixiit.py` | HIXIIT: выбор модели и генерация медиа |
| Роутинг моделей | `core/ai_router.py` | Какой LLM на какого агента, фолбэки, стоимость |
| Память | `core/memory.py`, `database/*` | Сохранённый контекст проекта |
| Публикация | `backend/publishers/*` | Telegram / Instagram / VK / YouTube / TikTok |
| Расписание | `core/scheduler.py` | APScheduler, TZ Asia/Almaty |

## HIXIIT — пути доступа

`core/hixiit.py::generate()` пробует по порядку и объясняет каждый отказ:

1. **MCP** — `HIGGSFIELD_MCP_URL` + `HIGGSFIELD_MCP_TOKEN`. Основной рабочий путь.
   Модель подбирается вызовом `models_explore(action="recommend", …)` по реальному
   каталогу аккаунта, а не по захардкоженному списку. Модели, требующие входа,
   которого у нас нет (например YouTube-ссылку), отфильтровываются.
2. **REST** — `HIGGSFIELD_API_KEY` (`core/higgsfield.py`), только видео.
3. **Браузер-агент** — `desktop_agent.py` на включённом ПК, только видео.
4. **Pollinations** — бесплатная картинка, чтобы визуал был хоть какой-то.

Диагностика: команда `/hixiit` в Telegram.

## Память

`database/db.py::_database_url()`:
- `DATABASE_URL` → Postgres (схемы `postgres://` и `postgresql://` приводятся к `asyncpg`).
  **Это единственный способ не терять память между рестартами на Render.**
- иначе SQLite по пути `NEXUS_DB_PATH` (по умолчанию `./nexus.db`).

⚠️ Файловая система Render эфемерна, а в `render.yaml` диск не подключён. Без `DATABASE_URL`
вся память — ниши, контент-план, очередь, сохранённые ключи из таблицы `connections` —
стирается при каждом деплое. См. TODO.md, пункт 1.

`core/memory.py::build_context()` собирает сохранённое (профиль, ниши, план, очередь,
последний контент, ошибки, голос бренда) и подаёт в Cloud Opus, чтобы он не анализировал
всё заново.

## Точки входа

- `backend/main.py` — FastAPI: API + WebSocket + статика фронта + запуск бота и планировщика.
- `desktop_agent.py` — агент на ПК пользователя (браузерные действия), по WebSocket `/ws/desktop`.
- `start.sh` (`back` / `front` / `all`), деплой — `render.yaml`.
