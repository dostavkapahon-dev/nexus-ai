# AGENTS — реестр агентов NEXUS AI

## Базовый класс
`agents/base_agent.py:8` — `BaseAgent(ABC)`, атрибут `name`.
- `call_ai(db, niche_id, variables) -> str` — берёт промпт и модель из `core/prompt_store.py`
  (БД `custom_prompts` → фолбэк `DEFAULT_PROMPTS`), подставляет переменные, зовёт
  `ai_router.call`, логирует в `AgentLog`.
- `log(db, niche_id, status, model, tokens, cost, duration, error)` — запись расхода.

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
