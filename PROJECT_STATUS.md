# PROJECT STATUS — NEXUS AI

> Аудит от 2026-08-11. Статусы получены **анализом кода**, без живых прогонов с реальными
> токенами (ключей нет, соцсети закрыты egress-прокси среды аудита).
> Всё, что требует живой проверки, помечено ⚠️.

Легенда: 🟢 WORKING · 🟡 PARTIAL · 🔴 BROKEN · ⚪ NOT IMPLEMENTED · 🔵 BLOCKED BY API

## Корневая причина нестабильности 🔴

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
| 01 | Core / Orchestrator | 🟡 | Дирижёр есть; нет task id/статусов/retry; две конкурирующие «головы» |
| 02 | AI Provider Layer | 🟢 | Единый `ai_router.call`, 6 free + 5 платных, фолбэк-цепочка, backoff |
| 03 | Social Connectors | 🟡 | Нет интерфейса `SocialConnector`, нет OAuth/refresh/webhooks/rate-limit |
| 04 | Social Analytics | 🟡 | Чтение есть, но результаты **нигде не сохраняются** |
| 05 | Market / Competitor Research | 🟡 | `viral_research` + duckduckgo + `/hunt`; результат только в `viral_recipe` |
| 06 | Content Strategy | 🟢 | `strategy_advisor` + `autopilot` (3 варианта, план на 7 дней) |
| 07 | Content Generation | 🟢 | Copywriter / adapter / creative_director, ротация хуков |
| 08 | Image / Video Generation | 🟢 | Pollinations (беспл.), Imagen / DALL·E / Stability, HeyGen / HiggsField / Runway |
| 09 | Content Pipeline | 🟢 | `run_factory` со сквозным отчётом по шагам |
| 10 | Publishing Engine | 🟡 | Публикация + браузер-фолбэк; нет retry, очереди, персистентных статусов |
| 11 | Telegram Control Center | 🟢 | ~30 команд, inline-кнопки, голос/медиа, модерация approve/fix/reject |
| 12 | Web Dashboard | 🟡 | 11 страниц; `Analytics` выпала из навигации; нет health агентов и соцсетей |

## Критические поломки

| Приоритет | Проблема | Где |
|---|---|---|
| 🔴 | Вся БД эфемерна на Render | `render.yaml`, `database/db.py:5` |
| 🔴 | `gemini-1.5-flash` — модели нет в роутере; trend_analyst и funnel_agent стартуют с ошибки | `core/prompt_store.py:50,55` |
| 🔴 | `FunnelAgent` не вызывается ниоткуда — мёртвый код | `agents/funnel_agent.py` |
| 🔴 | `publish_youtube_short` — заглушка, всегда `ok:False` | `publishers/youtube_pub.py:11` |
| 🟡 | `ai_mode` (economy/premium) — фикция, агенты его не читают | `core/orchestrator.py:54` |
| 🟡 | Расходы «мимо кассы»: логируется только `BaseAgent` | `agents/base_agent.py:29` |
| 🟡 | Секреты plaintext в БД и в `os.environ` всего процесса | `api/routes_settings.py:80-94` |
| 🟡 | Гонки при read-modify-write KV `Connection` без блокировки | `core/command_center.py`, `core/moderation.py` |
| ⚪ | Нет системы задач (task id, статусы, retry, история) | — |
| ⚪ | Нет OAuth и long-lived токенов для соцсетей | — |

## Что работает надёжно
- AI Provider Layer с фолбэком между 11 провайдерами (BLOCK 02).
- Telegram Control Center (BLOCK 11) — основной рабочий интерфейс.
- Конвейер генерации контента (BLOCK 09) со сквозным отчётом.
- Единый пульт: дашборд и Telegram на одном мозге (`core/command_center.py`).

## Порядок исправления
См. `TODO.md`.
