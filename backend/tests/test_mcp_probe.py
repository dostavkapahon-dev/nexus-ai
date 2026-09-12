"""Что именно сломалось в MCP.

«Server returned an error response (code=-32603)» одинаково выглядит и когда
сервер не принял авторизацию, и когда на нём просто нет нужного инструмента.
Чинится это по-разному — токеном, адресом, названием инструмента. Поэтому шаги
проходятся по очереди, и называется первый упавший.
"""
import pytest

from core import hixiit


class _Tool:
    def __init__(self, name):
        self.name = name


class _Listed:
    def __init__(self, names):
        self.tools = [_Tool(n) for n in names]


class _Session:
    """Сессия, которая падает на заданном шаге."""

    def __init__(self, fail_at=None, tools=("balance", "generate_image"), error=None):
        self.fail_at, self._tools = fail_at, tools
        self.error = error or RuntimeError("боль")

    async def list_tools(self):
        if self.fail_at == "tools":
            raise self.error
        return _Listed(self._tools)

    async def call_tool(self, name, args):
        if self.fail_at == "balance":
            raise self.error
        return _Ok()


class _Ok:
    isError = False
    structuredContent = {"credits": 100}
    content = []


def _with_session(monkeypatch, session=None, connect_error=None):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake():
        if connect_error:
            raise connect_error
        yield session

    monkeypatch.setattr(hixiit, "_mcp_session", fake)
    monkeypatch.setenv("HIGGSFIELD_MCP_URL", "https://mcp.example.test/x")


@pytest.mark.asyncio
async def test_probe_ok_when_everything_answers(monkeypatch):
    _with_session(monkeypatch, _Session())
    probe = await hixiit.mcp_probe()
    assert probe["ok"] and probe["stage"] == "ok"
    assert hixiit.probe_verdict(probe) == "MCP работает"


@pytest.mark.asyncio
async def test_connect_failure_is_named_as_connect(monkeypatch):
    _with_session(monkeypatch, connect_error=RuntimeError("connect refused"))
    probe = await hixiit.mcp_probe()
    assert probe["stage"] == "connect" and not probe["ok"]


@pytest.mark.asyncio
async def test_unauthorized_asks_for_token(monkeypatch):
    _with_session(monkeypatch, connect_error=RuntimeError("HTTP 401 unauthorized"))
    probe = await hixiit.mcp_probe()
    assert "HIGGSFIELD_MCP_TOKEN" in hixiit.probe_verdict(probe)


@pytest.mark.asyncio
async def test_missing_tool_is_not_blamed_on_auth(monkeypatch):
    """Рукопожатие прошло — значит ключ ни при чём, и просить токен нельзя."""
    _with_session(monkeypatch, _Session(fail_at="balance", tools=("generate_image",)))
    probe = await hixiit.mcp_probe()
    verdict = hixiit.probe_verdict(probe)
    assert probe["stage"] == "balance"
    assert "balance" in verdict and "generate_image" in verdict
    assert "TOKEN" not in verdict


@pytest.mark.asyncio
async def test_tool_exists_but_call_fails(monkeypatch):
    _with_session(monkeypatch, _Session(fail_at="balance"))
    verdict = hixiit.probe_verdict(await hixiit.mcp_probe())
    assert "отказал сам вызов" in verdict


@pytest.mark.asyncio
async def test_list_tools_failure_is_its_own_stage(monkeypatch):
    _with_session(monkeypatch, _Session(fail_at="tools"))
    probe = await hixiit.mcp_probe()
    assert probe["stage"] == "tools"
    assert "список инструментов" in hixiit.probe_verdict(probe)


@pytest.mark.asyncio
async def test_probe_without_url_does_not_connect(monkeypatch):
    monkeypatch.delenv("HIGGSFIELD_MCP_URL", raising=False)

    def boom():
        raise AssertionError("не должно подключаться без адреса")

    monkeypatch.setattr(hixiit, "_mcp_session", boom)
    probe = await hixiit.mcp_probe()
    assert not probe["ok"] and "HIGGSFIELD_MCP_URL" in probe["error"]


@pytest.mark.asyncio
async def test_probe_error_carries_real_cause(monkeypatch):
    _with_session(monkeypatch, connect_error=RuntimeError("сервер лёг"))
    probe = await hixiit.mcp_probe()
    assert "сервер лёг" in probe["error"]
