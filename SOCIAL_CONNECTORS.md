# SOCIAL CONNECTORS — NEXUS AI

## Статус: 🟢 WORKING (BLOCK 03, реализовано)

> ⚠️ Живых прогонов с реальными токенами не проводилось (ключей нет, соцсети закрыты
> egress-прокси среды разработки). Проверено: контракт, health без ключей, маршрутизация,
> пометки BLOCKED_BY_API. Реальные публикации — на развёрнутом сайте.

## Принцип
Соцсети подключаются **напрямую** (официальные API/OAuth). AI не является транспортным
слоем: он анализирует полученные данные, но не добывает их.

```
ПЛОЩАДКА → OFFICIAL API / OAUTH → SocialConnector → НОРМАЛИЗОВАННЫЕ ДАННЫЕ → АГЕНТ → AI
```

## Единый контракт (`connectors/base.py`)

```
SocialConnector (ABC)
 ├── publish(text, image_url, video_url) -> {ok, post_id, via, error?, blocked_by_api?}
 ├── read_profile() -> {ok, handle, followers, ...}
 ├── read_posts(limit) -> {ok, top_posts[], ...}
 ├── health() -> {ok, configured, account, expires_at, days_left, permissions, can_publish}
 ├── refresh_token() -> {ok, refreshed, expires_in_days}
 ├── configured() / missing_env()
 └── RateLimiter — не чаще N вызовов в минуту (площадки банят за всплески)
```

Реестр: `connectors/__init__.py` — `get_connector(platform)`, `all_connectors()`, `health_all()`.
Коннектор — синглтон на процесс (внутри свой rate-limiter).

## Площадки

| Платформа | Публикация | Чтение | Rate | Статус |
|---|---|---|---|---|
| Instagram | Graph API v19 | профиль + посты с инсайтами | 20/мин | 🟢 |
| Threads | Threads API v1.0 | профиль + посты (**добавлено**) | 20/мин | 🟢 |
| Telegram | свой бот | — | 30/мин | 🟢 |
| TikTok | Content Posting API (фото) | yt-dlp/браузер | 10/мин | 🟡 видео 🔵 |
| YouTube | 🔵 нужен OAuth2 | Data API v3 | 30/мин | 🟡 |
| VK | VK API 5.199 | — | 20/мин | 🟢 |

## Маршрутизация публикации
`core/orchestrator.py::_publish_one` больше не содержит лестницу if-ов по площадкам:

```
NEXUS_PUBLISH_MODE=auto     коннектор настроен → API; отказ → браузер (причина сохраняется в api_note)
NEXUS_PUBLISH_MODE=api      только API, без браузерного фолбэка
NEXUS_PUBLISH_MODE=browser  всё через браузер (Telegram остаётся своим ботом)
```

## OAuth: подключение Instagram
Раньше токен добывался руками в Graph API Explorer. Теперь обычный OAuth:

1. Создать приложение на developers.facebook.com → `FACEBOOK_APP_ID`, `FACEBOOK_APP_SECRET`.
2. В настройках приложения указать redirect_uri: `<адрес сервиса>/api/social/oauth/callback`.
3. Дашборд → «Площадки» → «Подключить» → разрешить доступ.
4. Сервер сам меняет код на **long-lived токен (60 дней)**, находит Instagram Business
   аккаунт у Facebook-страниц и сохраняет `instagram_access_token` + `instagram_account_id`.

Callback (`/api/social/oauth/callback`) публичный — его вызывает Meta в браузере пользователя.

## Продление токенов — главная закрытая проблема
Токен Instagram умирал через ~60 дней **молча**, и система узнавала об этом только когда
падала публикация. Теперь:

- `health()` показывает срок и число оставшихся дней;
- `refresh_token()` меняет токен на долгоживущий;
- **джоб `tokens` в 08:00** (`scheduler.run_token_maintenance`) проверяет все площадки,
  продлевает всё, чему осталось меньше 14 дней, и пишет в Telegram, если продлить не вышло.

## Ограничения платформ (BLOCKED_BY_API)
Помечаются отдельным флагом и **не выдаются за ошибку кода** — см. `API_LIMITATIONS.md`:
- YouTube: загрузка видео только по OAuth2, API-ключа недостаточно;
- TikTok: видео-постинг не реализован; Research API закрыт;
- Instagram: Personal-аккаунты, Stories, часть insights — нужен App Review Meta.

## API
| Метод | Путь | Назначение |
|---|---|---|
| GET | `/api/social/health` | статус всех площадок |
| GET | `/api/social/health/{platform}` | статус одной |
| POST | `/api/social/refresh/{platform}` | продлить токен |
| GET | `/api/social/{platform}/profile` | профиль |
| POST | `/api/social/{platform}/posts` | последние посты |
| GET | `/api/social/oauth/start` | ссылка на подключение Instagram |
| GET | `/api/social/oauth/callback` | приём кода от Meta (публичный) |

Дашборд: страница **«Площадки»** — состояние токенов, права, предупреждения о протухании,
кнопки «Подключить» и «Продлить».

## Тесты (`tests/test_connectors.py`, 15 шт.)
Реестр покрывает 6 площадок · синглтон · единый контракт у всех · health без ключей не падает
и честно перечисляет недостающие · публикация без токена честна · YouTube/TikTok помечают
BLOCKED_BY_API · rate-limiter учитывает вызовы · оркестратор уходит в браузер без токенов ·
режим `api` не подключает браузер · API health/oauth · публичный callback.

## Осталось
- Webhooks (комментарии, упоминания) — нужен публичный HTTPS-эндпоинт и верификация.
- Работа с комментариями (`FunnelAgent` пока не подключён) — BLOCK 07.
- Видео-постинг TikTok.
