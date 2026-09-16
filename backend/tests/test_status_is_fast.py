"""Статус обязан отвечать быстро, даже когда провайдер молчит.

Замер сети с сервера показал: до mcp.higgsfield.ai соединение доходит за
полсекунды, но вызов после этого виснет — там нужен OAuth-вход человека,
которого на хостинге нет. Два вызова по 30 секунд складывались ровно в те 60,
за которые «проверка Higgsfield не ответила»: статус ждал того, чего
дождаться нельзя.
"""
import asyncio

import pytest

from core import hixiit


@pytest.mark.asyncio
async def test_status_does_not_wait_a_minute_for_mcp(monkeypatch):
    monkeypatch.setattr(hixiit, "mcp_configured", lambda: True)
    monkeypatch.setattr(hixiit, "MCP_STATUS_TIMEOUT", 0.05)

    async def hangs(*a, **k):
        await asyncio.sleep(30)

    async def no_browser(quick=False):
        return {"available": False, "where": "", "why": "не проверялся"}

    async def mode():
        return "auto"

    monkeypatch.setattr(hixiit, "_mcp_call", hangs)
    monkeypatch.setattr(hixiit, "unlim_status", hangs)
    monkeypatch.setattr(hixiit, "browser_available", no_browser)
    monkeypatch.setattr(hixiit, "execution_mode", mode)
    monkeypatch.setattr("core.higgsfield.credentials", lambda: None)

    st = await asyncio.wait_for(hixiit.status(), timeout=3.0)
    assert st["mcp_ok"] is False
    assert "не ответил" in st["mcp_error"]


@pytest.mark.asyncio
async def test_timeout_message_names_the_real_cause(monkeypatch):
    """«Не ответил» мало: надо сказать, что вызов не пройдёт без входа."""
    monkeypatch.setattr(hixiit, "mcp_configured", lambda: True)
    monkeypatch.setattr(hixiit, "MCP_STATUS_TIMEOUT", 0.05)

    async def hangs(*a, **k):
        await asyncio.sleep(30)

    async def no_browser(quick=False):
        return {"available": False, "where": "", "why": ""}

    async def mode():
        return "auto"

    monkeypatch.setattr(hixiit, "_mcp_call", hangs)
    monkeypatch.setattr(hixiit, "unlim_status", hangs)
    monkeypatch.setattr(hixiit, "browser_available", no_browser)
    monkeypatch.setattr(hixiit, "execution_mode", mode)
    monkeypatch.setattr("core.higgsfield.credentials", lambda: None)

    st = await hixiit.status()
    assert "OAuth" in st["mcp_error"]


@pytest.mark.asyncio
async def test_working_mcp_still_reports_credits(monkeypatch):
    monkeypatch.setattr(hixiit, "mcp_configured", lambda: True)

    async def balance(tool, args, timeout=30):
        return {"credits": 1041.74, "subscription_plan_type": "ultimate"}

    async def unlim():
        return {"available": False}

    async def no_browser(quick=False):
        return {"available": False, "where": "", "why": ""}

    async def mode():
        return "auto"

    monkeypatch.setattr(hixiit, "_mcp_call", balance)
    monkeypatch.setattr(hixiit, "unlim_status", unlim)
    monkeypatch.setattr(hixiit, "browser_available", no_browser)
    monkeypatch.setattr(hixiit, "execution_mode", mode)
    monkeypatch.setattr("core.higgsfield.credentials", lambda: None)

    st = await hixiit.status()
    assert st["mcp_ok"] is True and st["credits"] == 1041.74
