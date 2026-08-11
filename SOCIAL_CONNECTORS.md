# SOCIAL CONNECTORS — NEXUS AI

> ⚠️ Статусы получены анализом кода. Живых прогонов с реальными токенами не проводилось.

## Принцип
Соцсети подключаются **напрямую** (официальные API), AI не является транспортным слоем.
При отсутствии токена работает браузерный путь (`core/server_browser.py`), который тоже
не использует AI как транспорт — модель лишь извлекает данные из уже полученной страницы.

## Текущее состояние

| Платформа | Публикация | Чтение / аналитика | Статус |
|---|---|---|---|
| Telegram | `publishers/telegram_pub.py` (свой бот) | — | 🟢 |
| Instagram | `publishers/instagram_pub.py` (Graph API v19) + браузер | `core/instagram_reader.py` | 🟡 ⚠️ |
| TikTok | `publishers/tiktok_pub.py` (Content Posting API, **только PHOTO**) | yt-dlp / браузер | 🟡 |
| YouTube | `publishers/youtube_pub.py` — **заглушка**, всегда `ok:False` | `core/youtube_reader.py` (Data API v3) / yt-dlp / браузер | 🔴 публикация |
| Threads | `publishers/threads_pub.py` (Graph API v1.0) | ⚪ нет | 🟡 |
| VK | `publishers/vk_pub.py` (VK API 5.199) | — | 🟢 по коду |

Маршрутизация публикации: `core/orchestrator.py::_publish_one` —
нативный API при наличии токена → браузерный фолбэк.
Режим задаётся `NEXUS_PUBLISH_MODE` = `auto` / `browser` / `api`.

## Чего нет у ВСЕХ коннекторов ⚪
- Базового класса / интерфейса `SocialConnector` — сейчас это свободные функции.
- OAuth-флоу (обмен кода на токен) — токены вводятся руками в дашборде.
- Refresh / long-lived токенов.
- Webhooks (кроме Telegram polling).
- Rate-limit и backoff.
- Работы с комментариями.
- Health-check валидности токена и permissions.

## Instagram — техаудит

**Есть:** Graph API v19; `my_profile` (username, followers_count, media_count, biography);
`my_media` (посты и Reels); `media_insights` (reach, likes, comments, saved, shares, plays);
`analyze_competitor` через Business Discovery; публикация container → media_publish.

**Требования Meta:** аккаунт Business или Creator, привязанный к Facebook Page.
Permissions: `instagram_basic`, `instagram_manage_insights`, `pages_read_engagement`,
`pages_show_list`, для публикации — `instagram_content_publish`, `pages_manage_posts`.

**Нет:** OAuth-обмена кода, long-lived токена (**короткоживущий умрёт через ~60 дней молча**),
webhooks, комментариев, rate-limit, проверки типа аккаунта при подключении.

**🔵 BLOCKED_BY_API:** чтение личных (не Business) аккаунтов; публикация Stories;
часть insights и расширенные permissions — требуют App Review Meta.

## Threads — техаудит
**Есть:** публикация TEXT / IMAGE (container → threads_publish), нужны
`THREADS_ACCESS_TOKEN` + `THREADS_USER_ID`.
**Нет:** OAuth, чтение профиля, чтение публикаций, статистика, обработка лимитов.

## TikTok — техаудит
**Есть:** Content Posting API v2, `DIRECT_POST` для PHOTO, `get_tiktok_creator_info`.
**Нет:** публикации видео (основной формат!), OAuth, чтения статистики через API.

## Целевая структура (предложение, не реализовано)
```
SocialConnector (ABC)
 ├── publish(text, media) -> PublishResult
 ├── read_profile() -> Profile
 ├── read_posts(limit) -> list[Post]
 ├── health() -> {token_valid, expires_at, permissions}
 └── refresh_token()
      ├── InstagramConnector
      ├── ThreadsConnector
      ├── TelegramConnector
      ├── TikTokConnector
      └── YouTubeConnector
```
