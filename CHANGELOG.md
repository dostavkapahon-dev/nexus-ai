# CHANGELOG — NEXUS AI

## [Не влито] ветка `claude/social-media-automation-4gz8k0` — PR #41

### Убрана зависимость от Ayrshare
- Удалён `publishers/ayrshare_pub.py` — сторонний платный посредник, от доступности
  которого зависели и публикация, и аналитика.
- Публикация переведена на нативные API площадок: Instagram (Graph API), TikTok
  (Content Posting API), YouTube (Data API), VK, Threads, Telegram — с браузерным фолбэком.
- Аналитика переведена в новый `core/social_intel.py` с сохранением интерфейса
  (`is_configured`, `get_account_intelligence`).

### Публикация и анализ без API
- `core/server_browser.py` — браузер на стороне сервера (Playwright): те же команды,
  что у десктоп-агента, работает **без ПК пользователя**.
- Удалённый облачный браузер по CDP (`NEXUS_BROWSER_CDP`) — Chromium не поднимается
  на самом инстансе, Render остаётся лёгким.
- `core/browser_reader.py` — чтение профилей и постов через браузер, без ключей.
- Режимы `NEXUS_PUBLISH_MODE` и `NEXUS_ANALYZE_MODE`: `auto` / `browser` / `api`.

### Чтение соцсетей через официальные API
- `core/instagram_reader.py` — свой аккаунт с инсайтами (охват, просмотры, сохранения,
  репосты) + конкуренты через Business Discovery.
- `core/youtube_reader.py` — канал, подписчики, видео со статистикой (Data API v3).

### Единый пульт управления
- `core/command_center.py` — одна точка входа для дашборда и Telegram, общая лента
  событий, зеркалирование результатов в Telegram.
- `api/routes_control.py` — `POST /api/control/command`, `GET /api/control/feed`.
- Карточка «Пульт управления» на странице Центра в дашборде.

### Анализ из самого агента
- Инструмент `analyze` у оркестратора (`marketing_director`): досье аккаунта
  (instagram/tiktok/youtube) или разбор ролика по ссылке.
- Системный промпт требует вызывать `analyze` перед созданием контента.

### Безопасность
- SSRF-guard `server_browser.url_allowed`: блокируются loopback, приватные подсети,
  link-local и хосты облачных метаданных; разрешены только внешние http(s).
- Санитизация ников в `browser_reader` и в `instagram_reader.analyze_competitor`
  (username идёт в field-выражение Graph API).

### Деплой
- `Dockerfile` + `docker-compose.yml` (мультиарх, ffmpeg, Chromium, том `/data`).
- `DEPLOY_ORACLE.md` — инструкция для 24/7-хостинга.
- `render.yaml` — новые переменные публикации и анализа; лёгкая сборка без Chromium
  (браузер удалённый).

### BLOCK 09 — конвейер контента
- `content_factory._flush_steps()` переносит шаги конвейера в журнал задачи: раньше
  `report["steps"]` жил только в ответе, и по упавшей фабрике нельзя было понять,
  на каком шаге она сломалась. Журналирование идёт пачками в четырёх контрольных
  точках (до дорогой генерации, после медиа, после видео, после публикации),
  без повторов и без риска уронить конвейер.
- Точка согласования стала явным шагом `approval_requested`, а задача, упёршаяся
  в аппрув человека, получает статус **WAITING**, а не COMPLETED — раньше система
  сообщала «готово» о неопубликованном контенте.
- `POST /api/automation/factory` теперь создаёт Task и возвращает `task_id`:
  ручной запуск из дашборда оставляет такой же след, как ночной джоб.
- `run_daily_factory` возвращает отчёт наверх, чтобы планировщик видел WAITING.

### Тесты
- 137 passed на всех этапах.

## Документация аудита (2026-08-11)
Созданы: `PROJECT_STATUS.md`, `ARCHITECTURE.md`, `AGENTS.md`, `AI_PROVIDERS.md`,
`SOCIAL_CONNECTORS.md`, `INTEGRATIONS.md`, `API_LIMITATIONS.md`, `ARCHIE_DEPENDENCIES.md`,
`TASK_SYSTEM.md`, `MEMORY_SYSTEM.md`, `COST_CONTROL.md`, `TEST_RESULTS.md`, `TODO.md`,
`CHANGELOG.md`.

## Предыдущие (из истории master)
- Память скиллов + страница настройки агента в дашборде.
- Командный центр — живая карта агентов и статус ИИ-провайдеров.
- Реестр бесплатных провайдеров: Groq, Cerebras, OpenRouter, Mistral, GitHub Models, NVIDIA NIM.
- Claude-дирижёр распределяет подзадачи между Gemini / DeepSeek / OpenAI.
- Устойчивость к 429: lite-модели, перебор квот.
