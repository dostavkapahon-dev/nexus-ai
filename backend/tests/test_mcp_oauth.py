"""Вход в Higgsfield один раз руками — дальше сервер сам.

Официальный MCP авторизует пользователя, а не приложение: ключ и секрет там не
принимаются. Без этого потока MCP оставался «настроен, но не отвечает», и
генерация упиралась в REST, где у ключа нет права на модель.
"""
import json

import pytest

from core import mcp_oauth as oa

META = {
    "issuer": "https://auth.example",
    "authorization_endpoint": "https://auth.example/authorize",
    "token_endpoint": "https://auth.example/token",
    "registration_endpoint": "https://auth.example/register",
    "scopes_supported": ["generate"],
}


@pytest.fixture(autouse=True)
def public(monkeypatch):
    monkeypatch.setenv("NEXUS_PUBLIC_URL", "https://nexus.example")
    monkeypatch.delenv("HIGGSFIELD_MCP_CLIENT_ID", raising=False)


@pytest.fixture
def store(monkeypatch):
    kv = {}

    async def _get(key):
        return kv.get(key, "")

    async def _set(key, value):
        kv[key] = value

    monkeypatch.setattr(oa, "_kv_get", _get)
    monkeypatch.setattr(oa, "_kv_set", _set)
    return kv


def _http(monkeypatch, handler):
    class _R:
        def __init__(self, status, payload):
            self.status_code = status
            self._p = payload

        def json(self):
            return self._p

        @property
        def text(self):
            return json.dumps(self._p)

    class _C:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, **k):
            status, payload = handler("GET", url, None)
            return _R(status, payload)

        async def post(self, url, json=None, data=None, headers=None):
            status, payload = handler("POST", url, data or json)
            return _R(status, payload)

    monkeypatch.setattr("httpx.AsyncClient", _C)


def _normal(method, url, body):
    if url.endswith("/.well-known/oauth-protected-resource"):
        return 200, {"authorization_servers": ["https://auth.example"]}
    if url.endswith("/.well-known/oauth-authorization-server"):
        return 200, META
    if url.endswith("/register"):
        return 200, {"client_id": "client-1"}
    if url.endswith("/token"):
        if (body or {}).get("grant_type") == "refresh_token":
            return 200, {"access_token": "fresh", "refresh_token": "r2"}
        return 200, {"access_token": "tok-1", "refresh_token": "r1",
                     "expires_in": 3600}
    return 404, {}


@pytest.mark.asyncio
async def test_start_returns_a_login_link(monkeypatch, store):
    _http(monkeypatch, _normal)
    res = await oa.start()
    assert res["ok"] and res["url"].startswith("https://auth.example/authorize?")
    assert "code_challenge_method=S256" in res["url"], "PKCE обязателен"
    assert "client-1" in res["url"]


@pytest.mark.asyncio
async def test_secret_never_leaves_us(monkeypatch, store):
    """Наружу уходит отпечаток, сам verifier остаётся на сервере."""
    _http(monkeypatch, _normal)
    res = await oa.start()
    flow = json.loads(store[oa.FLOW_KEY])
    assert flow["verifier"] not in res["url"]


@pytest.mark.asyncio
async def test_without_public_address_we_say_so(monkeypatch, store):
    monkeypatch.delenv("NEXUS_PUBLIC_URL", raising=False)
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    res = await oa.start()
    assert res["ok"] is False and "NEXUS_PUBLIC_URL" in res["error"]


@pytest.mark.asyncio
async def test_finish_stores_the_token(monkeypatch, store):
    _http(monkeypatch, _normal)
    started = await oa.start()
    assert started["ok"]
    state = json.loads(store[oa.FLOW_KEY])["state"]
    res = await oa.finish("code-1", state)
    assert res["ok"] and res["refreshable"] is True
    assert store[oa.TOKEN_KEY] == "tok-1"
    assert store[oa.REFRESH_KEY] == "r1"


@pytest.mark.asyncio
async def test_foreign_request_is_refused(monkeypatch, store):
    """Чужой запрос на адрес возврата — это попытка войти в чужой аккаунт."""
    _http(monkeypatch, _normal)
    await oa.start()
    res = await oa.finish("code-1", "не-тот-state")
    assert res["ok"] is False and "state" in res["error"]
    assert oa.TOKEN_KEY not in store


@pytest.mark.asyncio
async def test_refresh_works_without_the_human(monkeypatch, store):
    _http(monkeypatch, _normal)
    await oa.start()
    state = json.loads(store[oa.FLOW_KEY])["state"]
    await oa.finish("code-1", state)
    res = await oa.refresh()
    assert res["ok"] and store[oa.TOKEN_KEY] == "fresh"


@pytest.mark.asyncio
async def test_refresh_without_a_token_asks_for_a_new_login(store):
    res = await oa.refresh()
    assert res["ok"] is False and "повторный вход" in res["error"]


@pytest.mark.asyncio
async def test_state_tells_the_fact_not_the_token(monkeypatch, store):
    _http(monkeypatch, _normal)
    await oa.start()
    state = json.loads(store[oa.FLOW_KEY])["state"]
    await oa.finish("code-1", state)
    st = await oa.state()
    assert st["connected"] is True
    assert "tok-1" not in json.dumps(st), "значение токена наружу не отдаём"


@pytest.mark.asyncio
async def test_registration_failure_is_explained(monkeypatch, store):
    def broken(method, url, body):
        if url.endswith("/register"):
            return 403, {"error": "registration disabled"}
        return _normal(method, url, body)
    _http(monkeypatch, broken)
    res = await oa.start()
    assert res["ok"] is False and "регистрация клиента отклонена" in res["error"]


@pytest.mark.asyncio
async def test_server_without_resource_metadata_still_works(monkeypatch, store):
    """Часть серверов метаданных ресурса не отдаёт — это не отказ."""
    def partial(method, url, body):
        if url.endswith("/.well-known/oauth-protected-resource"):
            return 404, {}
        return _normal(method, url, body)
    _http(monkeypatch, partial)
    res = await oa.start()
    assert res["ok"] is True
