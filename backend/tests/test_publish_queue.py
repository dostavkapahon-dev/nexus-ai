"""Очередь публикаций: повторы после сбоя, честный отказ, расписание."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import delete, select

from core import publish_queue as pq
from core.orchestrator import nexus_core
from database.db import AsyncSessionLocal
from database.models import Publication


@pytest.fixture(autouse=True)
async def _clean(client):
    """Очередь общая на всю БД — соседние тесты не должны видеть чужие записи."""
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Publication))
        await db.commit()
    yield


async def _get(pub_id):
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Publication).where(Publication.id == pub_id))
        return r.scalar_one()


@pytest.mark.asyncio
async def test_transient_failure_is_retried_not_lost(client, monkeypatch):
    """Раньше сетевой сбой означал потерянный пост: строка failed без текста."""
    async def flaky(platform, text, image_url):
        return {"ok": False, "error": "timeout: площадка не ответила"}

    monkeypatch.setattr(nexus_core, "_publish_one", flaky)
    pub_id = await pq.enqueue("instagram", "текст поста", "https://img/1.png")

    res = await pq.attempt(pub_id)
    assert res["ok"] is False

    pub = await _get(pub_id)
    assert pub.status == pq.RETRYING
    assert pub.attempts == 1
    assert pub.next_retry_at > datetime.utcnow()
    assert pub.text == "текст поста"          # текст сохранён — есть чем повторять
    assert "timeout" in pub.last_error


@pytest.mark.asyncio
async def test_retry_eventually_succeeds(client, monkeypatch):
    calls = {"n": 0}

    async def flaky(platform, text, image_url):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"ok": False, "error": "502 bad gateway"}
        return {"ok": True, "post_id": "p1", "post_url": "https://ig/p1"}

    monkeypatch.setattr(nexus_core, "_publish_one", flaky)
    pub_id = await pq.enqueue("instagram", "текст")

    await pq.attempt(pub_id)
    await pq.retry_now(pub_id)

    pub = await _get(pub_id)
    assert pub.status == pq.PUBLISHED
    assert pub.post_url == "https://ig/p1"
    assert pub.attempts == 2
    assert pub.next_retry_at is None


@pytest.mark.asyncio
async def test_permanent_refusal_is_not_retried(client, monkeypatch):
    """Нет прав у API — повторять бессмысленно, это не временный сбой."""
    async def blocked(platform, text, image_url):
        return {"ok": False, "blocked_by_api": True,
                "error": "YouTube: загрузка требует OAuth-права youtube.upload"}

    monkeypatch.setattr(nexus_core, "_publish_one", blocked)
    pub_id = await pq.enqueue("youtube", "текст")
    await pq.attempt(pub_id)

    pub = await _get(pub_id)
    assert pub.status == pq.BLOCKED
    assert pub.next_retry_at is None
    assert "OAuth" in pub.last_error
    assert await pq.due() == []               # очередь его больше не трогает


@pytest.mark.asyncio
async def test_unconfigured_telegram_is_blocked_not_retried(client, monkeypatch):
    """Найдено живой проверкой: без токена Telegram уходил в браузерный путь,
    возвращал «нет браузерного сценария» и очередь пять раз повторяла заведомо
    безнадёжную публикацию. Telegram — свой бот, браузером не подменяется."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    pub_id = await pq.enqueue("telegram", "текст")
    await pq.attempt(pub_id)

    pub = await _get(pub_id)
    assert pub.status == pq.BLOCKED
    assert "не настроена" in pub.last_error
    assert "браузерн" not in pub.last_error.lower()   # причина по существу, а не подмена
    assert await pq.due() == []


@pytest.mark.asyncio
async def test_missing_browser_flow_is_permanent(client, monkeypatch):
    """Отсутствие браузерного сценария само не пройдёт — повторять нечего."""
    async def no_flow(platform, text, image_url):
        return {"ok": False, "error": "Нет браузерного сценария для платформы 'vk'."}

    monkeypatch.setattr(nexus_core, "_publish_one", no_flow)
    pub_id = await pq.enqueue("vk", "текст")
    await pq.attempt(pub_id)

    assert (await _get(pub_id)).status == pq.BLOCKED


@pytest.mark.asyncio
async def test_attempts_are_capped(client, monkeypatch):
    async def always_down(platform, text, image_url):
        return {"ok": False, "error": "connection reset"}

    monkeypatch.setattr(nexus_core, "_publish_one", always_down)
    pub_id = await pq.enqueue("telegram", "текст")

    for _ in range(pq.MAX_ATTEMPTS):
        await pq.retry_now(pub_id)

    pub = await _get(pub_id)
    assert pub.status == pq.FAILED
    assert pub.attempts == pq.MAX_ATTEMPTS
    assert pub.next_retry_at is None


@pytest.mark.asyncio
async def test_scheduled_post_waits_for_its_time(client, monkeypatch):
    """Пост на 19:00 не должен уйти в 10:00."""
    async def ok(platform, text, image_url):
        return {"ok": True, "post_id": "x"}

    monkeypatch.setattr(nexus_core, "_publish_one", ok)
    later = await pq.enqueue("telegram", "поздний", when=datetime.utcnow() + timedelta(hours=3))
    now = await pq.enqueue("telegram", "сейчас")

    picked = await pq.due()
    assert now in picked
    assert later not in picked

    stats = await pq.process_due()
    assert stats["published"] == 1
    assert (await _get(later)).status == pq.SCHEDULED


@pytest.mark.asyncio
async def test_cancel_removes_from_queue(client):
    pub_id = await pq.enqueue("telegram", "текст")
    assert await pq.cancel(pub_id) is True
    assert (await _get(pub_id)).status == pq.CANCELLED
    assert await pq.due() == []
    assert await pq.cancel(pub_id) is False   # повторная отмена — уже нечего


@pytest.mark.asyncio
async def test_api_shows_queue_and_retries(auth_client, monkeypatch):
    async def down(platform, text, image_url):
        return {"ok": False, "error": "timeout"}

    monkeypatch.setattr(nexus_core, "_publish_one", down)

    r = await auth_client.post("/api/publish/schedule",
                               json={"platform": "instagram", "text": "пост"})
    assert r.json()["ok"] is True
    pub_id = r.json()["publication_id"]

    await auth_client.post("/api/publish/process")

    r = await auth_client.get("/api/publish/queue")
    body = r.json()
    item = next(i for i in body["items"] if i["id"] == pub_id)
    assert item["status"] == pq.RETRYING
    assert item["attempts"] == 1
    assert body["stats"].get(pq.RETRYING) == 1


@pytest.mark.asyncio
async def test_queue_requires_auth(client):
    r = await client.get("/api/publish/queue")
    assert r.status_code in (401, 403)
