"""
Подключение Telegram-каналов для постинга: бот → канал → права → тест.

Зачем отдельный модуль. Раньше канал задавался переменной окружения
TELEGRAM_POST_CHAT_ID: пользователь вписывал строку и узнавал о том, что бот
не админ или не может писать, только когда терялся первый настоящий пост.
Здесь подключение проходит по шагам, и каждый шаг отвечает на свой вопрос:

  1. `bot_info`        — жив ли токен и что это за бот;
  2. `discover`        — какие каналы бот уже видит (по свежим апдейтам);
  3. `check_channel`   — админ ли бот в канале и есть ли право публиковать;
  4. `test_publish`    — реально ли уходит сообщение (тестовое удаляется);
  5. `add_channel`     — сохранение канала в список подключённых.

Список каналов лежит в таблице Connection (ключ `telegram_channels`, JSON) —
так же, как другие настройки системы, без миграций схемы.
"""
import json
import os
import time

from sqlalchemy import select

from core import kv
from database.db import AsyncSessionLocal
from database.models import Connection
from publishers import telegram_pub as tg

CHANNELS_KEY = "telegram_channels"

# Каналы, которые бот увидел в своих обновлениях. Заполняется циклом бота
# (core/telegram_bot.poll_updates), читается мастером подключения.
_seen_chats: dict[str, dict] = {}
# Право писать в канал; в супергруппе роль админа устроена иначе — там смотрим
# на сам факт членства со статусом administrator/creator.
POST_RIGHT = "can_post_messages"


# ─────────────────────────── хранилище ───────────────────────────

async def list_channels() -> list[dict]:
    items = await kv.get(CHANNELS_KEY, [])
    return items if isinstance(items, list) else []


async def default_channel() -> str:
    """chat_id канала по умолчанию: помеченный default, иначе первый подключённый,
    иначе — старые переменные окружения (совместимость с прежними установками)."""
    items = await list_channels()
    for it in items:
        if it.get("default"):
            return str(it.get("chat_id") or "")
    if items:
        return str(items[0].get("chat_id") or "")
    return (os.getenv("TELEGRAM_POST_CHAT_ID", "") or os.getenv("TELEGRAM_CHAT_ID", "")).strip()


# ─────────────────────────── шаги подключения ───────────────────────────

async def bot_info(token: str = "") -> dict:
    """Шаг 1: подключение бота. Токен можно проверить до сохранения."""
    res = await tg.call("getMe", {}, token=token)
    if not res.get("ok"):
        return {"ok": False, "error": res.get("error") or "токен не принят Telegram"}
    me = res.get("result") or {}
    return {"ok": True, "id": me.get("id"), "username": "@" + (me.get("username") or ""),
            "name": me.get("first_name") or "", "can_join_groups": me.get("can_join_groups"),
            "saved": bool(tg.bot_token())}


def remember_chat(chat: dict):
    """Запомнить канал, который бот увидел в обновлениях.

    Вызывается из цикла бота. Своего `getUpdates` мастер больше не делает:
    Telegram допускает только одно активное соединение на токен, и запрос из
    веба отбирал его у бота — тот получал 409 и замолкал, а мастер видел пустой
    список и объяснял это тем, что бота «нет в канале».
    """
    chat_id = str(chat.get("id") or "")
    if not chat_id:
        return
    _seen_chats[chat_id] = {
        "chat_id": chat_id, "title": chat.get("title") or "",
        "username": ("@" + chat["username"]) if chat.get("username") else "",
        "type": chat.get("type") or ""}


async def discover(token: str = "") -> dict:
    """Шаг 2: выбор канала — из того, что бот уже видел.

    Telegram не отдаёт списка чатов бота, поэтому единственный источник —
    обновления, которые проходят через цикл бота.
    """
    connected = {c.get("chat_id") for c in await list_channels()}
    items = [{**v, "connected": v["chat_id"] in connected} for v in _seen_chats.values()]
    if items:
        return {"ok": True, "items": items, "hint": ""}

    from publishers.telegram_pub import bot_token
    if not (token or bot_token()):
        return {"ok": False, "items": [],
                "error": "бот не подключён — начните с первого шага"}
    return {"ok": True, "items": [],
            "hint": ("Добавьте бота администратором в канал и опубликуйте там любое "
                     "сообщение — канал появится в списке в течение нескольких секунд. "
                     "Либо укажите @имя канала вручную ниже.")}


async def check_channel(chat_id: str, token: str = "") -> dict:
    """Шаги 3–4: проверка прав и возможности публикации.

    Отвечает на два разных вопроса. «Права» — что говорит Telegram про роль бота
    (`getChatMember`). «Можно ли публиковать» — вывод из этих прав: для канала
    нужен can_post_messages, для группы достаточно быть админом.
    """
    chat_id = (chat_id or "").strip()
    if not chat_id:
        return {"ok": False, "error": "не указан канал"}

    chat = await tg.call("getChat", {"chat_id": chat_id}, token=token)
    if not chat.get("ok"):
        return {"ok": False, "error": chat.get("error") or "канал не найден",
                "hint": "Проверьте @имя канала и что бот добавлен в него администратором."}
    info = chat.get("result") or {}

    me = await tg.call("getMe", {}, token=token)
    if not me.get("ok"):
        return {"ok": False, "error": me.get("error") or "токен бота не принят"}
    bot_id = (me.get("result") or {}).get("id")

    member = await tg.call("getChatMember", {"chat_id": info.get("id", chat_id),
                                             "user_id": bot_id}, token=token)
    if not member.get("ok"):
        return {"ok": False, "error": member.get("error") or "не удалось узнать права бота",
                "chat": _chat_brief(info)}
    m = member.get("result") or {}
    status = m.get("status") or ""
    is_admin = status in ("administrator", "creator")
    chat_type = info.get("type") or ""

    if chat_type == "channel":
        can_publish = bool(m.get(POST_RIGHT)) or status == "creator"
    else:
        # В группе обычный участник обычно писать может, но право могут отобрать
        # настройками группы. Раньше любой `member` считался пригодным — и канал
        # сохранялся как рабочий, а посты в него не уходили.
        restricted = status == "restricted"
        can_publish = is_admin or (status == "member" and not restricted)
        if restricted:
            can_publish = bool(m.get("can_send_messages"))

    rights = sorted(k for k, v in m.items() if k.startswith("can_") and v is True)
    if can_publish:
        reason = ""
    elif chat_type == "channel" and not is_admin:
        reason = "бот не администратор канала"
    elif chat_type == "channel":
        reason = "у бота нет права «Публикация сообщений»"
    else:
        reason = "боту запрещено писать в этой группе"

    return {"ok": True, "chat": _chat_brief(info), "status": status,
            "is_admin": is_admin, "can_publish": can_publish, "rights": rights,
            "reason": reason,
            "hint": "" if can_publish else
                    ("Откройте канал → Администраторы → добавьте бота и включите "
                     "«Публикация сообщений»." if chat_type == "channel" else
                     "Проверьте разрешения группы: боту нужно право отправлять сообщения.")}


def _chat_brief(info: dict) -> dict:
    return {"chat_id": str(info.get("id") or ""), "title": info.get("title") or "",
            "username": ("@" + info["username"]) if info.get("username") else "",
            "type": info.get("type") or ""}


async def test_publish(chat_id: str, token: str = "", *, keep: bool = False) -> dict:
    """Шаг 5: тестовая публикация. По умолчанию сообщение удаляется — канал
    пользователя не должен превращаться в свалку проверок."""
    text = ("✅ <b>NEXUS AI</b> — тестовая публикация.\n"
            "Канал подключён и готов принимать посты.")
    res = await tg.send_message(chat_id, text, token=token, silent=True)
    if not res.get("ok"):
        return {"ok": False, "error": res.get("error"),
                "hint": "Публикация не прошла: проверьте права бота в канале."}
    deleted = False
    if not keep and res.get("message_id"):
        d = await tg.delete_message(chat_id, res["message_id"], token=token)
        deleted = bool(d.get("ok"))
    return {"ok": True, "message_id": res.get("message_id"), "post_url": res.get("post_url"),
            "deleted": deleted}


# ─────────────────────────── список подключённых ───────────────────────────

async def add_channel(chat_id: str, *, make_default: bool = True,
                      token: str = "") -> dict:
    """Сохраняет канал, но только если он реально пригоден для публикации.
    Иначе в списке заведётся «подключение», которое молча не работает."""
    check = await check_channel(chat_id, token=token)
    if not check.get("ok"):
        return check
    if not check.get("can_publish"):
        return {"ok": False, "error": check.get("reason") or "публикация недоступна",
                "hint": check.get("hint"), "check": check}

    chat = check["chat"]
    entry = {**chat, "connected_at": int(time.time()),
             "rights": check.get("rights", []), "default": False}

    async with kv.update(CHANNELS_KEY, []) as items:
        items[:] = [c for c in items if c.get("chat_id") != chat["chat_id"]]
        items.append(entry)
        if make_default or len(items) == 1:
            for c in items:
                c["default"] = c["chat_id"] == chat["chat_id"]

    # Совместимость: остальной код (коннектор, планировщик) читает переменную.
    os.environ["TELEGRAM_POST_CHAT_ID"] = chat["chat_id"]
    await _persist_env("telegram_post_chat_id", chat["chat_id"])
    return {"ok": True, "channel": entry, "check": check}


async def remove_channel(chat_id: str) -> dict:
    removed = False
    async with kv.update(CHANNELS_KEY, []) as items:
        rest = [c for c in items if str(c.get("chat_id")) != str(chat_id)]
        removed = len(rest) != len(items)
        if removed:
            if rest and not any(c.get("default") for c in rest):
                rest[0]["default"] = True
            items[:] = rest
    if not removed:
        return {"ok": False, "error": "канал не подключён"}
    os.environ["TELEGRAM_POST_CHAT_ID"] = await default_channel()
    await _persist_env("telegram_post_chat_id", os.environ["TELEGRAM_POST_CHAT_ID"])
    return {"ok": True, "removed": str(chat_id)}


async def set_default(chat_id: str) -> dict:
    known = False
    async with kv.update(CHANNELS_KEY, []) as items:
        known = any(str(c.get("chat_id")) == str(chat_id) for c in items)
        if known:
            for c in items:
                c["default"] = str(c.get("chat_id")) == str(chat_id)
    if not known:
        return {"ok": False, "error": "канал не подключён"}
    os.environ["TELEGRAM_POST_CHAT_ID"] = str(chat_id)
    await _persist_env("telegram_post_chat_id", str(chat_id))
    return {"ok": True, "default": str(chat_id)}


async def _persist_env(key_name: str, value: str):
    """Настройки переживают рестарт только в БД: на Render процесс поднимается
    с чистым окружением и подтягивает ключи из таблицы Connection."""
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Connection).where(Connection.key_name == key_name))
        c = r.scalar_one_or_none()
        if c:
            c.key_value = value
        else:
            db.add(Connection(key_name=key_name, key_value=value))
        await db.commit()


async def status() -> dict:
    """Сводка для страницы подключения: бот, каналы, готовность публиковать."""
    info = await bot_info()
    items = await list_channels()
    return {"bot": info, "channels": items, "default": await default_channel(),
            "ready": bool(info.get("ok") and (items or await default_channel()))}
