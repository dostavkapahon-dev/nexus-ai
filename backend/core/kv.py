"""
Общее KV-хранилище: чтение и правка одной строки без гонок.

Проблема. Состояние системы — очередь согласования, ответы на комментарии,
список каналов, ход интервью автопилота — лежит JSON-строками в таблице
`Connection`. Каждый модуль правил свою строку одинаково: прочитал → изменил в
памяти → записал целиком. Между чтением и записью успевает вклиниться соседняя
задача (Telegram обрабатывает сообщения параллельно, планировщик работает
одновременно с запросами), и та, что коммитится последней, затирает чужое
изменение. Пост исчезает из очереди на согласование, ответ на комментарий
пропадает, ответ на вопрос интервью не сохраняется — без единого следа в логах.

Точечные замки это не лечили: замок в одном модуле не защищает строку, которую
правит другой. Поэтому замок живёт здесь, рядом с самой операцией, и один на
ключ — правки разных ключей друг друга не ждут.

Два уровня защиты:
  • `asyncio.Lock` на ключ — от гонки задач внутри процесса (основной случай:
    на Render крутится один инстанс);
  • `SELECT … FOR UPDATE` на Postgres — от гонки процессов, если инстансов
    станет несколько. На SQLite не действует, но там запись и так одна за раз.

Использование:

    async with kv.update("moderation_queue", {}) as queue:
        queue[pid] = item          # изменения сохранятся при выходе из блока
"""
import asyncio
import json
from contextlib import asynccontextmanager

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from database.db import PERSISTENT, AsyncSessionLocal
from database.models import Connection

_locks: dict[str, asyncio.Lock] = {}


def _lock_for(key: str) -> asyncio.Lock:
    """Один замок на ключ. Словарь пополняется из корутин, а между `in` и
    присваиванием нет `await` — значит переключения задач тут произойти не может
    и два замка на один ключ не появятся."""
    lock = _locks.get(key)
    if lock is None:
        lock = _locks[key] = asyncio.Lock()
    return lock


def _decode(raw: str | None, default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except ValueError:
        # Не JSON. Два разных случая, и путать их нельзя:
        #  • ключ хранит простое значение — строку, записанную не через `kv`
        #    (так пишут `telegram_owner` и другие модули). Её и возвращаем;
        #  • ключ хранит структуру, а строка испорчена — тогда честнее отдать
        #    пустое состояние: вызывающий перезапишет его, а не упадёт на
        #    каждом заходе.
        if default is None or isinstance(default, str):
            return raw
        return default


def _encode(value) -> str:
    """Всегда JSON — включая строки.

    Раньше строка писалась как есть, а читалась через `json.loads` и не
    разбиралась: `set(key, "pid123")` с последующим `get` возвращал пустоту.
    Так молча ломался флаг «человек сейчас пишет правки» — кнопка «Правки»
    переставала работать.
    """
    return json.dumps(value, ensure_ascii=False)


async def get(key: str, default=None):
    """Значение ключа. Без замка: чтение никому не мешает."""
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Connection).where(Connection.key_name == key))
        row = r.scalar_one_or_none()
    return _decode(row.key_value if row else None, default)


async def set(key: str, value) -> None:
    """Записать значение целиком. Для замены, не для правки: если новое значение
    считается из старого, нужен `update` — иначе возвращается та же гонка."""
    async with _lock_for(key):
        await _write(key, _encode(value))


async def _write(key: str, payload: str) -> None:
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Connection).where(Connection.key_name == key))
        row = r.scalar_one_or_none()
        if row:
            row.key_value = payload
        else:
            db.add(Connection(key_name=key, key_value=payload))
        try:
            await db.commit()
        except IntegrityError:
            # Строку успел создать кто-то другой между выборкой и вставкой.
            # Она уникальна по key_name, поэтому просто дописываем в неё.
            await db.rollback()
            r = await db.execute(select(Connection).where(Connection.key_name == key))
            row = r.scalar_one_or_none()
            if row:
                row.key_value = payload
                await db.commit()


@asynccontextmanager
async def update(key: str, default=None):
    """Прочитать, дать изменить, сохранить — целиком под замком.

    Отдаётся то, что лежит в базе (или `default`). Менять нужно сам объект:
    список и словарь правятся на месте, поэтому `q[pid] = item` и `items.append(...)`
    работают. Если нужно заменить значение целиком — используйте `set`.

    Исключение внутри блока ничего не сохраняет: половина изменения хуже, чем
    его отсутствие, — по ней потом не понять, что состояние неполное.
    """
    async with _lock_for(key):
        async with AsyncSessionLocal() as db:
            stmt = select(Connection).where(Connection.key_name == key)
            if PERSISTENT:
                stmt = stmt.with_for_update()      # блокировка строки в Postgres
            r = await db.execute(stmt)
            row = r.scalar_one_or_none()
            value = _decode(row.key_value if row else None, default)

            yield value

            payload = _encode(value)
            if row:
                row.key_value = payload
            else:
                db.add(Connection(key_name=key, key_value=payload))
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
                await _write(key, payload)


async def replace(key: str, fn):
    """Заменить значение результатом `fn(старое)` — под тем же замком.

    Нужно там, где новое значение не правится на месте, а вычисляется:
    обрезанный список, отфильтрованный словарь.
    """
    async with _lock_for(key):
        async with AsyncSessionLocal() as db:
            stmt = select(Connection).where(Connection.key_name == key)
            if PERSISTENT:
                stmt = stmt.with_for_update()
            r = await db.execute(stmt)
            row = r.scalar_one_or_none()
            current = _decode(row.key_value if row else None, None)
            new = fn(current)
            payload = _encode(new)
            if row:
                row.key_value = payload
            else:
                db.add(Connection(key_name=key, key_value=payload))
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
                await _write(key, payload)
    return new
