# PROJECT_RECOVERY_MAP

Дата: 2026-09-22 · ветка `claude/zealous-pasteur-6i9g3m`

Правило документа (§5, §73 ТЗ): статус ставится по доказательству, а не по
наличию кода, ключа, кнопки или зелёного индикатора. Где доказательства нет —
пишется `UNKNOWN` или `BLOCKED_EXTERNAL_ACCESS`, а не «готово».

Что было доказано в этой сессии:

* **реальная генерация Higgsfield** — job `247423ab-2748-4593-bef0-f314739f1256`,
  модель `gpt_image_2_5`, 9:16, статус `completed`, `result_url` получен;
* **живой каталог моделей** — `models_explore` отдаёт `items[]` с `id`, `name`,
  `aspect_ratios`, `parameters`, блок `unlim`;
* **баланс аккаунта** — план `ultimate`, 759.62 кредита;
* **1322 автотеста** проходят на этой ветке.

Чего доказать из этой среды нельзя (и почему):

* скачивание файла по ссылке CDN — `d8j0ntlcm91z4.cloudfront.net` закрыт
  политикой прокси песочницы (`403 на CONNECT`), проверено;
* Render, Telegram, Postgres, ключи — доступов нет, переменных окружения нет.

---

## 1. Инфраструктура

| NAME | PURPOSE | CURRENT IMPLEMENTATION | ENTRY POINT | STATUS | REAL/MOCK | SAFE TO REPLACE |
|---|---|---|---|---|---|---|
| GitHub | код | репозиторий, ветка разработки | — | WORKING | REAL | нет |
| Render web | процесс приложения | `render.yaml`, `start.sh`, FastAPI `main.py` | `/api/health` | UNKNOWN (нет доступа) | REAL | нет |
| Render worker | долгие задачи | отдельного воркера в `render.yaml` нет — всё в web-процессе | — | NOT_CONFIGURED | — | да, §44 |
| Postgres | память, доступы, KV | `database/db.py`, таблица `Connection` как KV | `DATABASE_URL` | PARTIALLY_WORKING (бесплатный Postgres Render истекает, TODO #1) | REAL | нет |
| Очередь | долгие задачи | `publish_queue`, `production_queue` поверх БД, без брокера | — | PARTIALLY_WORKING | REAL | нет |
| Keepalive | не давать уснуть | `core/keepalive.py`, пинг своего `/api/health` | — | WORKING (по коду) | REAL | да |
| Переменные/секреты | доступы | `core/credentials.py` + `core/secrets.py` (шифрование) | дашборд, `/diag` | WORKING — проверено тестом моста БД→окружение | REAL | нет |

## 2. Приложение

| NAME | PURPOSE | IMPLEMENTATION | INPUT → OUTPUT | STATUS | REAL/MOCK |
|---|---|---|---|---|---|
| Telegram | главный интерфейс | `core/telegram_bot.py` (~40 команд), `task_feed` | сообщение → задача/результат | UNKNOWN живьём (нет токена); код есть, тесты зелёные | REAL |
| Dashboard | настройка и диагностика | `frontend/`, 7 разделов | — | UNKNOWN живьём | REAL |
| Оркестратор | понять и распределить | `core/marketing_director.py` (Claude tool-use + Gemini-фолбэк), `core/orchestrator.py` | запрос → шаги | UNKNOWN живьём | REAL |
| Task Engine | единый Task | `core/task_manager.py` (+ статусы, шаги, стоимость, восстановление) | — | WORKING (по тестам) | REAL |
| Task Spec | не терять тему (§9) | `core/task_spec.py` — разбор фразы правилами | «шашлык вечером» → kind/subject/platform/quality | WORKING (по тестам) | REAL |
| Execution Router | каким каналом (§14) | `core/exec_router.py` — режим, настроенность, остывание, история | — | WORKING (по тестам) | REAL |
| Model Router | выбор модели (§11) | `core/ai_router.py`, `core/model_registry.py` | — | PARTIALLY_WORKING (реестр ведётся по факту; живьём не проверен) | REAL |
| Higgsfield MCP | приоритетный канал | `core/hixiit.py` — клиент MCP по OAuth | prompt → job → url | **BROKEN → FIXED** (см. §3) | REAL |
| Higgsfield REST | канал по ключу | `core/higgsfield.py` — Soul/DoP по официальному API | — | BLOCKED_EXTERNAL_ACCESS (нет ключа и секрета, TODO #2) | REAL |
| Higgsfield OAuth | вход один раз (§15) | `core/mcp_oauth.py` — discovery, PKCE, refresh, callback | — | WORKING (шов до клиента проверен тестом); живого входа не было | REAL |
| Browser | браузерный канал | `core/server_browser.py`, `browser_agent`, `browser_reader` | — | UNKNOWN живьём | REAL |
| Artifact Registry | результат до доставки (§49,§50) | `core/artifacts.py` | url → artifact_id | WORKING; повтор доставки был **BROKEN → FIXED** | REAL |
| Storage | архив файлов | `core/drive_store.py` (Google Drive) | — | UNKNOWN живьём | REAL |
| Publishing | 6 площадок | `publishers/*` | — | UNKNOWN живьём | REAL |
| Memory | ниша, разборы, навыки | `core/research_store.py`, `skills_store` | — | PARTIALLY_WORKING (зависит от БД) | REAL |
| Scheduler | расписание | `core/scheduler.py`, 12 джобов, Asia/Almaty | — | UNKNOWN живьём | REAL |
| Diagnostics | самопроверка | `core/system_test.py`, `/diag`, `/netcheck`, `core/env_audit.py` | — | WORKING (по тестам) | REAL |

## 3. Найденные причины отказа

### 3.1 Ожидание результата нарушало протокол платформы — BROKEN → FIXED

`core/hixiit.py` просил `jobs_wait` держать соединение 45 секунд. Инструмент
официального MCP объявляет `timeout_seconds` как «default 15, **max 15**»
(проверено по живой схеме инструмента). Значение выше отклоняется проверкой
аргументов — то есть:

1. заявка на генерацию уходила и **кредиты списывались**;
2. каждый опрос готовности падал;
3. задача сообщала «Higgsfield не отдал результат вовремя» при готовом кадре.

Исправлено: шаг опроса ограничен протоколом (`MCP_WAIT_MAX_SECONDS = 15`),
общий запас времени сохранён и считается в секундах (`JOB_BUDGET_SECONDS`),
видео получило свой запас (`VIDEO_BUDGET_SECONDS`). Регрессия закрыта тестом
`tests/test_job_wait_protocol.py`, который падает на прежнем значении.

Почему это не поймали 1315 тестов: поддельный MCP в тестах принимал любые
аргументы. Новый тест ведёт себя как платформа — отклоняет значение выше
максимума (§73: подделка, которая всё принимает, не проверка).

### 3.2 Повторная отправка результата — BROKEN → FIXED

`artifacts.redeliver` отправляла результат по ссылке провайдера. Ссылка CDN
живёт часы, а повтор нужен именно позже. Две беды в одном месте:

* **тихий ложный успех**: `send_photo` не бросает исключение, а возвращает
  `{"ok": false}`. Результат не проверялся — артефакт помечался «доставлено
  повторно», а человеку не приходило ничего;
* копия файла в архиве Drive была, но не использовалась: `_archive` писала в
  артефакт «ссылку ИЛИ id», и при наличии ссылки id терялся, а по `webViewLink`
  Telegram файл забрать не может — это страница просмотра, а не файл.

Исправлено: `drive_store.download()` (файл байтами), `telegram_pub.send_file()`
(отправка multipart по общему пути с повторами и разбором 429), артефакт хранит
`storage_id`, `redeliver` проверяет результат отправки и при мёртвой ссылке
берёт копию из архива. Генерация заново не запускается ни в каком случае (§50).
Тесты: `tests/test_redeliver_from_archive.py`.

### 3.3 Проверенные и **снятые** гипотезы

* «OAuth-вход не доходит до клиента MCP» — **неверно**. `credentials.set()`
  зеркалит значение в окружение, а `load_into_env()` возвращает его после
  перезапуска (`higgsfield_mcp_token` проходит `is_credential` по окончанию
  `_token`). Шов раньше не проверялся ни одним тестом — все подменяли либо
  хранилище, либо `mcp_configured`. Закрыт тестом
  `tests/test_oauth_reaches_mcp_client.py`.
* «Форма вызова MCP неверна» — **неверно**. Сверено с живой схемой: `params`
  вложенным объектом, `medias[{value, role}]` по `media_id`, разбор ответа
  (`results[].id`, `jobs[].status`, `result_url`, `all_terminal`) и разбор
  каталога (`items[]`, блок `unlim`) совпадают с платформой.
* «Памяти не хватает / браузер душит сервер» — ранее опровергнуто замером
  (`/netcheck`: 209 из 512 МБ, задержка цикла 0.000 с). Новых данных нет.

## 4. Что мешает закрыть вертикальный срез (§82, §89)

| Шаг цепочки | Состояние |
|---|---|
| Telegram → Task | код есть, живьём не проверен (нет токена) |
| Task → Orchestrator → Router | WORKING по тестам |
| Router → Higgsfield | MCP: исправлен; REST: нет ключа и секрета |
| Реальная генерация | **PASS** — доказано настоящим job (§19-промпт) |
| Опрос готовности | **исправлено** (было: отказ на каждом опросе) |
| Download → Storage | BLOCKED_EXTERNAL_ACCESS: CDN закрыт прокси песочницы |
| Telegram delivery | BLOCKED_EXTERNAL_ACCESS: нет токена бота |

Требуемый доступ, чтобы снять BLOCKED (§77): `HIGGSFIELD_API_KEY` +
`HIGGSFIELD_SECRET` **или** выполненный `/hfconnect` на сервере, плюс прогон на
Render, где CDN и Telegram доступны.

## 5. Порядок дальнейших работ (§79)

P0 инфраструктура: вынести долгие задачи в Background Worker `render.yaml`
(сейчас всё в web-процессе, §44) · P1–P2 сделано · P3 Higgsfield: живой прогон
после ключей · P4 браузер: живая проверка · P6 хранилище: живая проверка Drive
(повтор доставки теперь на неё опирается) · далее QC, Telegram UI, публикация.
