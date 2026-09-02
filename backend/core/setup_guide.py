"""
Чеклист готовности: что уже работает, что включится, если подключить ещё одно.

Зачем отдельный модуль, когда есть `/diag` и `preflight`: те отвечают на вопрос
«запустится ли прямо сейчас», списком галочек по ключам. Человеку же нужен
обратный разрез — по способностям: «умеет ли система публиковать сама»,
«может ли разобрать мой Instagram», «сделает ли видео». И, если не умеет, —
что именно подключить, где это взять и что оно включит.

Каждый пункт отвечает тремя вещами:
  status — ready (работает) / partial (работает, но хуже) / off (не работает);
  have   — на чём это уже держится;
  need   — чего не хватает: имя ключа, зачем он и где его получить.

Имена ключей здесь — те же, что в `core/credentials.py`, поэтому любую строку
из `need` можно тут же исполнить командой `/key <имя> <значение>` в Telegram.
"""
import os

READY, PARTIAL, OFF = "ready", "partial", "off"

ICON = {READY: "✅", PARTIAL: "🟡", OFF: "❌"}


def _env(name: str) -> str:
    return (os.getenv(name.upper(), "") or "").strip()


def _need(key: str, what: str, where: str) -> dict:
    return {"key": key, "what": what, "where": where}


async def _brain() -> dict:
    """Модели: без них нет ни темы, ни сценария, ни стратегии."""
    from core.ai_router import available_providers
    providers = available_providers()
    if providers:
        return {"status": READY, "have": [f"ИИ: {', '.join(providers)}"], "need": []}
    return {
        "status": OFF,
        "have": ["Заготовка по шаблону — без моделей тексты придётся дорабатывать"],
        "need": [
            _need("nvidia_api_key", "бесплатные открытые модели на GPU NVIDIA",
                  "build.nvidia.com/settings/api-keys — регистрация по email"),
            _need("groq_api_key", "самая быстрая бесплатная выдача",
                  "console.groq.com/keys"),
            _need("gemini_api_key", "дешёвые черновики и зрение",
                  "aistudio.google.com/apikey"),
        ],
    }


async def _control() -> dict:
    """Управление: бот и закреплённый владелец."""
    from core.telegram_owner import owner_id
    have, need = [], []
    if _env("telegram_bot_token"):
        have.append("Бот подключён")
    else:
        need.append(_need("telegram_bot_token", "управление и согласование в чате",
                          "@BotFather → /newbot"))
    if await owner_id():
        have.append("Владелец закреплён")
    elif _env("telegram_bot_token"):
        need.append(_need("—", "напишите боту /start — первый написавший станет владельцем",
                          "в чате с ботом"))
    return {"status": READY if len(have) == 2 else (PARTIAL if have else OFF),
            "have": have, "need": need}


async def _publishing() -> dict:
    """Куда система умеет выкладывать готовое."""
    from core.telegram_channels import list_channels
    have, need = [], []

    try:
        if await list_channels() or _env("telegram_post_chat_id"):
            have.append("Telegram-канал")
    except Exception:
        pass
    if _env("instagram_access_token"):
        have.append("Instagram")
    else:
        need.append(_need("instagram_access_token", "публикация в Instagram по API",
                          "Подключения → Instagram, вход через Instagram Login (токен IGAA…)"))
    if _env("vk_access_token"):
        have.append("ВКонтакте")
    else:
        need.append(_need("vk_access_token", "публикация во ВКонтакте",
                          "vk.com/dev → ключ доступа сообщества"))
    if _env("threads_access_token"):
        have.append("Threads")
    if _env("tiktok_access_token"):
        have.append("TikTok")

    if not have:
        need.insert(0, _need("telegram_post_chat_id",
                             "самый быстрый способ начать выкладывать — свой канал",
                             "добавьте бота в канал администратором, затем /channels"))
    return {"status": READY if have else OFF, "have": have, "need": need}


async def _autopublish() -> dict:
    """Выходит ли контент сам, без нажатия кнопки."""
    from core.autopublish import get_settings, AUTO
    pub = await _publishing()
    settings = await get_settings()
    modes = settings.get("platforms") or {}
    auto_on = [p for p, m in modes.items() if m == AUTO]

    if not pub["have"]:
        return {"status": OFF,
                "have": [],
                "need": [_need("—", "сначала нужна хотя бы одна площадка (см. «Публикация»)",
                               "/setup")]}
    if not settings.get("enabled"):
        return {"status": OFF,
                "have": ["Площадки есть, расписание работает"],
                "need": [_need("—", "автопубликация выключена общим рубильником",
                               "включить: /autopub on")]}
    if not auto_on:
        return {"status": PARTIAL,
                "have": ["Контент готовится и встаёт на подтверждение (/approve)"],
                "need": [_need("—", "ни одна площадка не в режиме auto",
                               "например: /autopub telegram auto")]}
    return {"status": READY, "have": [f"Сами публикуем: {', '.join(auto_on)}"], "need": []}


async def _analysis() -> dict:
    """Разбор своих аккаунтов — из него строится стратегия."""
    have, need = [], []
    if _env("youtube_handle"):
        have.append("YouTube (бесплатно, через yt-dlp)")
    if _env("tiktok_handle"):
        have.append("TikTok")
    if _env("ig_handle"):
        have.append("Instagram")
    if not have:
        need.append(_need("ig_handle", "чей аккаунт разбирать — без этого анализ не с чего начать",
                          "просто ник без @"))
    if _env("ig_handle") and not (_env("instagram_access_token") or _env("nexus_browser_cdp")):
        need.append(_need("instagram_access_token",
                          "чтение своих метрик Instagram (иначе только публичные данные)",
                          "Подключения → Instagram"))
    if not _env("perplexity_api_key"):
        need.append(_need("perplexity_api_key", "свежие тренды и факты со ссылками",
                          "perplexity.ai/settings/api"))
    return {"status": READY if have else OFF, "have": have, "need": need}


async def _media() -> dict:
    """Фото, видео, озвучка."""
    have = ["Изображения: бесплатный генератор (без ключа)"]
    need = []
    video = [k for k in ("HEYGEN_API_KEY", "HIGGSFIELD_API_KEY", "RUNWAY_API_KEY")
             if _env(k)]
    if video:
        have.append("Видео: " + ", ".join(k.split("_")[0].title() for k in video))
    else:
        need.append(_need("higgsfield_api_key", "кинематографичные ролики вместо слайд-шоу",
                          "higgsfield.ai → API"))
        need.append(_need("heygen_api_key", "говорящий аватар в кадре",
                          "app.heygen.com → Settings → API"))
    if _env("elevenlabs_api_key"):
        have.append("Озвучка: ElevenLabs")
    else:
        need.append(_need("elevenlabs_api_key", "живая озвучка вместо субтитров",
                          "elevenlabs.io → Profile → API Key"))
    return {"status": READY if video else PARTIAL, "have": have, "need": need}


async def _storage() -> dict:
    """Переживёт ли всё это перезапуск."""
    from database.db import storage_info
    st = storage_info()
    have, need = [], []
    # Обе переменные читаются один раз при старте процесса (движок базы и ключ
    # шифрования), поэтому через /key их задать нельзя — только в окружении.
    # Обещать обратное было бы советом, который не исполняется.
    if st["persistent"]:
        have.append("Постоянная база (Postgres)")
    else:
        need.append(_need("—",
                          "DATABASE_URL — без неё при каждом деплое стираются "
                          "ключи, память и проекты",
                          "supabase.com → новый проект → Connection string → "
                          "Render → Environment (не через /key: читается при старте)"))
    if _env("nexus_secret_key"):
        have.append("Ключи площадок шифруются")
    else:
        need.append(_need("—",
                          "NEXUS_SECRET_KEY — иначе токены лежат в базе открытым текстом",
                          "любая длинная строка в Render → Environment; не терять её"))
    return {"status": READY if not need else (PARTIAL if have else OFF),
            "have": have, "need": need}


SECTIONS = (
    ("brain", "Мозг: тексты, анализ, стратегия", _brain),
    ("control", "Управление в Telegram", _control),
    ("publishing", "Публикация", _publishing),
    ("autopublish", "Автопубликация", _autopublish),
    ("analysis", "Анализ аккаунтов", _analysis),
    ("media", "Фото, видео, озвучка", _media),
    ("storage", "Хранилище и защита ключей", _storage),
)


async def report() -> dict:
    """Полный чеклист. Ошибка одной секции не должна ронять весь отчёт —
    иначе человек вместо ответа получает трассировку."""
    sections = []
    for key, title, fn in SECTIONS:
        try:
            data = await fn()
        except Exception as e:
            data = {"status": OFF, "have": [],
                    "need": [_need("—", f"проверка не отработала: {type(e).__name__}", "")]}
        sections.append({"key": key, "title": title, **data})
    ready = sum(1 for s in sections if s["status"] == READY)
    return {"sections": sections, "ready": ready, "total": len(sections)}


def as_text(rep: dict) -> str:
    """Чеклист словами — для чата."""
    lines = [f"🧩 <b>Что работает</b> — {rep['ready']} из {rep['total']} готово", ""]
    for s in rep["sections"]:
        lines.append(f"{ICON[s['status']]} <b>{s['title']}</b>")
        for h in s["have"]:
            lines.append(f"   • {h}")
        for n in s["need"]:
            key = n["key"]
            head = f"   ↳ <code>{key}</code> — " if key != "—" else "   ↳ "
            lines.append(head + n["what"])
            if n["where"]:
                lines.append(f"      <i>{n['where']}</i>")
        lines.append("")
    lines.append("Подключить ключ прямо здесь: <code>/key имя значение</code>")
    lines.append("Например: <code>/key groq_api_key gsk_...</code>")
    return "\n".join(lines)
