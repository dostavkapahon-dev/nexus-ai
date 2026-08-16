"""
Память диалога с ботом: последние реплики и «чего мы ждём от пользователя».

Без неё каждое сообщение читалось в отрыве от предыдущего: на список вариантов
ответ «1» ничего не значил, а «Напиши» — тем более, и бот замолкал. Здесь
хранится короткая история и явное ожидание (например, темы ролика), чтобы
следующая фраза попадала туда, куда человек и целился.

Состояние лежит в таблице Connection — как у автопилота, без миграций схемы.
"""
import json

from sqlalchemy import select

from database.db import AsyncSessionLocal
from database.models import Connection

KEEP = 8               # реплик в памяти
MAX_CHARS = 2000       # сколько истории отдаём модели
AWAIT_TOPIC = "topic"  # ждём тему ролика


def _key(chat_id: str) -> str:
    return f"dialog_{chat_id}"


async def _load(chat_id: str) -> dict:
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Connection).where(Connection.key_name == _key(chat_id)))
        c = r.scalar_one_or_none()
        if c and c.key_value:
            try:
                return json.loads(c.key_value)
            except Exception:
                return {}
    return {}


async def _save(chat_id: str, state: dict):
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Connection).where(Connection.key_name == _key(chat_id)))
        c = r.scalar_one_or_none()
        payload = json.dumps(state, ensure_ascii=False)
        if c:
            c.key_value = payload
        else:
            db.add(Connection(key_name=_key(chat_id), key_value=payload))
        await db.commit()


async def remember(chat_id: str, role: str, text: str):
    """Кладёт реплику в память. role: user | agent."""
    if not text:
        return
    st = await _load(chat_id)
    turns = st.get("turns", [])
    turns.append({"role": role, "text": str(text)[:800]})
    st["turns"] = turns[-KEEP:]
    await _save(chat_id, st)


async def history(chat_id: str, n: int = KEEP) -> str:
    """История в виде текста для модели. Пусто — значит разговор начался сейчас."""
    st = await _load(chat_id)
    turns = (st.get("turns") or [])[-n:]
    if not turns:
        return ""
    lines = [f"{'Пользователь' if t['role'] == 'user' else 'Бот'}: {t['text']}"
             for t in turns]
    out = "\n".join(lines)
    return out[-MAX_CHARS:]


async def expect(chat_id: str, what: str, data: dict | None = None):
    """Отметить, чего ждём от следующего сообщения (или снять ожидание).

    `data` — контекст ожидания: например, что человек уже выбрал «видео» и
    «Instagram», осталось назвать тему. Без него выбор кнопками терялся бы к
    моменту, когда придёт текст.
    """
    st = await _load(chat_id)
    if what:
        st["awaiting"] = what
        st["pending"] = data or {}
    else:
        st.pop("awaiting", None)
        st.pop("pending", None)
    await _save(chat_id, st)


async def pending(chat_id: str) -> dict:
    """Контекст текущего ожидания."""
    return (await _load(chat_id)).get("pending") or {}


async def awaiting(chat_id: str) -> str:
    return (await _load(chat_id)).get("awaiting") or ""


async def clear(chat_id: str):
    await _save(chat_id, {})
