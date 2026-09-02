"""Правка KV-строки без потерянных записей.

Состояние системы (очередь согласования, ответы на комментарии, список каналов,
ход интервью) лежит JSON-строками в `Connection`. Каждый модуль правил свою
строку по схеме «прочитал → изменил → записал целиком», и параллельная задача
успевала вклиниться между чтением и записью: побеждала та, что коммитилась
последней, а чужое изменение исчезало без следа в логах.
"""
import asyncio
import json

import pytest
from sqlalchemy import select

from core import kv
from database.db import AsyncSessionLocal, init_db
from database.models import Connection


@pytest.fixture(autouse=True)
def _fresh_locks():
    kv._locks.clear()
    yield
    kv._locks.clear()


async def _raw(key: str):
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Connection).where(Connection.key_name == key))
        row = r.scalar_one_or_none()
    return row.key_value if row else None


@pytest.mark.asyncio
async def test_parallel_appends_all_survive():
    """Главный случай: двадцать задач дописывают в один список одновременно.
    Без замка выживала бы горстка — та, что успела закоммититься последней."""
    await init_db()
    key = "test_parallel_appends"

    async def add(n: int):
        async with kv.update(key, []) as items:
            await asyncio.sleep(0)      # уступаем управление ровно в середине правки
            items.append(n)

    await asyncio.gather(*(add(i) for i in range(20)))

    assert sorted(json.loads(await _raw(key))) == list(range(20))


@pytest.mark.asyncio
async def test_parallel_dict_writes_all_survive():
    """Очередь согласования — словарь: пропавший ключ = пост, исчезнувший
    с согласования."""
    await init_db()
    key = "test_parallel_dict"

    async def put(n: int):
        async with kv.update(key, {}) as queue:
            await asyncio.sleep(0)
            queue[f"id{n}"] = {"text": n}

    await asyncio.gather(*(put(i) for i in range(15)))

    assert len(json.loads(await _raw(key))) == 15


@pytest.mark.asyncio
async def test_different_keys_do_not_wait_for_each_other():
    """Замок — на ключ, а не общий: правка очереди не должна ждать правку ленты."""
    await init_db()
    order = []

    async def slow():
        async with kv.update("test_slow", []) as v:
            await asyncio.sleep(0.05)
            v.append("slow")
            order.append("slow")

    async def quick():
        await asyncio.sleep(0.01)
        async with kv.update("test_quick", []) as v:
            v.append("quick")
            order.append("quick")

    await asyncio.gather(slow(), quick())
    assert order == ["quick", "slow"], "быстрая правка чужого ключа ждала медленную"


@pytest.mark.asyncio
async def test_failure_inside_block_saves_nothing():
    """Половина изменения хуже, чем его отсутствие: по ней потом не понять,
    что состояние неполное."""
    await init_db()
    key = "test_rollback"
    await kv.set(key, ["целое"])

    with pytest.raises(RuntimeError):
        async with kv.update(key, []) as items:
            items.append("половина")
            raise RuntimeError("шаг не удался")

    assert await kv.get(key) == ["целое"]


@pytest.mark.asyncio
async def test_broken_json_does_not_break_the_caller():
    """Испорченная строка не должна ронять каждый заход — вызывающий получает
    пустое состояние и перезаписывает его."""
    await init_db()
    key = "test_broken"
    async with AsyncSessionLocal() as db:
        db.add(Connection(key_name=key, key_value="{не json"))
        await db.commit()

    assert await kv.get(key, {"по умолчанию": 1}) == {"по умолчанию": 1}
    async with kv.update(key, []) as items:
        items.append("новое")
    assert await kv.get(key) == ["новое"]


@pytest.mark.asyncio
async def test_replace_computes_from_current_under_lock():
    await init_db()
    key = "test_replace"
    await kv.set(key, [1, 2, 3, 4, 5])
    result = await kv.replace(key, lambda cur: (cur or [])[-2:])
    assert result == [4, 5] and await kv.get(key) == [4, 5]


@pytest.mark.asyncio
async def test_missing_key_returns_default():
    await init_db()
    assert await kv.get("test_never_written", "пусто") == "пусто"


# ─────────────────── модули, переведённые на общий слой ───────────────────

@pytest.mark.asyncio
async def test_moderation_queue_keeps_every_post(monkeypatch):
    """Пост, исчезнувший из очереди на согласование, — самая дорогая потеря:
    работа сделана, но человек её никогда не увидит."""
    from core import moderation

    await init_db()
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setattr(moderation, "_tg", lambda *a, **k: asyncio.sleep(0))
    await kv.set(moderation.QUEUE_KEY, {})

    pids = await asyncio.gather(*(moderation.send_for_approval(f"пост {i}")
                                  for i in range(10)))

    queue = await kv.get(moderation.QUEUE_KEY, {})
    assert len(queue) == 10
    assert set(pids) == set(queue)


@pytest.mark.asyncio
async def test_webhook_duplicates_rejected_under_parallel_delivery():
    """Meta шлёт повторы пачками. Раздельные чтение и запись означали, что два
    параллельных вызова признавали одно событие новым — разбор комментариев
    запускался дважды на одно и то же."""
    from core import webhooks

    await init_db()
    await kv.set(webhooks.EVENTS_KEY, [])
    event = [{"id": "evt-1", "kind": "comment"}]

    results = await asyncio.gather(*(webhooks._remember(list(event)) for _ in range(8)))

    assert sum(len(r) for r in results) == 1, "событие принято больше одного раза"


@pytest.mark.asyncio
async def test_activity_feed_keeps_parallel_entries():
    from core import command_center

    await init_db()
    await kv.set(command_center.FEED_KEY, [])
    await asyncio.gather(*(command_center.log_event("telegram", "user", f"={i}")
                           for i in range(12)))

    feed = await kv.get(command_center.FEED_KEY, [])
    assert len(feed) == 12
    assert len(feed) <= command_center.FEED_MAX
