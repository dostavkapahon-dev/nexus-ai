"""
Кто имеет право командовать ботом.

Раньше владелец задавался переменной `TELEGRAM_CHAT_ID`, и если её не задали —
а это обычный случай, токен можно подключить через веб без неё, — бот исполнял
команды **любого**, кто его нашёл: публикацию в канал, запуск браузера на ПК
владельца, генерацию за деньги. Вдобавок сверялся `chat.id`, а не отправитель:
в группе командовать мог любой участник.

Теперь владелец закрепляется за первым, кто написал боту `/start`, и хранится в
БД. Явно заданный `TELEGRAM_CHAT_ID` имеет приоритет — это ручное указание
владельца, и оно сильнее самозахвата.
"""
import os

from sqlalchemy import select

from database.db import AsyncSessionLocal
from database.models import Connection

OWNER_KEY = "telegram_owner_id"

_cache: str | None = None


def _env_owner() -> str:
    return (os.getenv("TELEGRAM_CHAT_ID", "") or "").strip()


async def owner_id() -> str:
    """Идентификатор владельца: из настроек, иначе закреплённый первым /start."""
    global _cache
    env = _env_owner()
    if env:
        return env
    if _cache is not None:
        return _cache
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Connection).where(Connection.key_name == OWNER_KEY))
        c = r.scalar_one_or_none()
    _cache = (c.key_value or "").strip() if c else ""
    return _cache


async def claim(user_id: str) -> bool:
    """Закрепить владельца. Возвращает True, если владельцем стал именно этот.

    Повторный вызов от того же человека безвреден; от чужого — ничего не меняет.
    """
    global _cache
    user_id = str(user_id or "").strip()
    if not user_id:
        return False
    current = await owner_id()
    if current:
        return current == user_id
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Connection).where(Connection.key_name == OWNER_KEY))
        c = r.scalar_one_or_none()
        if c and (c.key_value or "").strip():
            _cache = c.key_value.strip()
            return _cache == user_id
        if c:
            c.key_value = user_id
        else:
            db.add(Connection(key_name=OWNER_KEY, key_value=user_id))
        await db.commit()
    _cache = user_id
    return True


async def reset():
    """Снять закрепление (смена владельца через настройки)."""
    global _cache
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Connection).where(Connection.key_name == OWNER_KEY))
        c = r.scalar_one_or_none()
        if c:
            await db.delete(c)
            await db.commit()
    _cache = None


def invalidate():
    global _cache
    _cache = None


async def allowed(user_id: str, chat_id: str = "") -> bool:
    """Можно ли выполнять команду от этого отправителя.

    Смотрим на отправителя (`from.id`), а не на чат: в группе иначе командовать
    может любой участник. `chat_id` принимается для случая, когда отправитель
    неизвестен (например, сообщение от имени канала) — тогда сверяем чат.
    """
    owner = await owner_id()
    if not owner:
        return False           # владельца нет — не слушаемся никого
    user_id = str(user_id or "").strip()
    chat_id = str(chat_id or "").strip()
    return owner in (user_id, chat_id)


DENIED = ("👋 Это личный бот NEXUS AI. Командовать им может только владелец.\n"
          "Если это ваш бот — откройте его настройки в панели и укажите себя владельцем.")

CLAIMED = ("✅ Вы закреплены как владелец этого бота.\n"
           "Теперь команды принимаются только от вас.")
