"""Разбор ссылки без данных — отказ, а не сочинение (ТЗ §26).

Раньше результат разбора уходил в модель, даже когда ни одна ссылка не
открылась. Модель уверенно объясняла, почему «зашли» ролики, которых система не
видела, и это сохранялось в память как рецепт. Выдуманный анализ хуже отказа:
по нему потом делается контент.
"""
import json

import pytest

from core import viral_research as vr


BROKEN = {"meta": {"ok": False, "error": "login required"}}
GOOD = {"meta": {"ok": True, "title": "Кофе за 30 секунд", "views": 120000,
                 "url": "https://x/1"},
        "vision": "крупный план, быстрый монтаж"}


@pytest.fixture
def no_model(monkeypatch):
    """Модель не должна вызываться вовсе, когда разбирать нечего."""
    def boom(*a, **k):
        raise AssertionError("модель не должна вызываться без данных")

    monkeypatch.setattr("core.ai_router.ai_router.call", boom)


@pytest.mark.asyncio
async def test_no_readable_links_is_an_honest_refusal(client, monkeypatch, no_model):
    async def broken(url, with_vision=True):
        return BROKEN

    monkeypatch.setattr(vr, "analyze_reference", broken)

    res = await vr.research(["https://instagram.com/reel/x"], niche="кофе")

    assert res["ok"] is False
    assert "ни одну ссылку" in res["error"]
    assert not res["why_viral"] and not res["recipe"]


@pytest.mark.asyncio
async def test_refusal_names_the_reason_and_the_fix(client, monkeypatch, no_model):
    async def broken(url, with_vision=True):
        return BROKEN

    monkeypatch.setattr(vr, "analyze_reference", broken)

    res = await vr.research(["https://instagram.com/reel/x"])

    assert any("login required" in d for d in res["details"])
    assert "браузер" in res["hint"].lower()


@pytest.mark.asyncio
async def test_partial_data_is_analysed_and_the_gap_is_reported(client, monkeypatch):
    """Часть ссылок открылась — разбираем их, но молчать о пропущенных нельзя."""
    seq = iter([GOOD, BROKEN])

    async def mixed(url, with_vision=True):
        return next(seq)

    sent = {}

    async def call(model, system, prompt):
        sent["prompt"] = prompt
        return {"text": json.dumps({"why_viral": ["быстрый монтаж"], "recipe": "делай так"})}

    monkeypatch.setattr(vr, "analyze_reference", mixed)
    monkeypatch.setattr("core.ai_router.ai_router.call", call)

    res = await vr.research(["https://x/1", "https://x/2"])

    assert res["ok"] is True
    assert res["skipped"] == 1
    assert "login required" not in sent["prompt"], "в модель уходят только живые данные"


def test_vision_error_is_not_data():
    """Строка «vision error: …» — это сообщение о сбое, а не разбор кадра."""
    assert vr._has_data({"meta": {"ok": False}, "vision": "vision error: timeout"}) is False
    assert vr._has_data({"meta": {"ok": False}, "vision": "в кадре бариста"}) is True
    assert vr._has_data({"meta": {"ok": True}}) is True


@pytest.mark.asyncio
async def test_telegram_does_not_print_recipe_header_over_nothing(client, monkeypatch):
    """Заголовок «Рецепт вируса» над пустотой читается как выполненный разбор."""
    from core import telegram_bot as tb

    sent = []
    monkeypatch.setattr(tb, "send_message",
                        lambda chat, text, **kw: sent.append(text) or _none())

    async def refusal(urls, niche=""):
        return {"ok": False, "error": "ни одну ссылку не удалось прочитать",
                "details": ["https://x: login required"], "hint": "нужен браузер",
                "why_viral": [], "recipe": ""}

    monkeypatch.setattr("core.viral_research.research", refusal)

    await tb._handle_command("1", "/viral https://instagram.com/reel/x")

    body = "\n".join(sent)
    assert "Рецепт вируса" not in body
    assert "login required" in body


async def _none():
    return None
