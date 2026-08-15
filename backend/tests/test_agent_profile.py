"""
Профиль Главного агента.

Смысл проверок: настройки пользователя должны реально доходить до модели.
Раньше ниша, цели и ограничения лежали в базе, а дирижёр работал по промпту,
зашитому под одну студию, и про них не знал.
"""
import pytest
import pytest_asyncio
from sqlalchemy import delete

from core import agent_profile as ap
from database.db import AsyncSessionLocal
from database.models import AgentProfile, Niche, UserProfile


@pytest_asyncio.fixture(autouse=True)
async def _clean_profile(client):
    """Профиль — singleton на всю систему, поэтому тесты обязаны начинать с чистого:
    иначе одна проверка видит настройки, оставленные другой."""
    async def wipe():
        async with AsyncSessionLocal() as db:
            for model in (AgentProfile, Niche, UserProfile):
                await db.execute(delete(model))
            await db.commit()
        ap.invalidate()

    await wipe()
    yield
    await wipe()


@pytest.mark.asyncio
async def test_empty_profile_does_not_break_prompt(client):
    assert await ap.as_prompt() == ""


@pytest.mark.asyncio
async def test_saved_profile_reaches_the_prompt(client):
    await ap.save({
        "niche": "доставка еды", "brand_name": "Пахон", "goals": "продажи через контент",
        "audience": "жители Алматы 25-40", "tone_of_voice": "дружелюбный",
        "platforms": ["instagram", "telegram"], "posts_per_day": 2,
        "rules": "всегда указывать цену", "constraints": "никогда не обещать сроки доставки",
    })
    text = await ap.as_prompt()
    assert "доставка еды" in text
    assert "всегда указывать цену" in text
    assert "никогда не обещать сроки доставки" in text
    assert "instagram, telegram" in text
    # Пустые поля не выводим: «Стратегия:» без содержимого только сбивает модель.
    assert "Стратегия:" not in text


@pytest.mark.asyncio
async def test_profile_goes_into_director_system_prompt(client):
    from core.marketing_director import _full_system

    await ap.save({"niche": "барбершоп", "constraints": "без скидок"})
    system = await _full_system()
    assert "барбершоп" in system and "без скидок" in system
    # Профиль идёт первым: пользовательские правила важнее общих, зашитых в код.
    assert system.index("барбершоп") < system.index("ИНСТРУМЕНТЫ ДИРЕКТОРА")


@pytest.mark.asyncio
async def test_brand_facts_follow_profile(client):
    from core.brand import brand_facts, system_prompt

    before = await brand_facts()
    assert before["name"]                      # дефолт есть и без профиля

    await ap.save({"brand_name": "Моя студия", "brand_location": "Астана",
                   "niche": "мебель"})
    facts = await brand_facts()
    assert facts == {"name": "Моя студия", "location": "Астана", "niche": "мебель"}
    assert "Моя студия" in await system_prompt()


@pytest.mark.asyncio
async def test_bootstrap_takes_old_settings(client):
    """Настройки, введённые до появления профиля, не должны пропасть."""
    async with AsyncSessionLocal() as db:
        db.add(Niche(name="цветочный магазин", city="Алматы", platforms=["telegram"],
                     posts_per_day=3, tone_of_voice="тёплый", about_user="женщины 30+",
                     status="active"))
        db.add(UserProfile(product_description="букеты на заказ", brand_style="пастель",
                           strategy_focus="sales"))
        await db.commit()

    ap.invalidate()
    profile = await ap.bootstrap()
    assert profile["niche"] == "цветочный магазин"
    assert profile["platforms"] == ["telegram"] and profile["posts_per_day"] == 3
    assert profile["audience"] == "женщины 30+"
    assert profile["goals"] == "sales"

    # Повторный вызов не затирает то, что пользователь уже поправил руками.
    await ap.save({"niche": "исправлено вручную"})
    again = await ap.bootstrap()
    assert again["niche"] == "исправлено вручную"


@pytest.mark.asyncio
async def test_api_roundtrip_and_preview(auth_client):
    r = await auth_client.put("/api/agent-profile", json={"niche": "автосервис",
                                                          "goals": "заявки"})
    assert r.json()["ok"] is True

    got = (await auth_client.get("/api/agent-profile")).json()
    assert got["niche"] == "автосервис"

    preview = (await auth_client.get("/api/agent-profile/preview")).json()
    assert preview["empty"] is False and "автосервис" in preview["prompt"]
