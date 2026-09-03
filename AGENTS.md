# AGENTS — кто есть в системе и как они связаны

Обновлено: 2026-09-03

Все агенты наследуют `agents/base_agent.py::BaseAgent`, вызывают LLM через
`core/ai_router.py` и логируют каждый вызов в таблицу `agent_logs`
(модель, токены, стоимость, длительность, ошибка).
Промпты и модели — `core/prompt_store.py::DEFAULT_PROMPTS`, переопределяются
в таблице `custom_prompts` через `/api/prompts` или страницу PromptStudio.

## Оркестраторы

| Кто | Файл | Что делает |
|---|---|---|
| **Cloud Opus** | `core/marketing_director.py` | Главный. Принимает задачу словами, сам выбирает инструменты: `run_browser`, `make_video`, `make_image`, `publish`, `done`. Работает на Claude tool-use; при отсутствии ключа Anthropic — на Gemini по JSON-протоколу. |
| NexusCore | `core/orchestrator.py` | Детерминированный пайплайн ниши: анализ → план → генерация → публикация. |
| Content Factory | `core/content_factory.py` | Сквозной цикл одного ролика: анализ → бриф → стратегия → обложка → раскадровка → видео → проверка → публикация. |
| Creative Director | `core/creative_director.py` | Выбор стратегии, бриф, финальная проверка «вау», подсказки по стоимости. |
| Browser Agent | `core/browser_agent.py` | Vision-цикл: скриншот → решение → действие на ПК пользователя. |

## Специализированные агенты

| Агент | Файл | Вход → выход |
|---|---|---|
| `niche_analyst` | `agents/niche_analyst.py` | ниша, город, цель → профиль ниши и аудитории |
| `viral_hunter` | `agents/viral_hunter.py` | ниша, площадки, аудитория → вирусные паттерны |
| `strategist` | `agents/strategist.py` | ниша + вирусные данные → контент-план (строки `content_plans`) |
| `copywriter` | `agents/copywriter.py` | тема, хук, ToV → текст поста |
| `reviewer` | `agents/reviewer.py` | текст → отредактированный текст + оценка |
| `voice_adapter` | `agents/voice_adapter.py` | текст → текст голосом автора |
| `visual_creator` | `agents/visual_creator.py` | тема, текст → промпт визуала + изображение |
| `adapter` | `agents/adapter.py` | текст → версии под каждую площадку |
| `trend_analyst` | `agents/trend_analyst.py` | ниша → свежие тренды (ежедневно в 09:00) |
| `funnel_agent` | `agents/funnel_agent.py` | ниша, цель → воронка |
| `reporter` | `agents/reporter.py` | БД → отчёт о состоянии (`/status`, `/report`) |

## Связи

```
run_full_pipeline:   niche_analyst → viral_hunter → [кэш Google Drive] → strategist → content_plans
generate_for_plan:   copywriter → reviewer → voice_adapter → visual_creator (+HIXIIT) → adapter
                     → generated_content → превью в Telegram с кнопками
publish_plan:        platform_versions → официальный API площадки → фолбэк браузер-агент
```

## Генеративный слой

**HIXIIT** (`core/hixiit.py`) — не агент, а слой под агентами. Его вызывают
`visual_creator` (через оркестратор) и Cloud Opus (инструменты `make_image` / `make_video`).
Он сам определяет тип генерации, подбирает модель из каталога аккаунта и возвращает
либо ссылку на медиа, либо внятную причину отказа.
