"""Контент-план должен становиться публикациями, а не только сообщением в чате.

План недели жил в KV-состоянии автопилота, а генерация, очередь, публикация и
планировщик читают таблицу content_plans — и о нём не знали. Из-за этого
«создать публикацию из плана» не работало.
"""
import pytest
from sqlalchemy import select

from core import autopilot as ap
from database.db import AsyncSessionLocal
from database.models import ContentPlan, Niche


DAYS = [
    {"day": 1, "format": "reels", "topic": "Как мы возим за час", "hook": "Час — и всё"},
    {"day": 2, "format": "post", "topic": "Отзыв клиента", "hook": "Он не поверил"},
    {"day": 3, "format": "carousel", "topic": "5 ошибок", "hook": "Пятая — дорогая"},
]


async def _make_niche(platforms):
    async with AsyncSessionLocal() as db:
        for old in (await db.execute(select(Niche))).scalars():
            await db.delete(old)
        for old in (await db.execute(select(ContentPlan))).scalars():
            await db.delete(old)
        niche = Niche(name="Доставка", status="active", platforms=platforms)
        db.add(niche)
        await db.commit()
        return niche.id


@pytest.mark.asyncio
async def test_week_plan_becomes_queue_items(client):
    niche_id = await _make_niche(["instagram", "telegram"])

    saved = await ap.persist_week_plan(DAYS)
    assert saved == 3

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(ContentPlan).order_by(ContentPlan.day_number))).scalars().all()

    assert [r.topic for r in rows] == [d["topic"] for d in DAYS]
    assert all(r.niche_id == niche_id and r.status == "pending" for r in rows)
    # Формат подсказывает площадку, но только из подключённых для ниши.
    assert rows[0].platform == "instagram"
    assert rows[1].platform == "telegram"


@pytest.mark.asyncio
async def test_platform_falls_back_to_a_connected_one(client):
    """Threads формату соответствует, но если площадка не подключена — не выдумываем."""
    await _make_niche(["telegram"])

    await ap.persist_week_plan([{"day": 1, "format": "threads", "topic": "т", "hook": "х"}])

    async with AsyncSessionLocal() as db:
        row = (await db.execute(select(ContentPlan))).scalars().first()
    assert row.platform == "telegram"


@pytest.mark.asyncio
async def test_replanning_does_not_pile_up_duplicates(client):
    """Повторный /plan7 заменяет незапущенные пункты, а не копит их."""
    await _make_niche(["instagram"])

    await ap.persist_week_plan(DAYS)
    await ap.persist_week_plan(DAYS)

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(ContentPlan))).scalars().all()
    assert len(rows) == 3


@pytest.mark.asyncio
async def test_started_items_survive_replanning(client):
    """Уже сгенерированное replan затирать нельзя — это потерянная работа."""
    await _make_niche(["instagram"])
    await ap.persist_week_plan(DAYS)

    async with AsyncSessionLocal() as db:
        row = (await db.execute(select(ContentPlan))).scalars().first()
        row.status = "generated"
        await db.commit()

    await ap.persist_week_plan(DAYS)

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(ContentPlan))).scalars().all()
    assert sum(1 for r in rows if r.status == "generated") == 1


@pytest.mark.asyncio
async def test_without_a_niche_nothing_is_written(client):
    """Без ниши привязать план не к чему — молча плодить сироты нельзя."""
    async with AsyncSessionLocal() as db:
        for old in (await db.execute(select(Niche))).scalars():
            await db.delete(old)
        for old in (await db.execute(select(ContentPlan))).scalars():
            await db.delete(old)
        await db.commit()

    assert await ap.persist_week_plan(DAYS) == 0
