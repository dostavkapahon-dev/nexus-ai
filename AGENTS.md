# AGENTS — реестр агентов NEXUS AI

## Реестр ролей (`agents/registry.py`)

Роли из ТЗ объявлены явно; классы-агенты и core-модули не переписывались —
роль ссылается на то, что уже работает.

| Роль | Чем занимается | Нужен доступ | Опирается на |
|---|---|---|---|
| `director` | главный управляющий агент | — | `core/marketing_director.py` |
| `research` | исследование интернета | — | `core/websearch.py`, `core/viral_research.py`, `agents/trend_analyst.py` |
| `instagram` | работа с Instagram | `INSTAGRAM_ACCESS_TOKEN` | `connectors/instagram.py`, `core/instagram_reader.py` |
| `tiktok` | работа с TikTok | `TIKTOK_ACCESS_TOKEN` | `connectors/tiktok.py` |
| `telegram` | работа с Telegram | `TELEGRAM_BOT_TOKEN` | `core/telegram_channels.py`, `connectors/telegram.py` |
| `content_strategist` | контентная стратегия | — | `agents/strategist.py`, `agents/niche_analyst.py` |
| `script` | сценарии роликов | — | `core/creative_director.py` |
| `video` | видео и Reels | — | `core/media_generator.py`, `core/montage.py` |
| `copywriter` | тексты | — | `agents/copywriter.py`, `voice_adapter.py`, `adapter.py` |
| `analytics` | аналитика | — | `core/post_analytics.py`, `agents/reporter.py` |
| `publisher` | публикация | — | `core/publish_queue.py`, `core/autopublish.py`, `publishers/` |

Роль без нужного доступа считается нерабочей: она не попадает в системный промпт
дирижёра и отказывается запускаться с понятной причиной, а не падает по ходу дела.

`delegate` дирижёра принимает и ключ роли, и имя модели-исполнителя: сначала
проверяется реестр, затем `core/dispatch.py`.

Все задачи проходят через дирижёра. Агенты не публикуют сами — это проверяется
тестом `tests/test_agent_registry.py::test_agents_are_not_publishing_on_their_own`.

API: `GET /api/agents`, `POST /api/agents/{key}/run` (запуск оформляется задачей
и виден в общем журнале). Страница — «🤖 Агенты».

## Базовый класс
`agents/base_agent.py:8` — `BaseAgent(ABC)`, атрибут `name`.
- `call_ai(db, niche_id, variables) -> str` — берёт промпт и модель из `core/prompt_store.py`
  (БД `custom_prompts` → фолбэк `DEFAULT_PROMPTS`), подставляет переменные, зовёт
  `ai_router.call`, логирует в `AgentLog`.
- `log(db, niche_id, status, model, tokens, cost, duration, error)` — запись расхода.
- Профиль Главного агента (`core/agent_profile.py`) подмешивается в системную часть
  промпта здесь же — одной точкой на всех агентов.

⚠️ Выбор модели у агентов идёт **только** через `prompt_store`. Словари `ECONOMY_MODELS` /
`PREMIUM_MODELS` из `ai_router` на агентов не влияют, поэтому режим `ai_mode` не работает.

## Агенты

| Агент | Файл | Метод | Модель по умолчанию | Возвращает | Статус |
|---|---|---|---|---|---|
| NicheAnalyst | `agents/niche_analyst.py:4` | `analyze(db, niche_id, niche, city, goal, tone)` | claude-sonnet-4-20250514 | audience, pain_points, content_pillars, competitors, best_times | 🟢 |
| ViralHunter | `agents/viral_hunter.py:4` | `hunt(db, niche_id, niche, platforms, audience, account_intel)` | claude-sonnet-4-20250514 | viral_topics, hooks, formats, hashtags | 🟢 |
| Strategist | `agents/strategist.py:4` | `create_plan(...)` | claude-sonnet-4-20250514 | 30 × {day, platform, topic, hook, format} | 🟢 |
| Copywriter | `agents/copywriter.py:3` | `write(...)` | gpt-4o | текст поста | 🟢 |
| Reviewer | `agents/reviewer.py:4` | `review(...)` | claude-sonnet-4-20250514 | text_reviewed, score, improvements | 🟢 |
| VoiceAdapter | `agents/voice_adapter.py:3` | `adapt(...)` | claude-sonnet-4-20250514 | текст под голос бренда | 🟢 |
| VisualCreator | `agents/visual_creator.py:3` | `create(...)` | gpt-4o | image_prompt, image_url | 🟢 |
| PlatformAdapter | `agents/adapter.py:4` | `adapt(...)` | gpt-4o-mini | версии под 6 площадок | 🟢 |
| TrendAnalyst | `agents/trend_analyst.py:11` | `analyze_trends(...)` | **gemini-1.5-flash** | top_topics, best_hooks, … | 🔴 модели нет в роутере |
| FunnelAgent | `agents/funnel_agent.py:22` | `generate_reply(...)`, `get_funnel_stats(...)` | **gemini-1.5-flash** | reply, intent, should_reply | 🔴 модель + не вызывается нигде |
| Reporter | `agents/reporter.py:11` | `build_status_report`, `build_trend_report` | — (без AI) | HTML-отчёт | 🟢 |

## Core-«мозги» (не наследуют BaseAgent, не логируются в AgentLog)

| Модуль | Функции | Модель |
|---|---|---|
| `core/marketing_director.py` | `run_director(goal, context, max_steps)` — tool-loop оркестратора | claude-sonnet-4-6 → Gemini-фолбэк |
| `core/creative_director.py` | `build_brief`, `choose_strategy`, `wow_review` | claude-sonnet-4-6 (хардкод) |
| `core/self_critique.py` | `pre_check(agent, task, context)` — уточнение задачи до дорогой генерации | `ECONOMY_MODELS['reviewer']` |
| `core/skills_store.py` | `context_for`, `learn_from` — память уроков | `ECONOMY_MODELS['reviewer']` |
| `core/strategy_advisor.py` | `build_options`, `choose_option` | `ECONOMY_MODELS['strategist']` |
| `core/autopilot.py` | `deep_analysis`, `build_questions`, `build_strategies`, `build_week_plan`, `predict_virality` | `ECONOMY_MODELS[*]` |
| `core/intent.py` | `route`, `chat_reply` | `ECONOMY_MODELS['adapter']` |

## Инструменты оркестратора (`marketing_director.TOOLS`)
`analyze` (досье аккаунта / разбор ролика) · `delegate` (подзадача другой модели) ·
`run_browser` (действия на сайте) · `make_video` · `publish` · `done`.

## Взаимодействие агентов
Структурированная передача данных существует внутри `orchestrator.run_pipeline`
(результат одного агента идёт во входные переменные следующего) и внутри
`content_factory.run_factory` (plan → brief → assets → review).
⚠️ Единого протокола agent-to-agent (типизированные контракты, confidence, sources) нет.

## Тесты не ходят в сеть

Прогон не должен зависеть от чужого сервиса — ни по результату, ни по времени.
Autouse-фикстура `_no_outbound_network` в `backend/tests/conftest.py` закрывает
настоящий транспорт httpx и сам сокет; локальные адреса оставлены (на них
держатся служебные пары сокетов внутри asyncio), а `ASGITransport`, через
который тесты стучатся в приложение, сетью не является и работает как раньше.

Попытка сходить наружу падает сразу и громко:

    OutboundBlocked: Тест пошёл в сеть: GET https://... Подмените вызов заглушкой

Так и надо чинить — подменить вызов заглушкой. Дважды подряд живой запрос
протекал в прогон (проверка сгенерированной картинки, затем полный запуск
фабрики из теста), и оба раза прогон оставался зелёным: заметить это можно было
только по времени CI — 1 м 30 с → 5 м 54 с → 3 м 09 с.

По той же причине не оставляйте в тестах настоящие паузы: `asyncio.sleep`
подменяется фикстурой (`no_backoff` в `tests/test_ai_router.py`). Два теста без
неё стоили 40 секунд из 74.
