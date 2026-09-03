# AI PROVIDERS — NEXUS AI

Единый интерфейс: `core/ai_router.py` → `ai_router.call(model, system, prompt)`
→ `{text, tokens, cost, model_used, duration_sec}`. Синглтон `ai_router` (`:392`).

## Бесплатные провайдеры (`FREE_PROVIDERS`, `ai_router.py:97`)

| Провайдер | Alias | Base URL | Переменная |
|---|---|---|---|
| NVIDIA NIM | `nvidia-free` | integrate.api.nvidia.com/v1 | `NVIDIA_API_KEY` |
| Groq | `groq-free` | api.groq.com/openai/v1 | `GROQ_API_KEY` |
| Cerebras | `cerebras-free` | api.cerebras.ai/v1 | `CEREBRAS_API_KEY` |
| OpenRouter | `openrouter-free` | openrouter.ai/api/v1 | `OPENROUTER_API_KEY` |
| Mistral | `mistral-free` | api.mistral.ai/v1 | `MISTRAL_API_KEY` |
| GitHub Models | `github-free` | models.github.ai/inference | `GITHUB_MODELS_TOKEN` |

Все OpenAI-совместимые. ID модели не зашит — резолвится по `/models` с кэшем
(`resolve_free_model`, `:171`). Стоимость = 0.

## Платные (`AI_ROUTING`, `:8`)

| Провайдер | Модели | Переменная |
|---|---|---|
| Anthropic | claude-sonnet-4-6, claude-sonnet-4-20250514, claude-haiku-4-5 | `ANTHROPIC_API_KEY` |
| OpenAI | gpt-4o, gpt-4o-mini | `OPENAI_API_KEY` |
| Google | gemini-2.0-flash, gemini-2.5-flash, gemini-flash-latest, gemini-2.0-flash-lite | `GEMINI_API_KEY` |
| Perplexity | sonar-pro, sonar-reasoning-pro, sonar | `PERPLEXITY_API_KEY` |
| DeepSeek | deepseek-chat, deepseek-reasoner | `DEEPSEEK_API_KEY` |

## Выбор модели — три независимых механизма ⚠️
1. **Агенты** → `core/prompt_store.py` (БД `custom_prompts` → `DEFAULT_PROMPTS`).
2. **Модули core** → `ECONOMY_MODELS.get(роль, дефолт)`.
3. **Хардкод** `claude-sonnet-4-6` в `creative_director.py:69,140`.

`PREMIUM_MODELS` используется только в `estimate_cost` (`:272`). Это причина того, что
переключатель `ai_mode` (economy/premium) ни на что не влияет.

### ECONOMY_MODELS (`ai_router.py:233`)
```
niche_analyst  → deepseek-chat        reviewer       → gemini-2.0-flash-lite
viral_hunter   → gemini-2.0-flash-lite voice_adapter → deepseek-chat
strategist     → deepseek-chat        visual_creator → gpt-4o-mini
copywriter     → deepseek-chat        adapter        → gpt-4o-mini
```

## Фолбэк и устойчивость
`FALLBACK_CHAIN` (`:270`) = 6 free-алиасов + `PAID_FALLBACK_CHAIN` (`:38`):
gemini-2.0-flash-lite → gemini-2.0-flash → gemini-flash-latest → deepseek-chat →
gpt-4o-mini → claude-sonnet-4-6.

В `call` (`:352`): отсев моделей без ключа, 3 попытки с backoff `2**attempt`;
при `insufficient_quota / resource_exhausted / 429 / not found / unsupported / deprecat`
— немедленный переход к следующей модели (`:384`). Само-ремонт Gemini через
`resolve_gemini_model()` (`:55`). Если всё упало — `RuntimeError` со сводкой ошибок.

## Учёт стоимости
`COST_PER_1K` (`:244`), расчёт tokens/1000 × ставка. **Оценочный, не из ответа API.**
🟡 Токены Gemini считаются как `len(text.split())*2` (`:311`).
🟡 Логируются только вызовы через `BaseAgent`; autopilot, content_factory,
marketing_director, viral_research, skills_store расходуют бюджет мимо `AgentLog`.

## Делегирование (`core/dispatch.py`)
`EXECUTORS` (gemini/deepseek/openai/perplexity/claude + 6 free), `available_executors()`,
`cheapest_available()`, `executors_doc()` (строка для системного промпта дирижёра),
`delegate(executor, task, system, context)`, `routing_table()` (диагностика для UI).
При недоступном исполнителе — автоподмена на самого дешёвого с флагом `substituted_for`.

## Ограничения текущей реализации
- `max_tokens=4096` захардкожен во всех адаптерах.
- Нет `temperature`, нет стриминга, нет истории сообщений (только system + один user turn).
