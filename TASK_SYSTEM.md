# TASK SYSTEM — NEXUS AI

## Текущее состояние: ⚪ NOT IMPLEMENTED

Системы задач **нет**. Нет модели `Task`, нет `task_id`, нет статусов
`CREATED / RUNNING / WAITING / COMPLETED / FAILED / CANCELLED`, нет retry и истории запусков.

## Как сейчас выполняются фоновые работы

| Механизм | Где | Проблема |
|---|---|---|
| `BackgroundTasks` | `api/routes_queue.py:66`, `api/routes_automation.py:87` | in-process, при рестарте задача теряется молча, статус зависает |
| `asyncio.create_task` | `core/telegram_bot.py:267,549,565,590,652,684,695` | без ID, упавшая задача исчезает бесследно |
| APScheduler | `core/scheduler.py:179` | расписание в памяти, пропущенные запуски не догоняются |

Единственные внешние `task_id` — задачи Runway (`core/media_generator.py:124-205`),
нигде не персистятся.

## Что ошибочно принимают за очередь задач
`api/routes_queue.py` + страница `Queue.jsx` — это **CRUD над `ContentPlan`** со строковым
статусом (`pending` → `generated` → `published`). Это очередь **контента**, а не задач агентов.
Запуски фабрики, автопилота, дирижёра, браузерных задач в ней не отражаются.

## Расписание (`core/scheduler.py`, TZ Asia/Almaty)

| id | Время | Функция |
|---|---|---|
| `trends` | 09:00 | `run_daily_trends` — TrendAnalyst + отчёт в Telegram |
| `factory` | 09:30 | `run_daily_factory` — `run_factory(dry_run = not AUTO_PUBLISH)` |
| `generate` | 10:00 | `run_daily_generate` — до 10 планов `pending` |
| `publish` | 19:00 | `run_daily_publish` — до 10 планов `generated` |
| `report` | 22:00 | `run_daily_report` |
| `weekly` | вс 20:00 | `run_weekly_analytics` |

⚠️ Докстринг в начале файла устарел (указаны UTC-времена, не совпадающие с кодом).
⚠️ Ни один джоб не наблюдаем из UI.

## Целевая модель (предложение, не реализовано)

```
Task
 ├── id            TASK-2026-000001
 ├── source        telegram | dashboard | scheduler | agent
 ├── goal          текст задачи
 ├── status        CREATED | RUNNING | WAITING | COMPLETED | FAILED | CANCELLED
 ├── agents[]      кто участвовал
 ├── models[]      какие модели вызывались
 ├── steps[]       журнал шагов с результатами
 ├── tokens, cost  суммарный расход
 ├── error         текст ошибки
 ├── started_at, finished_at, duration_sec
 └── parent_id     для подзадач
```

Требования: обёртка запуска (любая фоновая работа получает Task), восстановление
«зависших» RUNNING при старте, отображение в дашборде и `/tasks` в Telegram,
retry с ограничением попыток.

**Блокер:** реализация требует миграций и персистентной БД — см. `PROJECT_STATUS.md`.
