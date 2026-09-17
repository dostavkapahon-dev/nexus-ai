"""Ни одна часть статуса не имеет права съесть весь ответ.

Симптом из самопроверки: «check_hixiit — не ответила за 60 секунд». Причина —
живой запрос к платформе шёл по двум адресам по 20 секунд, а сверху ложились
база, браузер и MCP. Проверяем: зависшая часть заменяется honest-ответом, а
статус приходит целиком.
"""
import asyncio

import pytest

from core import hixiit


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(hixiit, "API_STATUS_TIMEOUT", 0.05)
    monkeypatch.setattr(hixiit, "BROWSER_STATUS_TIMEOUT", 0.05)
    monkeypatch.setattr(hixiit, "STORE_STATUS_TIMEOUT", 0.05)
    monkeypatch.setattr(hixiit, "MCP_STATUS_TIMEOUT", 0.05)


async def _hangs():
    await asyncio.sleep(30)


@pytest.mark.asyncio
async def test_within_returns_fallback_instead_of_hanging():
    got = await hixiit._within(_hangs(), 0.05, {"ok": False})
    assert got == {"ok": False}


@pytest.mark.asyncio
async def test_within_passes_the_real_answer_through():
    async def quick():
        return "готово"
    assert await hixiit._within(quick(), 1, "запас") == "готово"


@pytest.mark.asyncio
async def test_status_answers_even_when_every_part_hangs(monkeypatch):
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "3f8c1a2b-4d5e-6f70-8192-a3b4c5d6e7f8")
    monkeypatch.setenv("HIGGSFIELD_SECRET", "8f" * 32)
    monkeypatch.setattr(hixiit, "_key_sources", lambda: _hangs())
    monkeypatch.setattr(hixiit, "browser_available", lambda quick=False: _hangs())
    monkeypatch.setattr(hixiit, "execution_mode", lambda: _hangs())
    monkeypatch.setattr("core.higgsfield.check", lambda: _hangs())

    out = await asyncio.wait_for(hixiit.status(), timeout=5)

    assert out["api_ok"] is False
    assert "не ответила" in out["api_error"]
    assert out["browser_agent"] is False
    assert out["key_sources"] == []
