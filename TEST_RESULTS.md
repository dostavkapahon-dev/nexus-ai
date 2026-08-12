# TEST RESULTS — NEXUS AI

Прогон: `cd backend && python -m pytest -q` → **325 passed** (после вебхуков и прямого подключения Instagram;
на момент аудита от 2026-08-11 было 137).

## Покрытие по блокам

| Тест | Блок | Файл | Тестов | Статус |
|---|---|---|---|---|
| AI Router | 02 | `tests/test_ai_router.py` | 14 | 🟢 PASS |
| Free providers | 02 | `tests/test_free_providers.py` | 26 | 🟢 PASS |
| Dispatch / делегирование | 01 | `tests/test_dispatch.py` | 18 | 🟢 PASS |
| Auth + health | 12 | `tests/test_auth.py` | 14 | 🟢 PASS |
| Ниши (CRUD + pipeline) | 01 | `tests/test_niches.py` | 10 | 🟢 PASS |
| Настройки / ключи | 12 | `tests/test_settings.py` | 9 | 🟢 PASS |
| Отчёт фабрики | 09 | `tests/test_factory_report.py` | 6 | 🟢 PASS |
| Конвейер и журнал шагов | 09 | `tests/test_pipeline.py` | 4 | 🟢 PASS |
| Очередь публикаций и повторы | 10 | `tests/test_publish_queue.py` | 10 | 🟢 PASS |
| Отчёты о задачах и `/errors` | 11 | `tests/test_notify.py` | 8 | 🟢 PASS |
| Здоровье системы | 12 | `tests/test_health.py` | 9 | 🟢 PASS |
| Работа без внешних ИИ | 02 | `tests/test_no_ai_mode.py` | 8 | 🟢 PASS |
| Строка подключения к БД | 01 | `tests/test_db_url.py` | 11 | 🟢 PASS |
| Браузерная сессия без API | 10 | `tests/test_browser_session.py` | 15 | 🟢 PASS |
| Вебхуки Instagram (подпись, токен) | 03 | `tests/test_webhooks.py` | 23 | 🟢 PASS |
| Подключение Instagram по токену | 03 | `tests/test_ig_connect.py` | 12 | 🟢 PASS |

Живая проверка на поднятом сервере (2026-08-11), не только тестами:
- Приложение стартует, `/api/health` отвечает → 🟢 PASS.
- Все защищённые эндпоинты без токена дают 401 → 🟢 PASS.
- Планировщик поднят, 11 джобов зарегистрированы с корректным временем → 🟢 PASS.
- Очередь публикаций: постановка → разбор → статус с причиной → 🟢 PASS.
- **Состояние пережило перезапуск процесса** (запись и текст поста на месте) → 🟢 PASS.
- Режим «только управление» без ИИ отвечает списком команд → 🟢 PASS.
- OAuth Instagram без ключей даёт внятную причину, а не трассировку → 🟢 PASS.
- 🔴 Найден дефект: Telegram без токена уходил в браузерный путь и повторялся
  впустую. Исправлено, закреплено двумя тестами.
- 🔴 Найден блокер деплоя: строка Supabase с `?sslmode=require` уронила бы сервис
  на первом подключении (asyncpg не знает такого аргумента). Исправлено, 11 тестов.
- Цепочка миграций с нуля на пустой БД: все 6 ревизий применяются → 🟢 PASS.
- Собранный фронт с новыми страницами закоммичен в `frontend/dist` → 🟢 PASS.
- Вебхуки вживую: подтверждение подписки отдаёт challenge (200), чужой токен → 403,
  событие без подписи и с подделанной → 403, с настоящей → 200, событие сохранено,
  задача заведена → 🟢 PASS.

Дополнительно проверено вручную в ходе аудита:
- SSRF-guard `server_browser.url_allowed` — metadata/localhost/private блокируются,
  соцсети разрешены → 🟢 PASS.
- Браузерный путь анализа: Chromium стартует, навигация инициируется → 🟢 PASS
  (сам ответ площадки заблокирован egress-прокси среды, не кодом).

## 🔴 Не покрыто тестами вообще

| Модуль | Блок | Риск |
|---|---|---|
| `publishers/*` (все 7) | 03, 10 | **высокий** — публикация не проверена ни одним тестом |
| `core/orchestrator.py` (`_publish_one` — сама маршрутизация по коннекторам) | 10 | средний — очередь и повторы вокруг него покрыты `test_publish_queue.py` |
| `core/social_intel.py` | 04 | высокий |
| `core/instagram_reader.py` | 03, 04 | высокий |
| `core/youtube_reader.py` | 03, 04 | средний |
| `core/browser_reader.py` | 04 | средний |
| `core/server_browser.py` | 03 | средний |
| `core/telegram_bot.py` | 11 | высокий (главный интерфейс) |
| `core/command_center.py` | 01 | средний |
| `core/scheduler.py` | 01 | средний |
| `core/moderation.py` | 09 | средний |
| `core/autopilot.py` | 06 | средний |
| `core/viral_research.py` | 05 | средний |

**Вывод:** покрыта техническая обвязка (роутер, auth, настройки), а самая проблемная
часть — коннекторы, публикация и Telegram — не покрыта.

## Тесты, которых требует задача (не написаны)

| Тест | Что проверять | Статус |
|---|---|---|
| TEST 01 CORE | создание задачи, статусы, retry | ⚪ система задач отсутствует |
| TEST 02 AI PROVIDER | ✅ есть (`test_ai_router`, `test_free_providers`) | 🟢 PASS |
| TEST 03 Instagram OAuth | обмен кода, long-lived токен | ⚪ OAuth не реализован |
| TEST 04 Instagram Media Read | чтение постов/Reels/insights | ⚪ нет теста; ⚠️ живьём не проверено |
| TEST 05 Instagram Publishing | container → publish | ⚪ нет теста |
| TEST 06 Telegram | команды, кнопки, модерация | ⚪ нет теста |
| TEST 07 Threads | публикация и чтение | ⚪ чтения нет в коде |
| TEST 08 YouTube Publishing | загрузка Shorts | 🔴 в коде заглушка |
| TEST 09 Persistence | БД переживает рестарт | 🔴 не переживает |

## Честная оговорка
Ни один социальный коннектор **не проверялся вживую** с реальными токенами:
ключей нет, а среда аудита блокирует instagram.com / youtube.com через egress-прокси.
Статусы коннекторов в `SOCIAL_CONNECTORS.md` — «по коду», не «протестировано».
