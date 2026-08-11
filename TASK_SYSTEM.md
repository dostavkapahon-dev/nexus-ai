# TASK SYSTEM — NEXUS AI

## Статус: 🟢 WORKING (BLOCK 01, реализовано)

Каждая фоновая работа получает задачу: идентификатор, статус, журнал шагов, расход
и текст ошибки. Упавшая задача больше не исчезает бесследно.

## Модель `Task` (`database/models.py`)

| Поле | Смысл |
|---|---|
| `id` | `TASK-2026-000001` — человекочитаемый, сквозная нумерация в году |
| `source` | telegram · dashboard · scheduler · api · agent |
| `kind` | pipeline · factory · publish · generate · director · trends · report · analytics |
| `goal` | что просили, словами |
| `status` | CREATED · RUNNING · WAITING · COMPLETED · FAILED · CANCELLED |
| `ref_id` | niche_id / plan_id |
| `steps` | журнал шагов `[{ts, agent, action, ok, error}]`, последние 100 |
| `agents`, `models` | кто участвовал и какие модели вызывались |
| `tokens`, `cost_usd` | накопленный расход |
| `attempts`, `error`, `result` | попытки, текст ошибки, краткий итог |
| `created_at`, `started_at`, `finished_at`, `duration_sec` | тайминги |

Индексы по `status` и `created_at`.

## API (`core/task_manager.py`)

| Функция | Назначение |
|---|---|
| `create(kind, goal, source, ref_id)` | регистрация задачи (CREATED) |
| `run(task_id, coro_factory, max_attempts)` | выполнение с замером времени и retry (backoff `2**n`) |
| `spawn(kind, goal, coro_factory, ...)` | создать + запустить в фоне, вернуть id сразу |
| `add_step(task_id, action, ok, agent, error)` | журнал шагов |
| `add_cost(task_id, model, tokens, cost)` | накопление расхода (основа BLOCK 02) |
| `recover_stuck()` | зависшие RUNNING → FAILED при старте сервера |
| `list_tasks(status, kind, limit)`, `get(id)`, `cancel(id)` | чтение и отмена |

`coro_factory` — функция без аргументов, возвращающая корутину: нужна именно фабрика,
чтобы повторная попытка создавала новую корутину.

## Что теперь под учётом

| Точка запуска | kind |
|---|---|
| `api/routes_niche.py` — создание ниши, регенерация плана | `pipeline` |
| `api/routes_queue.py` — генерация контента | `generate` |
| `api/routes_automation.py` — публикация плана | `publish` (2 попытки) |
| `core/telegram_bot.py` — /factory, /reel, /makereel | `factory` |
| `core/telegram_bot.py` — /analyze, /create, /generate | `pipeline`, `generate` |
| `core/telegram_bot.py` — /trend | `trends` |
| `core/command_center.py` — любая команда дирижёру | `director` |
| `core/scheduler.py` — все 6 cron-джобов | по типу джоба |

Инфраструктурные `asyncio.create_task` (polling Telegram, обработчики сообщений)
намеренно НЕ оборачиваются — это не задачи.

## Поверхность управления

- **HTTP:** `GET /api/tasks` (фильтры `status`, `kind`, `limit`), `GET /api/tasks/stats`,
  `GET /api/tasks/{id}`, `POST /api/tasks/{id}/cancel`.
- **Telegram:** `/tasks` — последние 10 со статусами; `/task <id>` — детали, шаги, ошибка.
- **Dashboard:** страница «Задачи» (`/tasks`) — счётчики, фильтры, раскрытие шагов и ошибок,
  отмена активной задачи, автообновление раз в 5 с.

## WAITING — работа упёрлась в человека
Если работа вернула словарь с `awaiting_approval: true`, `run()` ставит **WAITING**,
а не COMPLETED. Так сделан конвейер фабрики: сгенерированный ролик уходит в Telegram
на согласование, и до ответа человека задача честно висит в ожидании. Помечать её
«завершена» — значит утверждать, что контент опубликован, хотя он не опубликован.

Шаги конвейера фабрики попадают в `steps` задачи через `content_factory._flush_steps()`:
журналирование идёт пачками в контрольных точках, поэтому по упавшей фабрике видно,
на каком именно шаге она сломалась, даже если ответ до вызывающего не дошёл.

## Восстановление после рестарта
`recover_stuck()` вызывается в `lifespan` (`main.py`): задачи, висящие в RUNNING дольше
`STUCK_AFTER_MIN` (30 мин), помечаются FAILED с пояснением «потеряна при перезапуске» —
чтобы статус не врал о состоянии системы.

## Тесты (`tests/test_tasks.py`, 8 шт.)
Успешное завершение и запись результата · падение сохраняет FAILED и текст ошибки ·
retry со второй попытки · `recover_stuck` · накопление шагов/расхода/агентов ·
отмена только активных · API-список с фильтрами и `stats` · требование авторизации.

## Осталось (следующие блоки)
- Привязка расхода AI к задаче на уровне `ai_router` — BLOCK 02.
- Retry публикаций на уровне площадок — BLOCK 10.
