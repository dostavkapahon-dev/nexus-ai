"""Настройка целиком из Telegram: чеклист способностей и ввод ключей.

Раньше единственным местом ввода ключей был веб — настроить систему с телефона
было нельзя, а `/diag` отвечал галочками по ключам, а не «умеет ли система
публиковать сама».
"""
import pytest

from core import setup_guide, telegram_bot
from database.db import init_db


# ─────────────────────────── чеклист способностей ───────────────────────────

@pytest.mark.asyncio
async def test_report_covers_every_section():
    await init_db()
    rep = await setup_guide.report()
    assert [s["key"] for s in rep["sections"]] == [k for k, _, _ in setup_guide.SECTIONS]
    assert rep["total"] == len(setup_guide.SECTIONS)
    assert 0 <= rep["ready"] <= rep["total"]


@pytest.mark.asyncio
async def test_missing_brain_names_free_options(monkeypatch):
    """Без моделей человеку нужен не диагноз, а следующий шаг — бесплатный ключ."""
    monkeypatch.setattr("core.ai_router.available_providers", lambda: [])
    section = await setup_guide._brain()
    assert section["status"] == setup_guide.OFF
    keys = [n["key"] for n in section["need"]]
    assert "nvidia_api_key" in keys and "groq_api_key" in keys
    assert all(n["where"] for n in section["need"]), "нужно сказать, где взять ключ"


@pytest.mark.asyncio
async def test_broken_section_does_not_kill_report(monkeypatch):
    """Одна упавшая проверка не должна превращать ответ в трассировку."""
    async def boom():
        raise RuntimeError("провайдер недоступен")

    monkeypatch.setattr(setup_guide, "SECTIONS", (("brain", "Мозг", boom),))
    rep = await setup_guide.report()
    assert rep["sections"][0]["status"] == setup_guide.OFF
    assert "RuntimeError" in rep["sections"][0]["need"][0]["what"]


@pytest.mark.asyncio
async def test_as_text_offers_the_fixing_command():
    await init_db()
    text = setup_guide.as_text(await setup_guide.report())
    assert "/key" in text
    for name, title, _ in setup_guide.SECTIONS:
        assert title in text


@pytest.mark.asyncio
async def test_need_keys_are_real_credential_names():
    """Имя из подсказки должно исполняться командой /key — иначе совет мёртвый."""
    from core import credentials
    await init_db()
    rep = await setup_guide.report()
    for section in rep["sections"]:
        for n in section["need"]:
            if n["key"] != "—":
                assert n["key"] in credentials.BY_KEY, f"{n['key']} нет в credentials"


# ─────────────────────────── секрет не остаётся в переписке ───────────────────

def test_key_with_value_is_treated_as_secret():
    assert telegram_bot.carries_secret("/key groq_api_key gsk_secret")
    assert telegram_bot.carries_secret("/key@nexusbot groq_api_key gsk_secret")


def test_key_without_value_is_help_not_secret():
    """`/key` и `/key имя` — это справка. Удалять её вредно: человек её читает."""
    assert not telegram_bot.carries_secret("/key")
    assert not telegram_bot.carries_secret("/key groq_api_key")
    assert not telegram_bot.carries_secret("/setup")


def test_feed_gets_the_command_without_the_value():
    assert telegram_bot.mask_secret("/key groq_api_key gsk_secret") == "/key groq_api_key •••"
    assert telegram_bot.mask_secret("/setup") == "/setup"
