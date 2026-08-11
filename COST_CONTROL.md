# COST CONTROL — учёт расходов на AI

## Текущее состояние: 🟡 PARTIAL

## Как считается
`core/ai_router.py`: `COST_PER_1K` (`:244`) — ставка за 1000 токенов на модель.
Каждый адаптер провайдера возвращает `{text, tokens, cost, model_used}`.
Стоимость = `tokens / 1000 × ставка` — **оценочная**, не берётся из ответа API.
Free-провайдеры всегда `cost = 0.0`.

## Где сохраняется
Только `AgentLog` (`tokens_used`, `cost_usd`, `model_used`, `duration_sec`),
запись делает `agents/base_agent.py:29` из `call_ai`.

## 🕳 Главная дыра
Логируются **только вызовы через `BaseAgent`**. Мимо учёта проходят:

| Модуль | Что делает |
|---|---|
| `core/autopilot.py` | 5 LLM-вызовов на полный цикл |
| `core/content_factory.py` | анализ, планирование |
| `core/creative_director.py` | бриф + wow-review (claude-sonnet-4-6, дорогая) |
| `core/marketing_director.py` | tool-loop дирижёра, до 12 шагов |
| `core/viral_research.py` | разбор рецепта |
| `core/strategy_advisor.py` | построение стратегий |
| `core/self_critique.py` | pre_check |
| `core/skills_store.py` | learn_from |
| `core/intent.py` | маршрутизация + chat_reply на каждое сообщение |
| `core/dispatch.py` | delegate (возвращает cost, но не пишет его в БД) |

**Следствие:** цифра «Потрачено» в отчётах систематически занижена — иногда в разы.

## Прочие неточности
- Токены Gemini считаются как `len(text.split()) * 2` (`ai_router.py:311`) — грубая оценка.
- Free-провайдеры без поля `usage` в ответе — токены тоже эвристика.
- `PREMIUM_MODELS` участвует только в `estimate_cost` (`:272`), на реальные вызовы не влияет.

## Где видно пользователю
| Место | Что показывает | Проблема |
|---|---|---|
| `Analytics.jsx` | «Стоимость AI» из `/api/analytics/{niche_id}` | только по одной нише; **страница отсутствует в навигации** |
| `/api/profile/cost-estimate` | прогноз, не факт | — |
| `Control.jsx`, `Director.jsx` | `est_cost` стратегии | оценка до запуска |
| Telegram `/status` | сумма `AgentLog.cost_usd` за 24ч | занижена из-за дыры выше |

## Чего нет ⚪
- Единой точки логирования (обёртки над `ai_router.call`, которая пишет расход всегда).
- Общего счётчика за день / месяц по всей системе.
- Бюджетных лимитов и алертов при превышении.
- Разбивки по задачам (нет `task_id`) и по площадкам.
- Реального переключателя economy/premium (`ai_mode` не влияет на выбор модели).

## Как экономится сейчас (что работает 🟢)
- 6 бесплатных провайдеров первыми в `FALLBACK_CHAIN` — платные только при их недоступности.
- `ECONOMY_MODELS` для core-модулей (deepseek-chat, gemini-flash-lite, gpt-4o-mini).
- `self_critique.pre_check` — уточнение задачи дешёвой моделью до дорогой генерации.
- `skills_store.context_for` — память вместо повторного research.
- Раскадровка через Pollinations (бесплатно, 0 токенов).
- Дирижёру предписано отдавать тексты через `delegate` дешёвым исполнителям.

## Целевое (не реализовано)
1. Обёртка `tracked_call(task_id, agent, model, …)` вокруг `ai_router.call` — расход пишется
   всегда, с привязкой к задаче.
2. Таблица `CostEntry` или расширение `AgentLog` полем `task_id`.
3. Бюджет в `UserProfile` + алерт в Telegram при 80 % и стоп при 100 %.
4. Дашборд: расходы за день/неделю/месяц, топ дорогих задач и моделей.
