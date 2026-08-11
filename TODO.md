# TODO — порядок стабилизации NEXUS AI

Правило: **один блок за раз** — изменить → протестировать → обновить документацию → отчёт.
Не переходить к следующему, пока текущий не имеет понятного статуса.

## BLOCK 00 — ПЕРСИСТЕНТНОСТЬ ✅ (код готов)
- [x] Postgres-совместимость: `normalize_db_url` (postgres:// → postgresql+asyncpg://), `pool_pre_ping`
- [x] alembic + baseline-миграция всех 10 таблиц
- [x] `DATABASE_URL` и `alembic upgrade head` в `render.yaml`
- [ ] **ДЕЙСТВИЕ ПОЛЬЗОВАТЕЛЯ:** создать бесплатный Postgres в Supabase и вставить
      строку подключения в Render → Environment → `DATABASE_URL`
- [ ] Перенести эфемерные `data/*.json` (skills, brand_voice, hook_history) в БД

## Быстрые 🔴-фиксы
- [x] `core/prompt_store.py` — `gemini-1.5-flash` → `gemini-2.0-flash`
- [x] `publishers/youtube_pub.py` — честный `blocked_by_api` с причиной
- [x] `frontend/src/App.jsx` — `Analytics` возвращена в навигацию
- [x] `agents/base_agent.py` — лог в отдельной сессии (не коммитит чужие изменения)
- [ ] `agents/funnel_agent.py` — подключить к обработке комментариев **или** удалить (BLOCK 07)
- [ ] `core/social_intel.py` — убрать 4 устаревших упоминания Ayrshare в комментариях

## BLOCK 01 — TASK SYSTEM ✅ ВЫПОЛНЕН
- [x] Модель `Task` + `core/task_manager.py` (создание, retry, шаги, расход, отмена)
- [x] Обёрнуты все 12 точек запуска фоновой работы + 6 cron-джобов
- [x] `recover_stuck()` в lifespan — зависшие RUNNING → FAILED
- [x] `/tasks` и `/task <id>` в Telegram + страница «Задачи» в дашборде
- [x] API `/api/tasks`, `/api/tasks/stats`, `/api/tasks/{id}`, `/cancel`
- [x] 8 тестов (`tests/test_tasks.py`), всего 145 passed
- [ ] Развилка двух «голов»: решено **разделить роли явно** — зафиксировать в докстрингах

## BLOCK 02 — COST CONTROL
- [ ] Единая обёртка над `ai_router.call` — расход пишется всегда, с `task_id`
- [ ] Бюджет в `UserProfile` + алерт в Telegram (80 %) и стоп (100 %)
- [ ] Сделать `ai_mode` (economy/premium) реально влияющим на выбор модели
- [ ] Точный подсчёт токенов там, где провайдер отдаёт `usage`

## BLOCK 03 — SOCIAL CONNECTORS
- [ ] Базовый класс `SocialConnector` (publish / read_profile / read_posts / health / refresh)
- [ ] `InstagramConnector`, `ThreadsConnector`, `TelegramConnector`, `TikTokConnector`, `YouTubeConnector`
- [ ] OAuth-флоу вместо ручного ввода токенов
- [ ] Long-lived token + авто-продление (Instagram — критично, 60 дней)
- [ ] Rate-limit и backoff
- [ ] `health()` — валидность токена, срок, permissions

## BLOCK 04 — СОХРАНЕНИЕ АНАЛИТИКИ
- [ ] Расширить `Publication`: просмотры, лайки, комментарии, сохранения, ER, ссылка на пост
- [ ] Периодический сбор метрик опубликованного (джоб)
- [ ] Обучение памяти агента на реальных результатах (`skills_store.learn_from`)

## BLOCK 12 — HEALTH DASHBOARD
- [ ] API-агрегат по агентам (ONLINE/last run/success rate/cost) из `AgentLog`
- [ ] Статус соцсетей (токен валиден, срок, permissions)
- [ ] Статус планировщика и его 6 джобов
- [ ] Глобальные логи и ошибки (не по одной нише)
- [ ] Расходы за день / неделю / месяц

## ТЕСТЫ
- [ ] Тесты на `publishers/*` и `orchestrator._publish_one`
- [ ] Тесты на `social_intel` / `instagram_reader` / `youtube_reader` / `browser_reader`
- [ ] Тесты на команды Telegram и `command_center`

## БЕЗОПАСНОСТЬ
- [ ] Шифрование секретов at-rest (сейчас plaintext в БД и в `os.environ`)
- [ ] Убрать ключи из глобального `os.environ` там, где можно
- [ ] Не возвращать фрагменты ключей в текстах ошибок
- [ ] Ротация токенов

## СХЕМА БД
- [ ] ForeignKey + каскады (сейчас осиротевшие `GeneratedContent`/`Publication`)
- [ ] Блокировки при read-modify-write KV `Connection` (гонки scheduler/telegram/dashboard)
- [ ] Ограничение роста `moderation_queue`, `autopilot_state`, `viral_recipe`
