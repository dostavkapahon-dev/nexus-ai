# ARCHITECTURE — NEXUS AI

## Схема (как есть на 2026-08-11)

```
USER
 ├── Telegram (long-polling)         core/telegram_bot.py
 └── Web (React/Vite)                frontend/  — 7 разделов:
      Главная · Командный центр · Подключения · Агенты · Контент ·
      Настройки · API/Credentials
              ↓
   command_center.run_command        core/command_center.py   ← единая точка входа
              ↓ intent.route()       core/intent.py
   marketing_director.run_director   core/marketing_director.py  ← оркестратор («Cloud Code»)
              ↓ tools
   ┌──────────┬──────────┬───────────┬──────────┬────────┐
 analyze   delegate   run_browser  make_video  publish  done
   │          │           │            │          │
   │     dispatch.delegate│            │          │
   │          ↓           │            │          │
   │     ai_router.call ──┘            │          │
   │     core/ai_router.py             │          │
   │     6 free + 5 платных провайдеров│          │
   │                                   │          │
 social_intel / instagram_reader /  media_generator  orchestrator._publish_one
 youtube_reader / browser_reader    core/media_*     core/orchestrator.py
              ↓                                          ↓
        НОРМАЛИЗОВАННЫЕ ДАННЫЕ                  publishers/*.py (нативные API)
                                                         ↓ фолбэк
                                            server_browser / desktop_agent
              ↓
   SQLite (эфемерная!) + Connection KV + data/*.json
   доступы: core/credentials.py → core/secrets.py (шифрование NEXUS_SECRET_KEY)
            → os.environ на старте, весь код читает их через os.getenv
```

## Второй конвейер (архитектурная развилка ⚠️)

Независимо от дирижёра существует `core/orchestrator.py::run_pipeline`:

```
NicheAnalyst → ViralHunter → Strategist → Copywriter → Reviewer
             → VoiceAdapter → VisualCreator → PlatformAdapter
```

Он делает похожую работу другими средствами и не связан с `marketing_director`.
Две «головы» — источник рассинхронизации; требует решения: объединить или явно разделить роли.

## Слои

| Слой | Модули | Назначение |
|---|---|---|
| Вход | `telegram_bot`, `api/routes_control` | приём команд от человека |
| Маршрутизация | `command_center`, `intent` | свободный текст → команда |
| Оркестрация | `marketing_director`, `dispatch` | декомпозиция и делегирование |
| AI | `ai_router` | единый вызов моделей, фолбэк, стоимость |
| Агенты | `agents/*` | специализированные роли |
| Пайплайн | `content_factory`, `creative_director`, `self_critique` | анализ → бриф → генерация → ревью |
| Медиа | `media_generator`, `higgsfield`, `heygen`, `montage`, `video_*` | изображения, видео, монтаж |
| Чтение соцсетей | `social_intel`, `instagram_reader`, `youtube_reader`, `browser_reader`, `viral_research` | сбор метрик |
| Публикация | `orchestrator._publish_one`, `publishers/*` | постинг |
| Браузер | `server_browser`, `browser_agent`, `desktop_agent.py` | работа без API |
| Хранение | `database/*`, `Connection` KV, `data/*.json` | состояние |
| Расписание | `scheduler` (APScheduler) | 6 cron-джобов |

## Режимы работы без API

| Переменная | Значения | Смысл |
|---|---|---|
| `NEXUS_PUBLISH_MODE` | `auto` / `browser` / `api` | как публиковать |
| `NEXUS_ANALYZE_MODE` | `auto` / `browser` / `api` | как анализировать |
| `NEXUS_SERVER_BROWSER` | `1` / `0` | включён ли серверный браузер |
| `NEXUS_BROWSER_CDP` | `wss://…` | удалённый облачный браузер (разгрузка Render) |

`auto` = сначала официальные API/сервисы, при неудаче — браузер.

## Известные архитектурные долги
1. Эфемерное хранилище (см. `PROJECT_STATUS.md`).
2. Две конкурирующие «головы» оркестрации.
3. Нет базового класса `SocialConnector` — коннекторы это свободные функции.
4. Нет системы задач: фоновые работы через `BackgroundTasks`/`asyncio.create_task` без ID.
5. Нет миграций (alembic) ⇒ схема расширяется через KV `Connection`.
