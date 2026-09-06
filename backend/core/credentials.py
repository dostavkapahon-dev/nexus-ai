"""
Единая работа с доступами: чтение, запись, удаление, выгрузка в окружение.

До этого модуля правила хранения были размазаны: список полей жил в
`api/routes_settings.py` и дублировался на трёх страницах веба, чтение ключей —
в lifespan `main.py`, а расшифровки не было вовсе. Здесь одна точка правды:

  * `FIELDS`         — какие доступы вообще бывают, к какой группе относятся;
  * `get/set/delete` — работа со значением с учётом шифрования;
  * `load_into_env`  — выгрузка в `os.environ` на старте, чтобы весь остальной код
                       продолжал работать через привычный `os.getenv("...")`.

Группы нужны интерфейсу (ТЗ: отдельная карточка на каждое подключение), а не
логике: по ним раздел «API / Подключения» собирается сам, без списка полей,
захардкоженного в React.
"""
import os
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select

from core import secrets
from database.db import AsyncSessionLocal
from database.models import Connection


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    group: str
    secret: bool = True
    hint: str = ""


# Группы подключений — ровно те, что просит ТЗ в разделе «API / CONNECTIONS».
GROUPS = {
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "telegram": "Telegram",
    "google": "Google",
    "ai": "AI-сервисы",
    "storage": "Хранилище",
    "other": "Другие интеграции",
}

FIELDS: tuple[Field, ...] = (
    # AI
    Field("anthropic_api_key", "Anthropic Claude", "ai"),
    Field("openai_api_key", "OpenAI", "ai"),
    Field("gemini_api_key", "Google Gemini", "ai"),
    Field("perplexity_api_key", "Perplexity (поиск в интернете)", "ai"),
    Field("deepseek_api_key", "DeepSeek", "ai"),
    Field("groq_api_key", "Groq", "ai"),
    Field("cerebras_api_key", "Cerebras", "ai"),
    Field("openrouter_api_key", "OpenRouter", "ai"),
    Field("mistral_api_key", "Mistral", "ai"),
    Field("nvidia_api_key", "NVIDIA NIM", "ai"),
    Field("github_models_token", "GitHub Models", "ai"),
    Field("heygen_api_key", "HeyGen (аватары)", "ai"),
    Field("heygen_avatar_id", "HeyGen: id аватара", "ai", secret=False),
    Field("heygen_voice_id", "HeyGen: id голоса", "ai", secret=False),
    Field("higgsfield_api_key", "HiggsField: ключ", "ai",
          hint="Пара ключ+секрет из cloud.higgsfield.ai. Без секрета запрос отклоняется."),
    Field("higgsfield_secret", "HiggsField: секрет", "ai",
          hint="Вторая половина пары. Показывается один раз при создании ключа."),
    Field("higgsfield_model", "HiggsField: модель по умолчанию", "ai", secret=False,
          hint="Пусто — HIXIIT подбирает модель под задачу сам."),
    Field("runway_api_key", "Runway", "ai"),
    Field("elevenlabs_api_key", "ElevenLabs (озвучка)", "ai"),
    # Telegram
    Field("telegram_bot_token", "Токен бота", "telegram"),
    Field("telegram_chat_id", "Чат для уведомлений", "telegram", secret=False),
    Field("telegram_post_chat_id", "Канал для публикаций", "telegram", secret=False),
    # Instagram
    Field("instagram_access_token", "Access Token", "instagram"),
    Field("instagram_account_id", "Account ID", "instagram", secret=False),
    Field("instagram_app_secret", "App Secret", "instagram"),
    Field("instagram_verify_token", "Verify Token (вебхуки)", "instagram"),
    Field("facebook_app_id", "Facebook App ID", "instagram", secret=False),
    Field("facebook_app_secret", "Facebook App Secret", "instagram"),
    Field("ig_handle", "Имя аккаунта", "instagram", secret=False),
    # TikTok
    Field("tiktok_access_token", "Access Token", "tiktok"),
    Field("tiktok_handle", "Имя аккаунта", "tiktok", secret=False),
    # Google
    Field("google_service_account_json", "Service Account JSON", "google"),
    Field("youtube_api_key", "YouTube Data API", "google"),
    Field("youtube_handle", "Канал YouTube", "google", secret=False),
    # Другие площадки
    Field("vk_access_token", "ВКонтакте: токен", "other"),
    Field("vk_group_id", "ВКонтакте: ID сообщества", "other", secret=False),
    Field("threads_access_token", "Threads: токен", "other"),
    Field("threads_user_id", "Threads: user id", "other", secret=False),
    Field("brightdata_api_key", "Bright Data", "other"),
    # Хранилище и системное
    Field("nexus_browser_storage_state", "Cookies браузера", "storage"),
    Field("nexus_browser_cdp", "Облачный браузер (CDP)", "storage", secret=False),
    Field("nexus_publish_mode", "Режим публикации", "storage", secret=False),
    Field("nexus_public_url", "Публичный адрес сервиса", "storage", secret=False),
    Field("nexus_token", "Токен доступа к API", "storage"),
)

BY_KEY = {f.key: f for f in FIELDS}


def schema() -> list[dict]:
    """Описание всех полей — интерфейс строится по нему, а не по своему списку."""
    return [{"key": f.key, "label": f.label, "group": f.group,
             "group_label": GROUPS.get(f.group, f.group),
             "secret": f.secret, "hint": f.hint} for f in FIELDS]


# ─────────────────────────── чтение и запись ───────────────────────────

async def get(key_name: str) -> str | None:
    """Значение доступа. None — записи нет либо её нечем расшифровать."""
    key_name = (key_name or "").strip().lower()
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Connection).where(Connection.key_name == key_name))
        conn = r.scalar_one_or_none()
    if conn and conn.key_value:
        return secrets.decrypt(conn.key_value)
    return os.getenv(key_name.upper()) or None


async def set(key_name: str, value: str) -> dict:
    """Сохраняет доступ (шифруя, если задан NEXUS_SECRET_KEY) и сразу делает его
    видимым для кода, который читает `os.getenv`."""
    key_name = (key_name or "").strip().lower()
    value = (value or "").strip()
    if not value:
        return {"ok": False, "error": "пустое значение"}

    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Connection).where(Connection.key_name == key_name))
        conn = r.scalar_one_or_none()
        stored = secrets.encrypt(value)
        if conn:
            conn.key_value = stored
        else:
            db.add(Connection(key_name=key_name, key_value=stored))
        await db.commit()
    os.environ[key_name.upper()] = value
    return {"ok": True, "encrypted": secrets.is_encrypted(stored)}


async def delete(key_name: str) -> dict:
    key_name = (key_name or "").strip().lower()
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Connection).where(Connection.key_name == key_name))
        conn = r.scalar_one_or_none()
        if conn:
            await db.delete(conn)
            await db.commit()
    from_env = os.environ.pop(key_name.upper(), None)
    if not conn and from_env is None:
        return {"ok": False, "error": "ключ не найден"}
    return {"ok": True, "was_in_env": from_env is not None and not conn}


async def record_check(key_name: str, ok: bool, error: str = ""):
    """Запоминает результат проверки связи — его показывает страница подключений."""
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Connection).where(Connection.key_name == key_name))
        conn = r.scalar_one_or_none()
        if not conn:
            return
        conn.last_check_at = datetime.utcnow()
        conn.last_check_ok = bool(ok)
        conn.last_check_error = (error or "")[:300] or None
        await db.commit()


# ─────────────────────────── старт приложения ───────────────────────────

# Таблица `connections` служит и хранилищем доступов, и KV-складом внутреннего
# состояния: лента Командного центра, история диалога, состояние автопилота,
# выбранные модели. Всё это — не ключи, и в переменные окружения ему не место:
# оно туда не читается никем, зато раздувает окружение и подделывается под
# конфликт настроек (лента меняется каждую минуту, и её новое значение выглядит
# как «ключ задан в двух местах»).
CREDENTIAL_SUFFIXES = ("_api_key", "_key", "_token", "_secret", "_id", "_json",
                       "_state", "_url", "_mode")


def is_credential(key_name: str) -> bool:
    """Доступ это или внутреннее состояние.

    Известные поля — по списку. Незнакомое имя считаем доступом только если оно
    похоже на доступ по окончанию: пропустить чужой ключ хуже, чем вынести в
    окружение лишнюю строку.
    """
    key = (key_name or "").strip().lower()
    if key in BY_KEY:
        return True
    if key in INTERNAL_STATE:
        return False
    return key.endswith(CREDENTIAL_SUFFIXES)


# Внутреннее состояние, которое заведомо не доступ. Список нужен для имён,
# попадающих под общее правило окончаний (например, `*_state`).
INTERNAL_STATE = {
    "control_feed",             # лента Командного центра
    "autopilot_state",          # состояние автопилота
    "nexus_last_auto_report",   # отметка о последнем отчёте
}

# Итог последней загрузки доступов. Нужен не для красоты: перекрытие переменной
# хостинга значением из дашборда — самая частая причина «ключ вписан, а ничего
# не работает», и увидеть её человек должен в Telegram, а не в логах Render.
LAST_LOAD: dict = {"loaded": 0, "unreadable": 0, "encrypted_now": 0, "shadowed": []}

# Что в окружение положили мы сами. Загрузка вызывается не только на старте, и
# без этой памяти обновлённое в дашборде значение сравнивалось бы с прошлым
# нашим же — то есть каждая правка ключа выглядела бы как конфликт с хостингом.
_EXPORTED: dict = {}

async def load_into_env() -> dict:
    """Выгружает сохранённые доступы в окружение процесса.

    Весь код читает ключи через `os.getenv`, поэтому это — единственный мостик
    между базой и остальной системой. Заодно, если шифрование только что
    включили, старые записи дошифровываются: иначе они так и остались бы лежать
    открытым текстом, а пользователь считал бы, что защитил их.
    """
    loaded = unreadable = re_encrypted = 0
    shadowed: list[str] = []
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Connection))
        rows = list(r.scalars())
        for conn in rows:
            raw = conn.key_value or ""
            if not raw:
                continue
            value = secrets.decrypt(raw)
            if value is None:
                # Зашифровано, а ключа нет: молча подставлять пустоту нельзя —
                # получится «ключ подключён, но ничего не работает».
                unreadable += 1
                print(f"[NEXUS] доступ {conn.key_name} зашифрован, но NEXUS_SECRET_KEY "
                      f"не задан или не тот — значение недоступно", flush=True)
                continue
            if not is_credential(conn.key_name):
                continue                # внутреннее состояние — не в окружение
            env_name = conn.key_name.upper()
            # Значение из дашборда перекрывает переменную хостинга. Само по себе
            # это правильно — человек редактирует именно в дашборде. Но молчать
            # об этом нельзя: положив новый ключ в Render поверх старого,
            # сохранённого на сайте, человек не увидит никакого эффекта и будет
            # искать поломку там, где её нет.
            previous = os.environ.get(env_name)
            if (previous and previous != value
                    and _EXPORTED.get(env_name) != previous):
                shadowed.append(env_name)
            os.environ[env_name] = value
            _EXPORTED[env_name] = value
            loaded += 1
            if secrets.enabled() and not secrets.is_encrypted(raw):
                conn.key_value = secrets.encrypt(value)
                re_encrypted += 1
        if re_encrypted:
            await db.commit()
    if re_encrypted:
        print(f"[NEXUS] зашифровано сохранённых доступов: {re_encrypted}", flush=True)
    if shadowed:
        print(f"[NEXUS] заданы и в дашборде, и в переменных хостинга — "
              f"используется дашборд: {', '.join(shadowed)}", flush=True)
    result = {"loaded": loaded, "unreadable": unreadable,
              "encrypted_now": re_encrypted, "shadowed": shadowed}
    LAST_LOAD.update(result)
    return result


async def overview() -> dict:
    """Состояние хранилища доступов для интерфейса."""
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Connection))
        rows = list(r.scalars())
    return {**secrets.status([c.key_value or "" for c in rows]), "total": len(rows)}
