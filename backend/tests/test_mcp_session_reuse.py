"""Одна генерация — одно соединение, а не семь.

Каждый вызов MCP открывал новое соединение и заново проходил initialize().
На одну генерацию приходится подбор модели, каталог безлимита, сам запрос и
опросы готовности — на рукопожатия уходило больше времени, чем на генерацию.
"""
import pytest

from core import hixiit


class _Session:
    def __init__(self, fail_after=None):
        self.calls = []
        self.fail_after = fail_after

    async def call_tool(self, tool, args):
        self.calls.append(tool)
        if self.fail_after is not None and len(self.calls) > self.fail_after:
            raise RuntimeError("соединение закрыто")
        return {"ok": tool}


@pytest.fixture
def sessions(monkeypatch):
    opened = []

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_session():
        s = _Session()
        opened.append(s)
        yield s

    monkeypatch.setattr(hixiit, "_mcp_session", fake_session)
    monkeypatch.setattr(hixiit, "_unwrap", lambda r: r)
    return opened


@pytest.mark.asyncio
async def test_without_scope_every_call_reconnects(sessions):
    await hixiit._mcp_call("balance", {})
    await hixiit._mcp_call("balance", {})
    assert len(sessions) == 2


@pytest.mark.asyncio
async def test_scope_reuses_one_connection(sessions):
    async with hixiit.mcp_scope():
        for _ in range(5):
            await hixiit._mcp_call("jobs_wait", {})
    assert len(sessions) == 1, "пять вызовов — одно соединение"
    assert len(sessions[0].calls) == 5


@pytest.mark.asyncio
async def test_scope_is_released_after_exit(sessions):
    async with hixiit.mcp_scope():
        await hixiit._mcp_call("balance", {})
    await hixiit._mcp_call("balance", {})
    assert len(sessions) == 2, "после выхода общая сессия не должна жить"


@pytest.mark.asyncio
async def test_broken_shared_session_falls_back_instead_of_failing(monkeypatch):
    """Долгая генерация может пережить своё соединение — это не отказ задачи."""
    opened = []
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_session():
        s = _Session(fail_after=1 if not opened else None)
        opened.append(s)
        yield s

    monkeypatch.setattr(hixiit, "_mcp_session", fake_session)
    monkeypatch.setattr(hixiit, "_unwrap", lambda r: r)

    async with hixiit.mcp_scope():
        assert await hixiit._mcp_call("generate_image", {}) == {"ok": "generate_image"}
        # Второй вызов по общей сессии падает — и молча уходит на своё соединение.
        assert await hixiit._mcp_call("jobs_wait", {}) == {"ok": "jobs_wait"}
    assert len(opened) >= 2


@pytest.mark.asyncio
async def test_scope_that_cannot_open_does_not_break_generation(monkeypatch):
    """Не открылась общая сессия — работаем как раньше, по вызову на соединение."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def refuses():
        raise RuntimeError("сеть недоступна")
        yield None

    monkeypatch.setattr(hixiit, "_mcp_session", refuses)
    async with hixiit.mcp_scope() as session:
        assert session is None
