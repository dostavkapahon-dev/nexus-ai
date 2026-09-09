"""
MCP отваливался из-за переименованной функции в пакете `mcp`.

С сервера пришло: `ImportError: cannot import name 'streamablehttp_client' from
'mcp.client.streamable_http'`. Пакет переименовал функцию между версиями
(`streamablehttp_client` → `streamable_http_client`), а requirements допускает
диапазон версий, то есть на сервере может оказаться любая. Код знал только
старое имя — и MCP молча выключался вместе с каталогом моделей и безлимитом.
"""
import sys
import types

import pytest

from core import hixiit


def _fake_module(monkeypatch, **attrs):
    mod = types.ModuleType("mcp.client.streamable_http")
    for k, v in attrs.items():
        setattr(mod, k, v)
    monkeypatch.setitem(sys.modules, "mcp.client.streamable_http", mod)
    return mod


def test_old_name_is_accepted(monkeypatch):
    def old(): ...
    _fake_module(monkeypatch, streamablehttp_client=old)

    assert hixiit._http_client_factory() is old


def test_new_name_is_accepted(monkeypatch):
    """Именно эта версия стоит на сервере."""
    def new(): ...
    _fake_module(monkeypatch, streamable_http_client=new)

    assert hixiit._http_client_factory() is new


def test_old_name_wins_when_both_exist(monkeypatch):
    """Переходная версия: берём то, под что писан остальной код."""
    def old(): ...
    def new(): ...
    _fake_module(monkeypatch, streamablehttp_client=old, streamable_http_client=new)

    assert hixiit._http_client_factory() is old


def test_unknown_naming_says_what_is_actually_there(monkeypatch):
    """Если переименуют снова — сообщение должно называть найденное."""
    def other(): ...
    _fake_module(monkeypatch, some_other_client=other)

    with pytest.raises(ImportError) as e:
        hixiit._http_client_factory()

    assert "some_other_client" in str(e.value), \
        "без списка того, что есть, следующий раз снова придётся гадать"


def test_real_installed_package_is_usable():
    """Тот же пакет, что поедет на сервер: имя должно находиться."""
    assert callable(hixiit._http_client_factory())


# ── как вызывается найденная функция ──────────────────────────────────────────
#
# С сервера пришло второе: `TypeError: streamable_http_client() got an
# unexpected keyword argument 'headers'`. У новой версии сменилась не только
# фамилия функции, но и способ передать заголовки — вместо `headers=` она
# принимает готовый http-клиент, а отдаёт ПАРУ потоков вместо тройки.

class _Streams:
    """Асинхронный контекст, отдающий заданный набор потоков."""

    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *a):
        return False


class _Session:
    def __init__(self, read, write):
        self.read, self.write = read, write

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def initialize(self):
        return None

    async def call_tool(self, tool, args):
        return {"tool": tool, "args": args}


@pytest.fixture
def mcp_env(monkeypatch):
    """Окружение вызова: адрес, токен и подменённая ClientSession."""
    monkeypatch.setenv("HIGGSFIELD_MCP_URL", "https://mcp.example/mcp")
    monkeypatch.setenv("HIGGSFIELD_MCP_TOKEN", "t0ken")
    mcp_mod = types.ModuleType("mcp")
    mcp_mod.ClientSession = _Session
    monkeypatch.setitem(sys.modules, "mcp", mcp_mod)
    monkeypatch.setattr(hixiit, "_unwrap", lambda res: res)


@pytest.mark.asyncio
async def test_old_signature_gets_headers(monkeypatch, mcp_env):
    seen = {}

    def old(url, headers=None):
        seen.update({"url": url, "headers": headers})
        return _Streams(("r", "w", "session-id"))

    monkeypatch.setattr(hixiit, "_http_client_factory", lambda: old)
    res = await hixiit._mcp_call("balance", {})

    assert seen["headers"]["Authorization"] == "Bearer t0ken"
    assert res["tool"] == "balance"


@pytest.mark.asyncio
async def test_new_signature_gets_a_prepared_client(monkeypatch, mcp_env):
    """Заголовки уходят в клиент, а сама функция получает http_client."""
    seen = {}

    def new(url, *, http_client=None, terminate_on_close=True):
        seen["http_client"] = http_client
        return _Streams(("r", "w"))          # пара, а не тройка

    def make_client(headers=None, timeout=None, auth=None):
        seen["headers"] = headers
        return _Streams("http-client")

    http_mod = types.ModuleType("mcp.client.streamable_http")
    http_mod.create_mcp_http_client = make_client
    monkeypatch.setitem(sys.modules, "mcp.client.streamable_http", http_mod)
    monkeypatch.setattr(hixiit, "_http_client_factory", lambda: new)

    res = await hixiit._mcp_call("balance", {})

    assert seen["headers"]["Authorization"] == "Bearer t0ken"
    assert seen["http_client"] == "http-client"
    assert res["tool"] == "balance", "пара потоков должна распаковываться"


@pytest.mark.asyncio
async def test_two_streams_are_unpacked_not_three(monkeypatch, mcp_env):
    """Прежний код требовал ровно три значения и падал на новой версии."""
    def new(url, *, http_client=None, terminate_on_close=True):
        return _Streams(("r", "w"))

    http_mod = types.ModuleType("mcp.client.streamable_http")
    http_mod.create_mcp_http_client = lambda headers=None, **kw: _Streams("c")
    monkeypatch.setitem(sys.modules, "mcp.client.streamable_http", http_mod)
    monkeypatch.setattr(hixiit, "_http_client_factory", lambda: new)

    assert (await hixiit._mcp_call("balance", {}))["tool"] == "balance"
