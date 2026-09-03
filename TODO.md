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
- [x] `agents/funnel_agent.py` — подключён к обработке комментариев (BLOCK 07)
- [ ] `core/social_intel.py` — убрать 4 устаревших упоминания Ayrshare в комментариях

## BLOCK 01 — TASK SYSTEM ✅ ВЫПОЛНЕН
- [x] Модель `Task` + `core/task_manager.py` (создание, retry, шаги, расход, отмена)
- [x] Обёрнуты все 12 точек запуска фоновой работы + 6 cron-джобов
- [x] `recover_stuck()` в lifespan — зависшие RUNNING → FAILED
- [x] `/tasks` и `/task <id>` в Telegram + страница «Задачи» в дашборде
- [x] API `/api/tasks`, `/api/tasks/stats`, `/api/tasks/{id}`, `/cancel`
- [x] 8 тестов (`tests/test_tasks.py`), всего 145 passed
- [ ] Развилка двух «голов»: решено **разделить роли явно** — зафиксировать в докстрингах

## BLOCK 02 — COST CONTROL ✅ ВЫПОЛНЕН
- [x] Запись расхода внутри `ai_router.call` — под учётом каждый вызов, с привязкой
      к задаче/агенту/нише через contextvar
- [x] `UserProfile.budget_usd_day` (миграция) + алерты в Telegram на 80 % и 100 %
- [x] `pick_model()` — `ai_mode` реально выбирает ECONOMY/PREMIUM (кастомная модель приоритетнее)
- [x] Точные токены Gemini через `usage_metadata` (была эвристика)
- [x] `/api/cost`, `/cost` в Telegram, страница «Расходы» в дашборде
- [x] 8 тестов (`tests/test_cost.py`), всего 153 passed
- [ ] Жёсткий стоп платных моделей при превышении — осознанно отложено

## BLOCK 03 — SOCIAL CONNECTORS ✅ ВЫПОЛНЕН
- [x] Базовый класс `SocialConnector` + `RateLimiter` (`connectors/base.py`)
- [x] 6 коннекторов: Instagram, Threads (+чтение, которого не было), Telegram, TikTok, YouTube, VK
- [x] OAuth Meta: `/api/social/oauth/start` + публичный `/callback`, авто-поиск IG Business аккаунта
- [x] Long-lived токен (60 дней) + джоб `tokens` в 08:00 продлевает всё, чему осталось <14 дней
- [x] Rate-limit по площадкам (Meta 20/мин, TikTok 10/мин)
- [x] `health()` с датой истечения, правами и `can_publish`; страница «Площадки» в дашборде
- [x] `_publish_one` переведён на коннекторы вместо лестницы if-ов
- [x] 15 тестов (`tests/test_connectors.py`), всего 168 passed
- [x] Webhooks: приём с проверкой подписи и токена (`core/webhooks.py`), 23 теста
- [ ] Видео-постинг TikTok

## BLOCK 04 — SOCIAL ANALYTICS ✅ ВЫПОЛНЕН
- [x] `Publication` расширена метриками (просмотры, лайки, комменты, сохранения, репосты,
      охват, ER, ссылка) + тема/хук/формат — чтобы связать результат с приёмом (миграция)
- [x] `core/post_analytics.py`: collect_metrics / performance / top_posts / learn_from_results
- [x] Джоб `metrics` в 23:00 — сбор метрик + обучение + сводка в Telegram
- [x] Реальные результаты подмешиваются в `strategy_advisor` — стратегия строится на фактах
- [x] API `/api/performance/*` + страница «Результаты» в дашборде
- [x] 10 тестов (`tests/test_post_analytics.py`), всего 178 passed

## BLOCK 09 — CONTENT PIPELINE ✅ ВЫПОЛНЕН
- [x] Шаги фабрики пишутся в журнал задачи (`_flush_steps`, 4 контрольные точки)
- [x] Точка согласования — явный шаг `approval_requested`
- [x] Задача, ждущая аппрува человека, получает статус WAITING, а не COMPLETED
- [x] `POST /api/automation/factory` создаёт Task и возвращает `task_id`
- [x] 4 теста (`tests/test_pipeline.py`), всего 228 passed

## BLOCK 10 — PUBLISHING ENGINE ✅ ВЫПОЛНЕН
- [x] `core/publish_queue.py` — очередь публикаций в БД (переживает рестарт)
- [x] Повторы с растущей паузой 2/8/30/120 мин, максимум 5 попыток
- [x] Отказ по существу (нет прав/токена) → `blocked` сразу, без бессмысленных повторов
- [x] Отложенное расписание: пост на 19:00 не уходит в 10:00
- [x] Джоб очереди каждые 10 минут + ручной повтор/отмена
- [x] `Publication` расширена полями очереди (миграция `64e59c73f0d2`)
- [x] `/api/publish/*`, `/queue` в Telegram, страница «Публикации» в дашборде
- [x] 8 тестов (`tests/test_publish_queue.py`), всего 236 passed
- [ ] Живая проверка с реальными токенами площадок — ключей нет, соцсети закрыты прокси среды

## BLOCK 11 — TELEGRAM CONTROL CENTER ✅ ВЫПОЛНЕН
- [x] `core/notify.py` — отчёт о завершении задачи приходит сам
- [x] Громко: провал, ожидание согласования, отмена. Молча: успех фонового джоба
- [x] Ручной запуск из Telegram не дублируется вторым отчётом
- [x] `/errors [часы]` — провалы задач и ошибки моделей в одном списке
- [x] `GET /api/tasks/errors` (объявлен выше `/{task_id}`, иначе перехватывался)
- [x] 8 тестов (`tests/test_notify.py`), всего 244 passed

## BLOCK 12 — HEALTH DASHBOARD ✅ ВЫПОЛНЕН
- [x] API-агрегат по агентам (online/degraded/silent, last run, success rate, cost) из `AgentLog`
- [x] Молчащий агент остаётся в списке — иначе сломанный джоб просто исчезает
- [x] Статус соцсетей через `connectors.health_all()`
- [x] Статус планировщика и всех его джобов со временем следующего запуска
- [x] Глобальные ошибки (задачи + вызовы моделей), не по одной нише
- [x] Расходы за день / неделю / месяц + бюджет
- [x] `/api/system/health`, `/agents`, `/scheduler`; страница «Здоровье» в дашборде
- [x] 9 тестов (`tests/test_health.py`), всего 253 passed

## РЕЖИМ БЕЗ ВНЕШНИХ ИИ ✅ ВЫПОЛНЕНО
- [x] `ai_available()` / `available_providers()` — система знает, есть ли чем работать
- [x] Бот отвечает списком рабочих команд вместо «All AI providers failed»
- [x] Не заводится задача, которая гарантированно упадёт
- [x] Разделены «нет ключа» и «провайдеры отказали»
- [x] Режим виден в `/diag` и на странице «Здоровье»
- [x] 8 тестов (`tests/test_no_ai_mode.py`), всего 261 passed

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

## HIXIIT через MCP — нужно действие владельца

Код готов, но процессу на Render нужен собственный доступ к MCP: сессия Claude
Code, где Higgsfield подключён, — это не то же самое, что сервер.

1. Render → сервис `nexus-ai` → Environment.
2. Добавить `HIGGSFIELD_MCP_URL` и `HIGGSFIELD_MCP_TOKEN`.
3. После деплоя проверить командой `/hixiit` в Telegram — она покажет активный
   путь и остаток кредитов.

До этого HIXIIT работает по запасным путям и честно сообщает, чего не хватает.
После подключения можно вернуть `producer=server`: отдавать видео внешнему
исполнителю (`producer=claude`) станет необязательно.

## Мелочи, замеченные попутно

- `core/ai_router.py` использует `google.generativeai`, а он объявлен устаревшим
  (предупреждение при каждом старте). Переход на `google.genai` — отдельная задача,
  трогать рабочий роутер заодно с другими правками не стоит.
