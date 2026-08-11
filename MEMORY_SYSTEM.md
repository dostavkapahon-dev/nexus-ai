# MEMORY SYSTEM — NEXUS AI

## Хранилища

| Где | Что | Переживает рестарт Render? |
|---|---|---|
| SQLite `backend/nexus.db` | 9 таблиц | 🔴 **НЕТ** (нет диска в render.yaml) |
| Таблица `Connection` (KV) | состояние, ключи | 🔴 **НЕТ** (та же БД) |
| `backend/data/skills.json` | память уроков агента | 🟡 откат к git-версии |
| `backend/data/brand_voice.txt` | голос бренда | 🟡 откат к git-версии |
| `backend/data/hook_history.json` | антиповтор хуков (60) | 🔴 НЕТ (в `.gitignore`) |
| Render Environment | API-ключи | 🟢 ДА |

## Таблицы (`database/models.py`)

| Класс | Таблица | Назначение |
|---|---|---|
| `Niche` | niches | ниша: название, город, цель, площадки, тон |
| `ContentPlan` | content_plans | пункт контент-плана (day, platform, topic, hook, status) |
| `GeneratedContent` | generated_content | текст, ревью, картинка, версии под площадки |
| `Publication` | publications | факт публикации (plan_id, platform, status, external_id) |
| `AgentLog` | agent_logs | лог AI-вызова: агент, модель, токены, стоимость, время, ошибка |
| `CustomPrompt` | custom_prompts | переопределённые промпты агентов |
| `Connection` | connections | **KV-хранилище**: ключи API + состояние системы |
| `UserProfile` | user_profile | продукт, стиль, стратегия, ai_mode, Drive |
| `NicheAnalysisCache` | niche_analysis_cache | кэш анализа ниши (+ ссылка на Google Drive) |

⚠️ **Нет ни одного ForeignKey и каскада.** Удаление плана оставляет осиротевшие
`GeneratedContent` / `Publication` (`api/routes_queue.py:57`).
⚠️ **Нет alembic** ⇒ новые колонки не появятся в существующей БД ⇒ весь новый функционал
складывается в `Connection` как KV.

## Ключи `Connection`

| key_name | Содержимое | Модуль |
|---|---|---|
| `viral_recipe` | «рецепт вируса» из разбора референсов | `core/viral_research.py` |
| `autopilot_state` | stage, answers, questions, analysis, options, plan | `core/autopilot.py` |
| `control_feed` | лента событий, последние 60 | `core/command_center.py` |
| `last_strategy_options` | 3 предложенные стратегии | `core/strategy_advisor.py` |
| `chosen_strategy` | выбранная стратегия | `core/strategy_advisor.py` |
| `moderation_queue` | очередь контента на согласование | `core/moderation.py` |
| `pending_fix` | pid, по которому админ пишет правку | `core/moderation.py` |
| `last_auto_analyze` | дата последнего авто-разбора (дедуп) | `core/auto_report.py` |
| `ig_handle`, `tiktok_handle`, `youtube_handle` | ники для аналитики | `core/social_intel.py` |
| `*_api_key`, `*_token` | все секреты | `api/routes_settings.py` |

⚠️ Read-modify-write **без блокировки**: scheduler, Telegram и дашборд могут писать
одновременно → гонки и потеря записей.
⚠️ Ограничение размера есть только у `control_feed` (60) и `hook_history` (60);
`moderation_queue`, `autopilot_state`, `viral_recipe` растут неограниченно в одном Text-поле.

## Память агента (`core/skills_store.py`)
Файл `data/skills.json`. Запись: `{id, kind, title, body, tags, score, used, created_at}`,
`kind ∈ hook|format|visual|audience|mistake|rule`.
- `context_for()` — собирает блок для промпта, отдельной секцией «ЧТО НЕ СРАБОТАЛО».
- `learn_from(text, source)` — дешёвой моделью извлекает ≤5 уроков и сохраняет.
Потребители: `content_factory.py:150`, `viral_research.py:158`, REST `/api/agent/skills`.

## Чего нет ⚪
1. Таблицы задач (см. `TASK_SYSTEM.md`).
2. Истории публикаций **с метриками** — `Publication` не хранит просмотры/лайки/ER,
   поэтому обучение на реальных результатах невозможно.
3. Векторного хранилища / эмбеддингов — память плоская, отбор по score и kind.
4. Версионирования промптов (`CustomPrompt` перезаписывается in-place).
5. Аудита изменений настроек и ключей.
6. Multi-tenant: `UserProfile` де-факто одна строка, `Connection` глобален.
