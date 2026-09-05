"""Из контент-плана должна создаваться публикация — одним нажатием.

Раньше пункт плана запускался только командой `/generate <UUID>`. Такое никто
не наберёт, и план оставался списком, из которого ничего не создать.
"""
import pytest
from sqlalchemy import select

from core import intent, telegram_bot as tg
from database.db import AsyncSessionLocal
from database.models import ContentPlan, Niche


async def _plan_item(topic="Как мы возим за час", day=1):
    async with AsyncSessionLocal() as db:
        for old in (await db.execute(select(ContentPlan))).scalars():
            await db.delete(old)
        niche = Niche(name="Доставка", status="active", platforms=["telegram"])
        db.add(niche)
        await db.flush()
        item = ContentPlan(niche_id=niche.id, day_number=day, platform="telegram",
                           topic=topic, hook="хук", status="pending")
        db.add(item)
        await db.commit()
        return item.id


@pytest.mark.asyncio
async def test_plan_offers_a_button_for_each_item(client, monkeypatch):
    plan_id = await _plan_item()
    sent = []

    async def fake_send(chat_id, text, parse_mode="HTML", reply_markup=None, feed=False):
        sent.append((text, reply_markup))
        return {}

    monkeypatch.setattr(tg, "send_message", fake_send)

    await tg._dispatch_command("55", "/plan")

    text, markup = sent[-1]
    assert markup, "у пункта плана должна быть кнопка запуска"
    codes = [b["callback_data"] for row in markup["inline_keyboard"] for b in row]
    assert f"genplan_{plan_id}" in codes


@pytest.mark.asyncio
async def test_button_starts_generation_for_that_item(client, monkeypatch):
    plan_id = await _plan_item(topic="Отзыв клиента")
    started = {}

    async def fake_spawn(kind, goal, factory, source="api"):
        started["goal"] = goal
        started["factory"] = factory
        return "TASK-1"

    monkeypatch.setattr("core.task_manager.spawn", fake_spawn)
    monkeypatch.setattr(tg, "send_message", _swallow)

    await tg._dispatch_command("55", f"/genplan_{plan_id}")

    assert "Отзыв клиента" in started["goal"], "запускается именно выбранный пункт"


@pytest.mark.asyncio
async def test_missing_item_says_so_instead_of_silence(client, monkeypatch):
    said = []

    async def fake_send(chat_id, text, parse_mode="HTML", reply_markup=None, feed=False):
        said.append(text)
        return {}

    monkeypatch.setattr(tg, "send_message", fake_send)

    await tg._dispatch_command("55", "/genplan_несуществующий")

    assert said and "не найден" in said[-1]


def test_router_understands_plan_requests():
    """«Создай по плану на понедельник» — про существующий план, а не новый."""
    assert intent.quick_route("создай контент по плану на понедельник") == "/plan"
    assert intent.quick_route("покажи мой план") == "/plan"
    # Составление нового плана осталось отдельной командой.
    assert intent.quick_route("сделай контент план на неделю") == "/plan7"


async def _swallow(chat_id, text, parse_mode="HTML", reply_markup=None, feed=False):
    return {}
