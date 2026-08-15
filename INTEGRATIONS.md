# INTEGRATIONS — внешние сервисы

## AI-провайдеры
См. `AI_PROVIDERS.md` (6 бесплатных + 5 платных).

## Соцсети
См. `SOCIAL_CONNECTORS.md` (Instagram, Threads, TikTok, YouTube, VK, Telegram).

## Генерация медиа

| Сервис | Модуль | Переменные | Назначение | Статус |
|---|---|---|---|---|
| Pollinations | `core/media_generator.py:62` | — (бесплатно) | изображения, раскадровка | 🟢 |
| Google Imagen | `media_generator.py:36` | `GEMINI_API_KEY`, `IMAGEN_MODEL` | изображения | 🟢 |
| DALL·E 3 | `media_generator.py:67` | `OPENAI_API_KEY` | изображения | 🟢 |
| Stability | `media_generator.py:84` | `STABILITY_API_KEY` | изображения | 🟢 |
| HeyGen | `core/heygen.py` | `HEYGEN_API_KEY`, `HEYGEN_AVATAR_ID`, `HEYGEN_VOICE_ID` | видео-аватар с озвучкой | 🟢 |
| HiggsField | `core/higgsfield.py` | `HIGGSFIELD_API_KEY`, `HIGGSFIELD_SECRET`, `HIGGSFIELD_MODEL` | кинематографичные клипы | 🟢 |
| Runway | `media_generator.py:123` | `RUNWAY_API_KEY` | видео gen3a_turbo | 🟢 |
| ElevenLabs | `media_generator.py:103` | `ELEVENLABS_API_KEY` | озвучка | 🟢 |

## Инфраструктурные

| Сервис | Модуль | Переменные | Назначение |
|---|---|---|---|
| Telegram Bot API | `core/telegram_bot.py` | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_POST_CHAT_ID` | управление и публикация |
| Google Drive | `core/google_drive.py` | `GOOGLE_SERVICE_ACCOUNT_JSON`, `GOOGLE_DRIVE_FOLDER_ID` | кэш анализа ниш |
| Google Sign-In | `api/routes_auth.py` | `GOOGLE_CLIENT_ID` | вход в дашборд |
| Bright Data | `core/social_intel.py:139` | `BRIGHTDATA_API_KEY`, `BRIGHTDATA_ZONE` | Web Unlocker для Instagram |
| Bright Data Scraping Browser | `core/server_browser.py` | `NEXUS_BROWSER_CDP` | удалённый браузер (разгрузка Render) |
| DuckDuckGo | `core/duckduckgo.py` | — | поиск трендов без ключа |
| yt-dlp | `core/viral_research.py` | — | метрики роликов YouTube/TikTok |
| Playwright | `core/server_browser.py` | `NEXUS_SERVER_BROWSER`, `NEXUS_BROWSER_PROFILE` | браузер на сервере |
| Desktop Agent | `desktop_agent.py` + `api/routes_desktop.py` | `NEXUS_TOKEN` | браузер на ПК пользователя (WebSocket) |
| ffmpeg | `imageio-ffmpeg` | — | монтаж, субтитры |

## Хранение доступов

Ключи площадок и AI лежат в таблице `connections`. `core/secrets.py` шифрует
значения ключом из `NEXUS_SECRET_KEY` (Fernet), `core/credentials.py` — единая
точка чтения/записи и выгрузки в окружение процесса.

| Переменная | Смысл |
|---|---|
| `NEXUS_SECRET_KEY` | ключ шифрования. Не задан — ключи хранятся открытым текстом (интерфейс об этом предупреждает). Появился — сохранённые записи дошифровываются при старте. Потерян — зашифрованные значения прочитать нельзя, их нужно ввести заново |

Весь остальной код читает доступы через `os.getenv`: расшифровка происходит один
раз на старте (`main.py` → `credentials.load_into_env`) и при сохранении ключа.

## Режимы работы

| Переменная | Значения | Смысл |
|---|---|---|
| `NEXUS_PUBLISH_MODE` | auto / browser / api | как публиковать |
| `NEXUS_ANALYZE_MODE` | auto / browser / api | как анализировать |
| `NEXUS_SERVER_BROWSER` | 1 / 0 | серверный браузер вкл/выкл |
| `AUTO_PUBLISH` | 1 / 0 | автопубликация дневной фабрики |
| `NEXUS_TZ` | Asia/Almaty | таймзона планировщика |

## Безопасность интеграций
- SSRF-guard: `core/server_browser.py::url_allowed` — браузер не откроет loopback,
  приватные подсети и хосты облачных метаданных.
- Санитизация ников: `browser_reader.py`, `instagram_reader.analyze_competitor`.
- 🟡 Секреты хранятся plaintext (см. `MEMORY_SYSTEM.md`).
