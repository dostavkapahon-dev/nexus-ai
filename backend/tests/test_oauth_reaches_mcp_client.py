"""Вход по OAuth должен доходить до клиента MCP — и переживать перезапуск.

Проверяется шов, который до сих пор не проверял никто: `mcp_oauth` кладёт токен
в хранилище доступов, а клиент MCP (`core.hixiit`) читает `os.getenv`. Все
прежние тесты подменяли либо хранилище (`_kv_get`/`_kv_set`), либо сам
`mcp_configured` — то есть ровно тот участок, где «вход выполнен, а MCP молчит».
"""
import os

import pytest

from core import credentials, hixiit, mcp_oauth as oa
from database.db import init_db


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("HIGGSFIELD_MCP_URL", raising=False)
    monkeypatch.delenv("HIGGSFIELD_MCP_TOKEN", raising=False)
    yield


@pytest.mark.asyncio
async def test_saved_token_makes_mcp_configured():
    await init_db()
    assert not hixiit.mcp_configured(), "без входа MCP не настроен"

    await credentials.set(oa.TOKEN_KEY, "access-abc")
    try:
        assert hixiit.mcp_url() == hixiit.OFFICIAL_MCP_URL
        assert hixiit.mcp_configured(), (
            "после входа MCP обязан считаться настроенным: токен сохранён")
    finally:
        await credentials.delete(oa.TOKEN_KEY)


@pytest.mark.asyncio
async def test_token_survives_restart():
    """Перезапуск теряет окружение, но не базу: выгрузка обязана вернуть токен."""
    await init_db()
    await credentials.set(oa.TOKEN_KEY, "access-abc")
    try:
        os.environ.pop("HIGGSFIELD_MCP_TOKEN", None)   # рестарт процесса
        assert not hixiit.mcp_configured()

        await credentials.load_into_env()
        assert os.getenv("HIGGSFIELD_MCP_TOKEN") == "access-abc", (
            "токен входа остался в базе и не дошёл до клиента MCP")
        assert hixiit.mcp_configured()
    finally:
        await credentials.delete(oa.TOKEN_KEY)
