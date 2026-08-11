# PROJECT STATUS — NEXUS AI

> Аудит от 2026-08-11. Статусы получены **анализом кода**, без живых прогонов с реальными
> токенами (ключей нет, соцсети закрыты egress-прокси среды аудита).
> Всё, что требует живой проверки, помечено ⚠️.

Легенда: 🟢 WORKING · 🟡 PARTIAL · 🔴 BROKEN · ⚪ NOT IMPLEMENTED · 🔵 BLOCKED BY API

## Корневая причина нестабильности 🟡 (исправлено в коде, ждёт подключения БД)

**BLOCK 01:** код переведён на постоянную БД — `DATABASE_URL` нормализуется под asyncpg,
добавлены alembic-миграции (`alembic upgrade head` в `startCommand`) и `DATABASE_URL`
в `render.yaml`. **Осталось действие пользователя:** создать бесплатный Postgres в Supabase
и вставить строку подключения в Render → Environment. До этого момента поведение прежнее ↓

`render.yaml` не имеет `disk`/volume, `DATABASE_URL` не задан.
`database/db.py:5` → `sqlite+aiosqlite:///./nexus.db` (относительный путь, `rootDir: backend`).
Render free — эфемерная ФС + засыпание при простое ⇒ **при каждом рестарте теряется вся БД**:
ниши, контент-планы, сгенерированный контент, публикации, `AgentLog` (расходы), кастомные
промпты и все KV-ключи `Connection` (состояние автопилота, рецепт вируса, очередь модерации,
лента событий, выбранная стратегия). Дополнительно: `skills.json` и `brand_voice.txt`
откатываются к версии из git, `hook_history.json` теряется (он в `.gitignore`).

API-ключи выживают только потому, что продублированы в Render Environment — отсюда фолбэк
`os.getenv` в `api/routes_settings.py:71`.

**Это фикс №1.** Без него любые другие исправления не переживут рестарт.

## Статус 12 блоков

| # | Блок | Статус | Комментарий |
|---|---|---|---|
| 01 | Core / Orchestrator | 🟢 | **BLOCK 01 выполнен:** система задач (id, статусы, retry, шаги, восстановление после рестарта), alembic, Postgres-совместимость |
| 02 | AI Provider Layer | 🟢 | **BLOCK 02 выполнен:** единая касса расходов (все вызовы), бюджет с алертами, реальный `ai_mode`, точные токены Gemini |
| 03 | Social Connectors | 🟢 | **BLOCK 03 выполнен:** `SocialConnector` + 6 коннекторов, OAuth Instagram, продление токенов, rate-limit, health |
| 04 | Social Analytics | 🟢 | **BLOCK 04 выполнен:** метрики публикаций в БД, джоб сбора в 23:00, обучение памяти агента на реальных результатах |
| 05 | Market / Competitor Research | 🟢 | **BLOCK 05 выполнен:** история исследований в БД, отслеживание конкурентов с динамикой, сводка рынка для агентов |
| 06 | Content Strategy | 🟢 | **BLOCK 06 выполнен:** версии стратегий в БД, привязка публикаций, сравнение по фактическому ER |
| 07 | Content Generation | 🟢 | Copywriter / adapter / creative_director, ротация хуков |
| 08 | Image / Video Generation | 🟢 | **BLOCK 08 выполнен:** генерации в общей кассе, разбивка текст/медиа, причины отказа провайдеров сохраняются |
| 09 | Content Pipeline | 🟢 | **BLOCK 09 выполнен:** шаги фабрики пишутся в журнал задачи, ожидание аппрува = статус WAITING, запуск из дашборда получает Task ID |
| 10 | Publishing Engine | 🟢 | **BLOCK 10 выполнен:** очередь публикаций в БД, повторы с backoff, отложенное расписание, честный BLOCKED вместо вечных попыток |
| 11 | Telegram Control Center | 🟢 | **BLOCK 11 выполнен:** отчёт о завершении задач приходит сам (провал/ожидание аппрува), `/errors`, `/queue`; ~30 команд, inline-кнопки, модерация |
| 12 | Web Dashboard | 🟢 | **BLOCK 12 выполнен:** страница «Здоровье» — агенты (online/degraded/silent), площадки, планировщик, задачи, расходы, ошибки в одном агрегате |

## Критические поломки

| Приоритет | Проблема | Где |
|---|---|---|
| 🟡 | БД эфемерна, пока не задан `DATABASE_URL` (код готов, нужен Supabase) | `render.yaml` |
| ✅ | ~~`gemini-1.5-flash`~~ → `gemini-2.0-flash` | `core/prompt_store.py` |
| ✅ | ~~`FunnelAgent` — мёртвый код~~ → подключён к комментариям Instagram | `core/engagement.py` |
| ✅ | `publish_youtube_short` — честный `blocked_by_api` + причина | `publishers/youtube_pub.py` |
| ✅ | ~~Расходы «мимо кассы»~~ → запись в `ai_router`, под учётом каждый вызов | `core/cost_tracker.py` |
| ✅ | ~~`ai_mode` — фикция~~ → `pick_model` реально выбирает economy/premium | `core/ai_router.py` |
| ✅ | ~~`log()` коммитил чужие изменения~~ → отдельная сессия | `agents/base_agent.py` |
| 🟡 | Секреты plaintext в БД и в `os.environ` всего процесса | `api/routes_settings.py:80-94` |
| 🟡 | Гонки при read-modify-write KV `Connection` без блокировки | `core/command_center.py`, `core/moderation.py` |
| ✅ | ~~Нет системы задач~~ → реализована, см. `TASK_SYSTEM.md` | `core/task_manager.py` |
| ✅ | ~~Нет OAuth и long-lived токенов~~ → OAuth Meta + авто-продление в 08:00 | `connectors/`, `api/routes_social.py` |

## Что работает надёжно
- AI Provider Layer с фолбэком между 11 провайдерами (BLOCK 02).
- Telegram Control Center (BLOCK 11) — основной рабочий интерфейс.
- Конвейер генерации контента (BLOCK 09): сквозной отчёт + журнал шагов в задаче.
- Единый пульт: дашборд и Telegram на одном мозге (`core/command_center.py`).
- Очередь публикаций с повторами (BLOCK 10) и отчёты о задачах (BLOCK 11).
- Страница «Здоровье» (BLOCK 12) — состояние системы одним взглядом.

## Порядок исправления
См. `TODO.md`.
