"""Стратегии: версии, активация, сравнение по фактическому результату."""
from datetime import datetime

import pytest
from sqlalchemy import delete

from core import strategy_store as ss
from database.db import AsyncSessionLocal
from database.models import Strategy, Publication


@pytest.fixture(autouse=True)
async def _clean(client):
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Strategy))
        await db.execute(delete(Publication))
        await db.commit()
    yield


async def _publish(strategy_id: str, er: float, views: int = 100):
    async with AsyncSessionLocal() as db:
        db.add(Publication(plan_id="p", niche_id="n1", platform="instagram",
                           status="published", strategy_id=strategy_id,
                           views=views, engagement_rate=er,
                           published_at=datetime.utcnow()))
        await db.commit()


@pytest.mark.asyncio
async def test_options_saved_as_versioned_drafts(client):
    """Раньше варианты лежали в KV и перезатирались — теперь это версии в БД."""
    ids = await ss.save_options([
        {"title": "Экспертный тон", "angle": "разбираем ошибки"},
        {"title": "Больше каруселей", "angle": "сохранения"},
    ], niche_id="n1")
    assert len(ids) == 2

    items = await ss.history("n1")
    assert all(i["status"] == ss.DRAFT for i in items)
    assert all(i["version"] == 1 for i in items)

    # Следующий набор получает новую версию, прошлый не теряется
    await ss.save_options([{"title": "Третий подход"}], niche_id="n1")
    items2 = await ss.history("n1")
    assert len(items2) == 3
    assert max(i["version"] for i in items2) == 2


@pytest.mark.asyncio
async def test_only_one_strategy_stays_active(client):
    """Активной может быть одна — иначе непонятно, чей результат мы меряем."""
    ids = await ss.save_options([{"title": "Первая"}, {"title": "Вторая"}], niche_id="n1")

    await ss.activate(ids[0])
    assert (await ss.current("n1"))["title"] == "Первая"

    await ss.activate(ids[1])
    cur = await ss.current("n1")
    assert cur["title"] == "Вторая"

    archived = await ss.history("n1", status=ss.ARCHIVED)
    assert len(archived) == 1
    assert archived[0]["title"] == "Первая"
    assert archived[0]["archived_at"] is not None


@pytest.mark.asyncio
async def test_activate_unknown_returns_none(client):
    assert await ss.activate("нет-такой") is None


@pytest.mark.asyncio
async def test_effectiveness_compares_by_real_results(client):
    """Смысл блока: видно, какая стратегия дала лучший отклик."""
    ids = await ss.save_options([{"title": "Слабая"}, {"title": "Сильная"}], niche_id="n1")
    await _publish(ids[0], er=1.5)
    await _publish(ids[0], er=2.5)
    await _publish(ids[1], er=9.0)

    items = await ss.effectiveness("n1")
    assert items[0]["title"] == "Сильная"
    assert items[0]["avg_engagement_rate"] == pytest.approx(9.0)
    assert items[1]["posts"] == 2
    assert items[1]["avg_engagement_rate"] == pytest.approx(2.0)


@pytest.mark.asyncio
async def test_drafts_without_posts_are_not_compared(client):
    """Черновик без публикаций сравнивать не с чем — он не мусорит в выдаче."""
    ids = await ss.save_options([{"title": "Черновик"}, {"title": "Рабочая"}], niche_id="n1")
    await _publish(ids[1], er=5.0)

    items = await ss.effectiveness("n1")
    assert [i["title"] for i in items] == ["Рабочая"]


@pytest.mark.asyncio
async def test_best_requires_enough_publications(client):
    """Одна удачная публикация — ещё не доказательство: нужен объём."""
    ids = await ss.save_options([{"title": "Случайный успех"}], niche_id="n1")
    await _publish(ids[0], er=50.0)
    assert await ss.best("n1") is None          # публикаций мало

    await _publish(ids[0], er=40.0)
    await _publish(ids[0], er=45.0)
    top = await ss.best("n1")
    assert top["title"] == "Случайный успех"
    assert top["posts"] == 3


@pytest.mark.asyncio
async def test_manual_strategy_is_equal_citizen(client):
    sid = await ss.add_manual("Своя стратегия", angle="как я решил",
                              pillars=["кейсы", "разборы"], niche_id="n1")
    await ss.activate(sid)
    cur = await ss.current("n1")
    assert cur["source"] == "manual"
    assert cur["pillars"] == ["кейсы", "разборы"]


@pytest.mark.asyncio
async def test_context_gives_agents_direction(client):
    """Контекст стратегии — то, что подмешивается в генерацию."""
    ids = await ss.save_options([{"title": "Экспертный тон", "angle": "разбираем ошибки"}],
                                niche_id="n1")
    await ss.activate(ids[0])

    ctx = await ss.context("n1")
    assert "Экспертный тон" in ctx
    assert "разбираем ошибки" in ctx
    assert "v1" in ctx


@pytest.mark.asyncio
async def test_context_mentions_historically_best(client):
    """Если прошлая стратегия давала лучший результат — агент должен об этом знать."""
    ids = await ss.save_options([{"title": "Старая удачная"}, {"title": "Новая"}],
                                niche_id="n1")
    for er in (8.0, 9.0, 8.5):
        await _publish(ids[0], er=er)
    await ss.activate(ids[1])

    ctx = await ss.context("n1")
    assert "Новая" in ctx
    assert "ЛУЧШИЙ ИСТОРИЧЕСКИЙ РЕЗУЛЬТАТ" in ctx
    assert "Старая удачная" in ctx


@pytest.mark.asyncio
async def test_context_empty_without_strategy(client):
    assert await ss.context("n1") == ""


@pytest.mark.asyncio
async def test_strategy_api(auth_client):
    ids = await ss.save_options([{"title": "Через API", "angle": "угол"}], niche_id="n1")

    r = await auth_client.get("/api/strategy", params={"niche_id": "n1"})
    assert r.json()["strategies"][0]["title"] == "Через API"

    r2 = await auth_client.post(f"/api/strategy/{ids[0]}/activate")
    assert r2.json()["status"] == ss.ACTIVE

    r3 = await auth_client.get("/api/strategy/current", params={"niche_id": "n1"})
    assert r3.json()["title"] == "Через API"

    r4 = await auth_client.post("/api/strategy/manual",
                                json={"title": "Руками", "angle": "мой угол"})
    assert r4.json()["ok"] is True

    r5 = await auth_client.get("/api/strategy/effectiveness", params={"niche_id": "n1"})
    assert "strategies" in r5.json()
