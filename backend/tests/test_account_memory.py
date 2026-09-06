"""ТЗ §20/§22: разбор аккаунта попадает в память и отвечает на вопросы о нише."""
import pytest
from sqlalchemy import delete

from core import research_store as rs
from database.db import AsyncSessionLocal
from database.models import Research


IG = {
    "ok": True, "platform": "instagram", "handle": "mycafe",
    "followers": 1200, "posts_count": 48, "source": "graph_api",
    "top_posts": [
        {"title": "Кофе с утра", "likes": 300, "comments": 12, "views": 5000},
        {"title": "Новое меню", "likes": 120, "comments": 4},
    ],
}


@pytest.fixture(autouse=True)
async def _clean(client):
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Research))
        await db.commit()
    yield


@pytest.mark.asyncio
async def test_analysis_is_saved_to_memory(client):
    rid = await rs.remember_account(IG)
    assert rid

    items = await rs.history(rs.ACCOUNT_KIND)
    assert len(items) == 1
    assert items[0]["findings"]["followers"] == 1200
    assert items[0]["findings"]["handle"] == "mycafe"
    assert "mycafe" in items[0]["summary"]
    assert "Кофе с утра" in items[0]["summary"]


@pytest.mark.asyncio
async def test_failed_analysis_is_not_remembered(client):
    assert await rs.remember_account({"ok": False, "platform": "instagram",
                                      "error": "нет токена"}) == ""
    assert await rs.history(rs.ACCOUNT_KIND) == []


@pytest.mark.asyncio
async def test_repeat_within_ttl_does_not_spam_history(client):
    """Плановые прогоны идут каждый час — история не должна ими забиваться."""
    assert await rs.remember_account(IG)
    assert await rs.remember_account(IG) == ""
    assert len(await rs.history(rs.ACCOUNT_KIND)) == 1


@pytest.mark.asyncio
async def test_memory_survives_and_reaches_prompts(client):
    """Сохранённый разбор виден и в сводке рынка, и в памяти для ответов."""
    await rs.remember_account(IG)

    mem = await rs.account_memory()
    assert "mycafe" in mem and "1200" in mem

    ctx = await rs.market_context()
    assert "МОИ АККАУНТЫ" in ctx and "mycafe" in ctx


@pytest.mark.asyncio
async def test_account_intelligence_writes_memory(client, monkeypatch):
    """Разбор через social_intel сохраняется сам — вызывающему помнить не надо."""
    from core import social_intel

    async def fake_fetch(handle):
        return IG

    monkeypatch.setattr(social_intel, "_fetch_instagram", fake_fetch)
    monkeypatch.setattr(social_intel, "_handle", lambda p: _async("mycafe"))

    out = await social_intel.get_account_intelligence(["instagram"])
    assert out["accounts"]["instagram"]["ok"]
    assert len(await rs.history(rs.ACCOUNT_KIND)) == 1


def _async(value):
    async def _inner():
        return value
    return _inner()


@pytest.mark.asyncio
async def test_chat_knows_the_niche_from_memory(client, monkeypatch):
    """§22: ниша сохранена — вопрос «какая у меня ниша?» отвечается по памяти."""
    from core import agent_profile, intent

    await agent_profile.save({"niche": "доставка еды", "brand_name": "Пахон"})

    block = await intent.memory_block()
    assert "доставка еды" in block

    seen = {}

    async def fake_call(model, system, prompt):
        seen["system"] = system
        return {"text": "Ваша ниша — доставка еды."}

    from core import ai_router as ar
    monkeypatch.setattr(ar.ai_router, "call", fake_call)
    monkeypatch.setattr(ar, "ai_available", lambda: True)
    monkeypatch.setattr(intent, "memory_block", intent.memory_block)

    reply = await intent.chat_reply("какая у меня ниша?")
    assert "доставка еды" in seen["system"]
    assert reply
