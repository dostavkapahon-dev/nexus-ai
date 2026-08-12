"""Прямое подключение Instagram по готовому токену и продление обоих его видов.

У Meta два несовместимых семейства токенов. Применить не тот способ продления —
значит не продлить вовсе: через 60 дней публикация встанет без внятной причины.
Поэтому тип определяется по факту при подключении и запоминается.
"""
import pytest

from core import ig_connect as ic
from connectors.instagram import InstagramConnector


@pytest.fixture(autouse=True)
def _no_env_leak():
    """`_save_key` намеренно пишет ключ в `os.environ` — чтобы он применялся сразу.
    Побочный эффект: подключение в тесте оставляло бы токен всему прогону, и
    соседние тесты начинали ходить в реальный Instagram. Восстанавливаем."""
    import os
    keys = ("INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_ACCOUNT_ID", "INSTAGRAM_TOKEN_TYPE")
    saved = {k: os.environ.get(k) for k in keys}
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeClient:
    """Отвечает по URL — так видно, к какому именно API мы пошли."""

    def __init__(self, routes: dict, seen: list):
        self._routes, self._seen = routes, seen

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None):
        self._seen.append(url)
        for fragment, payload in self._routes.items():
            if fragment in url:
                return FakeResponse(payload)
        return FakeResponse({"error": {"message": "не найдено"}})


@pytest.fixture
def routes(monkeypatch):
    """Подменяет httpx в обоих модулях; возвращает (маршруты, список вызовов)."""
    state = {"routes": {}, "seen": []}

    def factory(*a, **kw):
        return FakeClient(state["routes"], state["seen"])

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return state


IG_LOGIN_OK = {"id": "17841400999", "username": "pahon_ai"}
FB_PAGES_OK = {"data": [{"name": "Pakhon Studio",
                         "instagram_business_account": {"id": "17841400111"}}]}


@pytest.mark.asyncio
async def test_instagram_login_token_is_detected(client, routes, monkeypatch):
    routes["routes"] = {"graph.instagram.com/me": IG_LOGIN_OK}
    res = await ic.connect("IGAAxxxx")

    assert res["ok"] is True
    assert res["type"] == "instagram"
    assert res["account_id"] == "17841400999"
    assert res["username"] == "pahon_ai"
    assert "refresh_access_token" in res["note"]


@pytest.mark.asyncio
async def test_facebook_token_is_detected(client, routes):
    routes["routes"] = {"graph.instagram.com/me": {"error": {"message": "нет"}},
                        "me/accounts": FB_PAGES_OK}
    res = await ic.connect("EAAxxxx")

    assert res["ok"] is True
    assert res["type"] == "facebook"
    assert res["account_id"] == "17841400111"
    assert "fb_exchange_token" in res["note"]


@pytest.mark.asyncio
async def test_token_type_is_saved_for_future_refresh(client, routes):
    """Без сохранённого типа продление через 60 дней пойдёт не тем способом."""
    routes["routes"] = {"graph.instagram.com/me": IG_LOGIN_OK}
    await ic.connect("IGAAxxxx")

    from sqlalchemy import select
    from database.db import AsyncSessionLocal
    from database.models import Connection
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Connection).where(Connection.key_name == ic.TYPE_KEY))
        assert r.scalar_one().key_value == "instagram"


@pytest.mark.asyncio
async def test_bad_token_says_what_to_do(client, routes):
    routes["routes"] = {"graph.instagram.com/me": {"error": {"message": "invalid"}},
                        "me/accounts": {"error": {"message": "invalid"}}}
    res = await ic.connect("мусор")
    assert res["ok"] is False
    assert "новый" in res["error"]


@pytest.mark.asyncio
async def test_page_without_instagram_is_a_different_problem(client, routes):
    """«Страница есть, Instagram не привязан» — не то же, что «токен не подошёл»."""
    routes["routes"] = {"graph.instagram.com/me": {"error": {"message": "нет"}},
                        "me/accounts": {"data": [{"name": "Просто страница"}]}}
    res = await ic.connect("EAAxxxx")
    assert res["ok"] is False
    assert "не привязан" in res["error"]


@pytest.mark.asyncio
async def test_manual_account_id_wins(client, routes):
    routes["routes"] = {"graph.instagram.com/me": {"error": {"message": "нет"}},
                        "me/accounts": {"data": [{"name": "Страница"}]}}
    res = await ic.connect("EAAxxxx", account_id="17841400777")
    assert res["ok"] is True
    assert res["account_id"] == "17841400777"


@pytest.mark.asyncio
async def test_empty_token_rejected(client):
    assert (await ic.connect("   "))["ok"] is False


# ─────────────────────────────── продление ───────────────────────────────

@pytest.mark.asyncio
async def test_instagram_login_token_refreshes_via_graph_instagram(client, routes, monkeypatch):
    """Ключевое: для этого типа нужен graph.instagram.com, а не обмен Facebook."""
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "IGAAold")
    monkeypatch.setenv("INSTAGRAM_ACCOUNT_ID", "1784140")
    monkeypatch.setenv("INSTAGRAM_TOKEN_TYPE", "instagram")
    routes["routes"] = {"refresh_access_token": {"access_token": "IGAAnew",
                                                 "expires_in": 5184000}}

    res = await InstagramConnector().refresh_token()

    assert res["refreshed"] is True
    assert res["method"] == "ig_refresh_token"
    assert res["expires_in_days"] == 60.0
    assert any("graph.instagram.com" in u for u in routes["seen"])


@pytest.mark.asyncio
async def test_facebook_token_still_uses_exchange(client, routes, monkeypatch):
    """Старый путь не должен сломаться — им пользуются подключённые через OAuth."""
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "EAAold")
    monkeypatch.setenv("INSTAGRAM_ACCOUNT_ID", "1784140")
    monkeypatch.setenv("INSTAGRAM_TOKEN_TYPE", "facebook")
    monkeypatch.setenv("FACEBOOK_APP_ID", "111")
    monkeypatch.setenv("FACEBOOK_APP_SECRET", "secret")
    routes["routes"] = {"oauth/access_token": {"access_token": "EAAnew",
                                               "expires_in": 5184000}}

    res = await InstagramConnector().refresh_token()

    assert res["refreshed"] is True
    assert any("graph.facebook.com" in u for u in routes["seen"])


@pytest.mark.asyncio
async def test_expired_token_cannot_be_refreshed_and_says_so(client, routes, monkeypatch):
    """Просроченный токен не восстановить — надо сказать прямо, а не отдать код Meta."""
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "IGAAdead")
    monkeypatch.setenv("INSTAGRAM_ACCOUNT_ID", "1784140")
    monkeypatch.setenv("INSTAGRAM_TOKEN_TYPE", "instagram")
    routes["routes"] = {"refresh_access_token": {"error": {"message": "session expired"}}}

    res = await InstagramConnector().refresh_token()

    assert res["refreshed"] is False
    assert "сгенерируйте новый" in res["hint"]


@pytest.mark.asyncio
async def test_connect_endpoint(auth_client, routes):
    routes["routes"] = {"graph.instagram.com/me": IG_LOGIN_OK}
    r = await auth_client.post("/api/social/instagram/connect",
                               json={"access_token": "IGAAxxxx"})
    body = r.json()
    assert body["ok"] is True and body["type"] == "instagram"


@pytest.mark.asyncio
async def test_connect_requires_auth(client):
    r = await client.post("/api/social/instagram/connect", json={"access_token": "x"})
    assert r.status_code in (401, 403)
