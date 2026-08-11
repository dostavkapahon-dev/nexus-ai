# TODO — порядок стабилизации NEXUS AI

Правило: **один блок за раз** — изменить → протестировать → обновить документацию → отчёт.
Не переходить к следующему, пока текущий не имеет понятного статуса.

## BLOCK 00 — ПЕРСИСТЕНТНОСТЬ 🔴 БЛОКЕР
Без него всё остальное не переживёт рестарт.
- [ ] Render: подключить `disk` (mountPath) **или** перейти на Postgres (`DATABASE_URL`)
- [ ] Вынести `nexus.db` на постоянный путь; убрать относительный `./nexus.db`
- [ ] Добавить alembic + первая миграция от текущей схемы
- [ ] Перенести эфемерные `data/*.json` (skills, brand_voice, hook_history) в БД
- [ ] Тест: рестарт контейнера → данные на месте

## Быстрые 🔴-фиксы (можно параллельно с BLOCK 00)
- [ ] `core/prompt_store.py:50,55` — заменить несуществующую `gemini-1.5-flash`
      на рабочую модель (trend_analyst, funnel_agent)
- [ ] `agents/funnel_agent.py` — подключить к обработке комментариев **или** удалить
- [ ] `publishers/youtube_pub.py` — заглушка должна возвращать честный
      `BLOCKED: требуется YOUTUBE_OAUTH_JSON`, а не выглядеть как ошибка
- [ ] `frontend/src/App.jsx:18-27` — вернуть `Analytics` в навигацию
- [ ] `core/social_intel.py` — убрать 4 устаревших упоминания Ayrshare в комментариях

## BLOCK 01 — TASK SYSTEM
- [ ] Модель `Task` (id `TASK-YYYY-NNNNNN`, статусы, агенты, модели, cost, ошибки, время)
- [ ] Обёртка запуска: любая фоновая работа получает Task
- [ ] Восстановление «зависших» RUNNING при старте
- [ ] `/tasks` в Telegram + страница в дашборде
- [ ] Решить развилку двух «голов»: `orchestrator.run_pipeline` vs `marketing_director`

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
