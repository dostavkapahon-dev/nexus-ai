"""
Понимание свободного текста: пишешь обычными словами — агент сам решает, что делать.

Сначала быстрые правила без LLM (ссылки, явные слова) — это бесплатно и мгновенно.
Если не распознали — дешёвая модель определяет намерение.

Возвращает команду вида "/viral <url>" или "/factory тема", которую бот выполняет.
"""
import re

URL_RE = re.compile(r"https?://\S+")

VIDEO_HOSTS = ("instagram.com", "tiktok.com", "youtube.com", "youtu.be", "vk.com")

# Быстрые правила: слово в тексте → команда (без вызова модели).
RULES = [
    (("проанализируй аккаунт", "разбери аккаунт", "анализ аккаунта",
      "что с моим инстаграм", "статистика аккаунта"), "/strategy"),
    (("автопилот", "полный цикл", "начни с нуля", "с чего начать"), "/auto"),
    (("план на неделю", "контент план", "что постить"), "/plan7"),
    (("тренды", "что сейчас популярно", "что залетает"), "/trend"),
    (("статус", "как дела у системы", "что работает"), "/diag"),
    (("опубликуй", "публикуй очередь"), "/publish"),
    (("пауза", "останови"), "/pause"),
    (("продолжи", "возобнови"), "/resume"),
]

INTENT_SYSTEM = (
    "Ты — маршрутизатор команд для SMM-агента. По сообщению пользователя определи, "
    "что он хочет, и верни ОДНУ команду из списка. Отвечай ТОЛЬКО командой, без пояснений.\n"
    "/auto — полный цикл: анализ, стратегия, ролик\n"
    "/strategy — разбор аккаунта и варианты стратегии\n"
    "/factory <тема> — создать ролик на тему\n"
    "/predict <идея> — оценить шанс залёта идеи\n"
    "/plan7 — контент-план на неделю\n"
    "/hunt <ниша> — найти залетевшие ролики\n"
    "/trend — тренды сейчас\n"
    "/diag — что подключено\n"
    "/do <задача> — сделать что-то в браузере на ПК\n"
    "/chat — просто ответить текстом, если это вопрос или разговор"
)


def quick_route(text: str) -> str | None:
    """Мгновенная маршрутизация без LLM. None — если не уверены."""
    t = (text or "").strip()
    low = t.lower()

    # Ссылка на видео → разбор референса; прочие ссылки → зрение.
    urls = URL_RE.findall(t)
    if urls:
        u = urls[0]
        if any(h in u for h in VIDEO_HOSTS):
            return f"/viral {' '.join(urls[:5])}"
        return f"/see {u}"

    for words, cmd in RULES:
        if any(w in low for w in words):
            return cmd

    # «Сделай ролик про X» / «нужен рилс о X» → фабрика с темой
    m = re.search(r"(?:сделай|создай|сгенерируй|нужен|хочу)\s+(?:рилс\w*|reels|ролик|видео)\s*(?:про|о|об)?\s*(.*)",
                  t, re.IGNORECASE)
    if m:
        topic = m.group(1).strip(" .!?")  # регистр исходного текста сохраняем
        return f"/factory {topic}" if topic else "/factory"
    return None


async def route(text: str) -> str:
    """Определяет команду для свободного текста (правила → дешёвая модель)."""
    quick = quick_route(text)
    if quick:
        return quick
    try:
        from core.ai_router import ai_router, ECONOMY_MODELS
        model = ECONOMY_MODELS.get("adapter", "gemini-2.0-flash")
        res = await ai_router.call(model, INTENT_SYSTEM, text[:800])
        out = (res.get("text") or "").strip().split("\n")[0].strip()
        if out.startswith("/"):
            return out
    except Exception:
        pass
    return "/chat"


CHAT_SYSTEM = (
    "Ты — ассистент SMM-агента NEXUS AI. Отвечай кратко, по-русски, по делу. "
    "Если у тебя спрашивают, что ты умеешь — расскажи: анализ аккаунта, поиск трендов, "
    "разбор чужих роликов, создание Reels, монтаж, публикация, управление браузером на ПК."
)


async def chat_reply(text: str) -> str:
    """Свободный ответ, когда это просто вопрос/разговор."""
    try:
        from core.ai_router import ai_router, ECONOMY_MODELS
        model = ECONOMY_MODELS.get("copywriter", "gemini-2.0-flash")
        res = await ai_router.call(model, CHAT_SYSTEM, text[:1500])
        return (res.get("text") or "").strip()[:3000]
    except Exception as e:
        return f"⚠️ Не смог ответить: {str(e)[:150]}"
