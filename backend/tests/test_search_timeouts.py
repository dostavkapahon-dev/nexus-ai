"""Медленный источник не должен съедать весь поиск.

Живая проверка вернула «Интернет-поиск — не ответил за 45 секунд». Раньше она
отвечала сразу и называла причину по каждому источнику. Разница — браузерный
источник: он медленный и не был ограничен по времени, поэтому съедал весь срок
вызывающего, а имя зависшего источника терялось.

Второй дефект, более старый: проверка смотрела ключ `results`, а `search`
возвращает `items` — зелёной эта строка не могла стать никогда.
"""
import asyncio

import pytest

from core import websearch as ws
from core import health


@pytest.fixture(autouse=True)
def _no_keys(monkeypatch):
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)


def _slow(seconds):
    async def fn(query, n):
        await asyncio.sleep(seconds)
        return [{"title": "t", "snippet": "s", "url": "https://a.test"}]

    return fn


def _fast(items=None):
    async def fn(query, n):
        return items if items is not None else [
            {"title": "t", "snippet": "s", "url": "https://a.test"}]

    return fn


@pytest.mark.asyncio
async def test_slow_browser_does_not_hang_the_search(monkeypatch):
    monkeypatch.setattr(ws, "_search_ddg", _fast([]))
    monkeypatch.setattr(ws, "_search_browser", _slow(5))
    res = await asyncio.wait_for(ws.search("тест", 1, budget=0.2), timeout=3)
    assert not res["ok"]


@pytest.mark.asyncio
async def test_timeout_names_the_source(monkeypatch):
    """«Не ответил за 45 секунд» не говорит, кто именно завис."""
    monkeypatch.setattr(ws, "_search_ddg", _fast([]))
    monkeypatch.setattr(ws, "_search_browser", _slow(5))
    res = await ws.search("тест", 1, budget=0.2)
    assert "браузер" in res["error"] and "не ответил" in res["error"]


@pytest.mark.asyncio
async def test_slow_source_does_not_block_a_working_one(monkeypatch):
    """Каскад должен дойти до браузера, если http завис."""
    monkeypatch.setattr(ws, "_search_ddg", _slow(30))
    monkeypatch.setattr(ws, "_search_browser", _fast())
    res = await asyncio.wait_for(ws.search("тест", 1, budget=1), timeout=10)
    assert res["ok"] and res["provider"] == "браузер"


@pytest.mark.asyncio
async def test_probe_reads_the_right_key(monkeypatch):
    """Главный старый дефект: проверялся ключ, которого в ответе нет."""
    async def fake_search(query, n, budget=60.0):
        return {"ok": True, "provider": "браузер",
                "items": [{"url": "https://a.test"}]}

    monkeypatch.setattr("core.websearch.search", fake_search)
    res = await health._probe_web()
    assert res["ok"]


@pytest.mark.asyncio
async def test_probe_names_the_provider(monkeypatch):
    async def fake_search(query, n, budget=60.0):
        return {"ok": True, "provider": "браузер", "items": [{"url": "https://a"}]}

    monkeypatch.setattr("core.websearch.search", fake_search)
    assert "браузер" in (await health._probe_web())["detail"]


@pytest.mark.asyncio
async def test_probe_passes_a_short_budget(monkeypatch):
    """Проверке нужен быстрый ответ, а не результат любой ценой."""
    seen = {}

    async def fake_search(query, n, budget=60.0):
        seen["budget"] = budget
        return {"ok": False, "error": "нет источников", "items": []}

    monkeypatch.setattr("core.websearch.search", fake_search)
    await health._probe_web()
    assert seen["budget"] <= 20


@pytest.mark.asyncio
async def test_probe_keeps_the_reason(monkeypatch):
    async def fake_search(query, n, budget=60.0):
        return {"ok": False, "items": [],
                "error": "поиск не дал результатов — браузер: не ответил за 15 с"}

    monkeypatch.setattr("core.websearch.search", fake_search)
    res = await health._probe_web()
    assert "браузер" in res["detail"]


@pytest.mark.asyncio
async def test_budget_is_the_total_not_per_source(monkeypatch):
    """Раньше каждый источник отсчитывал бюджет заново, и «15 с» давали 40."""
    monkeypatch.setattr(ws, "_search_ddg", _slow(30))
    monkeypatch.setattr(ws, "_search_browser", _slow(30))
    loop = asyncio.get_event_loop()
    started = loop.time()
    await ws.search("тест", 1, budget=1)
    assert loop.time() - started < 4
