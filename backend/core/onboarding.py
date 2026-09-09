"""
Онбординг: с чего начать, чтобы система заработала.

Проблема была не в отсутствии функций, а в отсутствии порядка. `/start` открывал
сетку кнопок, и владелец не знал, что нажать первым: ниша не задана, ключа ИИ
нет, публиковать некуда — но узнать это можно было, только напоровшись на отказ
где-то в середине работы.

Здесь один вопрос — что осталось настроить — и ответ по фактическому состоянию,
а не по списку «желательного». Правила:

  * шаг считается сделанным только если это подтверждается данными, а не
    намерением: ключ в окружении, запись в профиле, сохранённый канал;
  * шаги упорядочены по тому, что раньше сломает работу: без модели ИИ нет
    ничего, без канала некуда публиковать, без ниши контент будет «вообще»;
  * сюда не ходит сеть. Настроенность и работоспособность — разные вопросы:
    второй проверяет `/system_test`, и онбординг честно на него ссылается.
"""
import os

# Шаг с этим ключом обязателен: пока он не сделан, система не даст результата.
REQUIRED = ("ai", "publish")


async def _step_ai() -> dict:
    from core.ai_router import available_providers
    providers = available_providers()
    return {
        "key": "ai", "title": "Модель ИИ",
        "done": bool(providers),
        "detail": ", ".join(providers) if providers else "ни одного ключа",
        "how": "Бесплатный ключ: console.groq.com/keys или ai.google.dev. "
               "Положить в Подключения или в переменные хостинга.",
        "why": "Без модели нет ни темы, ни сценария, ни текста.",
    }


async def _step_publish() -> dict:
    """Куда уйдёт готовый пост. Без этого работа упрётся в последний шаг."""
    chat = (os.getenv("TELEGRAM_POST_CHAT_ID") or "").strip()
    connected = []
    try:
        from connectors import get_connector
        for name in ("instagram", "tiktok", "vk", "youtube"):
            conn = get_connector(name)
            if conn and conn.configured():
                connected.append(name)
    except Exception:
        pass
    where = ([f"Telegram-канал {chat}"] if chat else []) + connected
    return {
        "key": "publish", "title": "Куда публиковать",
        "done": bool(where),
        "detail": ", ".join(where) if where else "не задано ни одной площадки",
        "how": "Добавить бота в канал администратором и выполнить /channels.",
        "why": "Иначе готовый пост некуда отправить — работа встанет на последнем шаге.",
    }


async def _step_profile() -> dict:
    from core import agent_profile
    prof = await agent_profile.get()
    filled = [f for f in ("niche", "audience", "goals") if str(prof.get(f) or "").strip()]
    return {
        "key": "profile", "title": "Ниша и аудитория",
        "done": bool(prof.get("niche")),
        "detail": (f"{prof.get('niche')} (заполнено: {len(filled)} из 3)"
                   if prof.get("niche") else "не заданы"),
        "how": "Пройти интервью: /auto — оно же соберёт стратегию и контент-план.",
        "why": "Без ниши контент получится «вообще про всё» и не зацепит аудиторию.",
    }


async def _step_accounts() -> dict:
    """Свои аккаунты — чтобы учиться на собственных результатах, а не вслепую."""
    handles = {k: os.getenv(k, "").strip()
               for k in ("IG_HANDLE", "TIKTOK_HANDLE", "YOUTUBE_HANDLE")}
    have = [v for v in handles.values() if v]
    return {
        "key": "accounts", "title": "Аккаунты для анализа",
        "done": bool(have),
        "detail": ", ".join(have) if have else "не указаны",
        "how": "Указать ники в Подключениях: IG_HANDLE, TIKTOK_HANDLE, YOUTUBE_HANDLE.",
        "why": "По ним система разбирает, что у вас уже заходит, и учится на этом.",
    }


async def _step_media() -> dict:
    from core.hixiit import mcp_configured
    from core.higgsfield import credentials
    if mcp_configured():
        detail, done = "Higgsfield через MCP", True
    elif credentials():
        detail, done = "Higgsfield по ключу и секрету", True
    else:
        detail, done = "только бесплатные картинки", False
    return {
        "key": "media", "title": "Генерация видео и картинок",
        "done": done, "detail": detail,
        "how": "HIGGSFIELD_MCP_URL и HIGGSFIELD_MCP_TOKEN — тогда работает "
               "безлимит подписки, а не поштучные кредиты.",
        "why": "Без этого вместо ролика соберётся слайд-шоу из бесплатных картинок.",
    }


async def _step_storage() -> dict:
    from database.db import storage_info
    store = storage_info()
    return {
        "key": "storage", "title": "Постоянная память",
        "done": bool(store.get("persistent")),
        "detail": "постоянное хранилище" if store.get("persistent")
                  else "данные исчезнут при перезапуске",
        "how": "Задать DATABASE_URL с Postgres в переменных хостинга.",
        "why": "Иначе ниша, ключи и очередь стираются при каждом деплое.",
    }


STEPS = (_step_ai, _step_publish, _step_profile,
         _step_accounts, _step_media, _step_storage)


async def state() -> dict:
    """Состояние настройки: что сделано, что осталось и что делать следующим."""
    steps = []
    for fn in STEPS:
        try:
            steps.append(await fn())
        except Exception as e:
            # Сломавшаяся проверка не должна выдавать шаг за сделанный:
            # непроверенное — не настроенное.
            steps.append({"key": getattr(fn, "__name__", "?"), "title": "Проверка",
                          "done": False, "detail": f"{type(e).__name__}: {str(e)[:80]}",
                          "how": "", "why": ""})

    left = [s for s in steps if not s["done"]]
    blocking = [s for s in left if s["key"] in REQUIRED]
    return {
        "ready": not blocking,
        "complete": not left,
        "done": len([s for s in steps if s["done"]]),
        "total": len(steps),
        "steps": steps,
        "next": (blocking or left or [None])[0],
    }


def as_text(st: dict) -> str:
    """Чек-лист для Telegram: сначала что делать сейчас, потом весь список."""
    if st.get("complete"):
        head = "✅ <b>Всё настроено</b>"
    elif st.get("ready"):
        head = (f"🟢 <b>Готово к работе</b> — {st['done']} из {st['total']}. "
                "Остальное улучшит результат, но не обязательно.")
    else:
        head = (f"⚙️ <b>Настройка</b> — {st['done']} из {st['total']}. "
                "Без отмеченного ниже система не даст результата.")

    lines = [head]
    nxt = st.get("next")
    if nxt:
        lines += ["", f"<b>Сейчас: {nxt['title']}</b>", nxt.get("why", ""),
                  f"→ {nxt.get('how', '')}"]

    lines.append("")
    for s in st.get("steps", []):
        lines.append(f"{'✅' if s['done'] else '⬜'} {s['title']} — {s['detail']}")

    lines.append("\nПроверить, что это <i>работает</i>, а не просто настроено — "
                 "<code>/system_test</code>")
    return "\n".join(x for x in lines if x is not None)
