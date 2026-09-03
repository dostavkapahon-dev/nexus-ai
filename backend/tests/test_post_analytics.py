"""Аналитика опубликованного: сохранение метрик, сводки, обучение на результатах."""
from datetime import datetime, timedelta

import pytest

from sqlalchemy import delete

from core import post_analytics as pa
from database.db import AsyncSessionLocal
from database.models import Publication


@pytest.fixture(autouse=True)
async def _clean_publications(client):
    """БД в тестах общая на прогон — чистим публикации, чтобы проверки не зависели
    от того, что насоздавали соседние тесты."""
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Publication))
        await db.commit()
    yield


async def _add_pub(platform="instagram", er=0.0, views=0, topic="тема", hook="хук",
                   status="published", age_hours=24, url="", metrics=True):
    async with AsyncSessionLocal() as db:
        p = Publication(
            plan_id="plan-1", niche_id="niche-1", platform=platform, status=status,
            post_url=url or f"https://x/{topic}", topic=topic, hook=hook,
            content_format="reels", views=views, likes=int(views * 0.1),
            comments=int(views * 0.01), engagement_rate=er,
            published_at=datetime.utcnow() - timedelta(hours=age_hours),
            metrics_updated_at=datetime.utcnow() if metrics else None)
        db.add(p)
        await db.commit()
        return p.id


def test_engagement_rate_uses_reach_then_views():
    assert pa._engagement_rate(10, 5, 5, reach=1000, views=2000) == 2.0
    # Охвата нет — считаем от просмотров
    assert pa._engagement_rate(10, 5, 5, reach=0, views=1000) == 2.0
    # Ни того ни другого — не делим на ноль
    assert pa._engagement_rate(10, 5, 5, reach=0, views=0) == 0.0


@pytest.mark.asyncio
async def test_record_publication_saves_what_was_posted(client):
    """Тема, хук и формат нужны, чтобы связать результат с приёмом."""
    pub_id = await pa.record_publication(
        plan_id="p1", niche_id="n1", platform="instagram", status="published",
        post_url="https://insta/1", topic="доставка за час", hook="Смотри до конца",
        content_format="reels")
    async with AsyncSessionLocal() as db:
        row = await db.get(Publication, pub_id)
    assert row.topic == "доставка за час"
    assert row.hook == "Смотри до конца"
    assert row.content_format == "reels"
    assert row.niche_id == "n1"


@pytest.mark.asyncio
async def test_performance_aggregates_and_counts_failures(client):
    await _add_pub(er=5.0, views=1000, topic="a")
    await _add_pub(er=3.0, views=500, topic="b", platform="tiktok")
    await _add_pub(status="failed", topic="c")

    perf = await pa.performance(30)
    assert perf["posts"] == 2                 # провалы не считаются публикациями
    assert perf["failed"] == 1
    assert perf["views"] == 1500
    assert perf["avg_engagement_rate"] == pytest.approx(4.0)
    assert {p["platform"] for p in perf["by_platform"]} == {"instagram", "tiktok"}


@pytest.mark.asyncio
async def test_top_and_worst_posts_are_ordered(client):
    await _add_pub(er=1.0, views=100, topic="слабый")
    await _add_pub(er=9.0, views=900, topic="сильный")
    await _add_pub(er=5.0, views=500, topic="средний")

    best = await pa.top_posts(30, limit=3)
    assert best[0]["topic"] == "сильный"

    worst = await pa.top_posts(30, limit=3, worst=True)
    assert worst[0]["topic"] == "слабый"


@pytest.mark.asyncio
async def test_posts_without_metrics_are_excluded_from_top(client):
    """Пока метрики не собраны, пост не должен попадать в выводы — иначе учимся на нулях."""
    await _add_pub(er=0.0, topic="без метрик", metrics=False)
    assert await pa.top_posts(30) == []


@pytest.mark.asyncio
async def test_collect_metrics_updates_from_connector(client, monkeypatch):
    pub_id = await _add_pub(topic="целевой", url="https://insta/target", metrics=False)

    async def fake_fetch(platform, limit=25):
        return {"https://insta/target": {"views": 5000, "likes": 400,
                                         "comments": 50, "saved": 50, "reach": 4000}}

    monkeypatch.setattr(pa, "_fetch_platform_metrics", fake_fetch)
    res = await pa.collect_metrics()
    assert res["updated"] == 1

    async with AsyncSessionLocal() as db:
        row = await db.get(Publication, pub_id)
    assert row.views == 5000
    assert row.likes == 400
    assert row.engagement_rate == pytest.approx(12.5)   # (400+50+50)/4000
    assert row.metrics_updated_at is not None


@pytest.mark.asyncio
async def test_collect_skips_too_fresh_posts(client, monkeypatch):
    """Сразу после публикации метрик ещё нет — опрашивать бессмысленно."""
    await _add_pub(topic="только что", age_hours=0, metrics=False)

    called = []

    async def fake_fetch(platform, limit=25):
        called.append(platform)
        return {}

    monkeypatch.setattr(pa, "_fetch_platform_metrics", fake_fetch)
    res = await pa.collect_metrics()
    assert res["updated"] == 0
    assert called == []          # до площадки даже не дошли


@pytest.mark.asyncio
async def test_learn_from_results_feeds_agent_memory(client, monkeypatch):
    await _add_pub(er=9.0, views=900, topic="сработало", hook="хороший хук")
    await _add_pub(er=0.5, views=50, topic="не сработало", hook="слабый хук")

    captured = {}

    async def fake_learn(text, source=""):
        captured["text"] = text
        captured["source"] = source
        return [{"title": "урок"}]

    import core.skills_store as ss
    monkeypatch.setattr(ss, "learn_from", fake_learn)

    res = await pa.learn_from_results(30)
    assert res["ok"] is True
    assert captured["source"] == "post_analytics"
    assert "сработало" in captured["text"]
    assert "хороший хук" in captured["text"]
    assert "ЧТО СРАБОТАЛО ХУЖЕ" in captured["text"]


@pytest.mark.asyncio
async def test_learn_reports_honestly_when_no_data(client):
    res = await pa.learn_from_results(30)
    assert res["ok"] is False
    assert "нет публикаций" in res["reason"]


@pytest.mark.asyncio
async def test_performance_api(auth_client):
    await _add_pub(er=4.0, views=400, topic="через api")

    r = await auth_client.get("/api/performance", params={"days": 30})
    assert r.status_code == 200
    assert r.json()["posts"] >= 1

    r2 = await auth_client.get("/api/performance/top", params={"limit": 5})
    assert any(p["topic"] == "через api" for p in r2.json()["posts"])

    r3 = await auth_client.post("/api/performance/collect")
    assert "updated" in r3.json()
