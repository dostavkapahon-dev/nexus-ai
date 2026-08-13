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


# Токены в тестах должны быть правдоподобной длины: проверка вставленной строки
# отклоняет короткие, и это правильное поведение — заглушки под него подстраиваем.
IG_TOKEN = "IGAA" + "x" * 120
FB_TOKEN = "EAA" + "y" * 120

IG_LOGIN_OK = {"id": "17841400999", "username": "pahon_ai"}
FB_PAGES_OK = {"data": [{"name": "Pakhon Studio",
                         "instagram_business_account": {"id": "17841400111"}}]}


@pytest.mark.asyncio
async def test_instagram_login_token_is_detected(client, routes, monkeypatch):
    routes["routes"] = {"graph.instagram.com/me": IG_LOGIN_OK}
    res = await ic.connect(IG_TOKEN)

    assert res["ok"] is True
    assert res["type"] == "instagram"
    assert res["account_id"] == "17841400999"
    assert res["username"] == "pahon_ai"
    assert "refresh_access_token" in res["note"]


@pytest.mark.asyncio
async def test_facebook_token_is_detected(client, routes):
    routes["routes"] = {"graph.instagram.com/me": {"error": {"message": "нет"}},
                        "me/accounts": FB_PAGES_OK}
    res = await ic.connect(FB_TOKEN)

    assert res["ok"] is True
    assert res["type"] == "facebook"
    assert res["account_id"] == "17841400111"
    assert "fb_exchange_token" in res["note"]


@pytest.mark.asyncio
async def test_token_type_is_saved_for_future_refresh(client, routes):
    """Без сохранённого типа продление через 60 дней пойдёт не тем способом."""
    routes["routes"] = {"graph.instagram.com/me": IG_LOGIN_OK}
    await ic.connect(IG_TOKEN)

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
    res = await ic.connect("EAA" + "z" * 100)   # правдоподобный, но не принятый Meta
    assert res["ok"] is False
    assert "новый" in res["error"]


@pytest.mark.asyncio
async def test_page_without_instagram_is_a_different_problem(client, routes):
    """«Страница есть, Instagram не привязан» — не то же, что «токен не подошёл»."""
    routes["routes"] = {"graph.instagram.com/me": {"error": {"message": "нет"}},
                        "me/accounts": {"data": [{"name": "Просто страница"}]}}
    res = await ic.connect(FB_TOKEN)
    assert res["ok"] is False
    assert "не привязан" in res["error"]


@pytest.mark.asyncio
async def test_manual_account_id_wins(client, routes):
    routes["routes"] = {"graph.instagram.com/me": {"error": {"message": "нет"}},
                        "me/accounts": {"data": [{"name": "Страница"}]}}
    res = await ic.connect(FB_TOKEN, account_id="17841400777")
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
                               json={"access_token": IG_TOKEN})
    body = r.json()
    assert body["ok"] is True and body["type"] == "instagram"


@pytest.mark.asyncio
async def test_connect_requires_auth(client):
    r = await client.post("/api/social/instagram/connect", json={"access_token": "x"})
    assert r.status_code in (401, 403)


# ──────────── диагностика вставленной строки ────────────
# «Invalid OAuth access token - Cannot parse access token» — самый частый ответ
# Meta, и по нему невозможно понять, что именно не так со вставленной строкой.

def test_line_breaks_from_copying_are_removed():
    """Панель Meta переносит длинный токен по строкам — переводы копируются с ним."""
    raw = "IGAA" + "x" * 40 + "\n" + "y" * 40 + "  \n"
    assert ic.clean_token(raw) == "IGAA" + "x" * 40 + "y" * 40


def test_quotes_are_stripped():
    assert ic.clean_token('"IGAA' + "z" * 60 + '"').startswith("IGAA")


def test_app_id_is_named_as_such():
    assert "App ID" in ic.diagnose("1234567890")


def test_app_secret_is_named_as_such():
    assert "App Secret" in ic.diagnose("a1b2c3d4e5f60718293a4b5c6d7e8f90")


def test_truncated_token_is_detected():
    msg = ic.diagnose("IGAAxxxxxxxxxxxxxxxxxxxx…xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    assert "не полностью" in msg


def test_short_string_is_detected():
    assert "слишком короткая" in ic.diagnose("IGAAshort")


def test_unexpected_prefix_is_reported():
    msg = ic.diagnose("EAAB" .replace("EAA", "XYZ") + "q" * 80)
    assert "начинается" in msg


def test_valid_looking_token_passes_diagnosis():
    assert ic.diagnose("IGAA" + "a" * 120) is None
    assert ic.diagnose("EAA" + "b" * 120) is None


@pytest.mark.asyncio
async def test_pasted_app_id_never_reaches_meta(client, routes):
    """Заведомо неверную строку не отправляем в Meta — ответ был бы невнятным."""
    routes["routes"] = {}
    res = await ic.connect("1234567890")
    assert res["ok"] is False
    assert "App ID" in res["error"]
    assert routes["seen"] == []          # запроса к Meta не было


@pytest.mark.asyncio
async def test_token_with_line_breaks_is_accepted(client, routes):
    """Именно этот случай и даёт «Cannot parse access token»."""
    routes["routes"] = {"graph.instagram.com/me": IG_LOGIN_OK}
    res = await ic.connect("IGAA" + "x" * 60 + "\n  " + "y" * 60)
    assert res["ok"] is True


# ──────────── токен Страницы Facebook ────────────
# Graph API Explorer выдаёт именно Page Access Token, и старый интерфейс просил
# ровно его. У такого токена нет «списка страниц»: /me/accounts отвечает ошибкой,
# и раньше рабочий токен получал «Meta не приняла токен».

PAGE_TOKEN = "EAA" + "p" * 120


@pytest.mark.asyncio
async def test_page_access_token_is_accepted(client, routes):
    routes["routes"] = {
        "graph.instagram.com/me": {"error": {"message": "нет"}},
        "me/accounts": {"error": {"message": "(#100) Tried accessing nonexisting field"}},
        "/me": {"name": "Pakhon Studio",
                "instagram_business_account": {"id": "17841400555"}},
    }
    res = await ic.connect(PAGE_TOKEN)

    assert res["ok"] is True
    assert res["type"] == "facebook"
    assert res["account_id"] == "17841400555"
    assert res["page"] == "Pakhon Studio"


@pytest.mark.asyncio
async def test_page_token_without_linked_instagram_says_so(client, routes):
    """«Instagram не привязан» — не то же, что «токен не подошёл»."""
    routes["routes"] = {
        "graph.instagram.com/me": {"error": {"message": "нет"}},
        "me/accounts": {"error": {"message": "нельзя"}},
        "/me": {"name": "Просто страница"},
    }
    res = await ic.connect(PAGE_TOKEN)
    assert res["ok"] is False
    assert "не привязан" in res["error"]


@pytest.mark.asyncio
async def test_truly_dead_token_still_rejected(client, routes):
    """Оба запроса отклонены — значит, токен действительно нерабочий."""
    routes["routes"] = {
        "graph.instagram.com/me": {"error": {"message": "invalid"}},
        "me/accounts": {"error": {"message": "invalid"}},
        "/me": {"error": {"message": "Invalid OAuth access token"}},
    }
    res = await ic.connect(PAGE_TOKEN)
    assert res["ok"] is False
    assert "новый" in res["error"]


def test_fingerprint_never_leaks_the_token():
    """Приметы нужны для диагностики, но сам секрет в них попадать не должен."""
    token = "IGAA" + "S3CR3T" * 30
    fp = ic.fingerprint(token)
    assert "S3CR3TS3CR3T" not in fp          # тела токена нет
    assert str(len(token)) in fp             # длина есть
    assert fp.startswith("начинается с «IGAAS3CR")


def test_fingerprint_flags_short_string():
    assert "подозрительно коротко" in ic.fingerprint("IGAA" + "x" * 60)
    assert "подозрительно коротко" not in ic.fingerprint("IGAA" + "x" * 200)


@pytest.mark.asyncio
async def test_rejection_includes_fingerprint(client, routes):
    """«Meta не приняла токен» одинаково для обрезанной строки, чужого приложения
    и просрочки — приметы позволяют различить это без переписки."""
    routes["routes"] = {"graph.instagram.com/me": {"error": {"message": "invalid"}},
                        "me/accounts": {"error": {"message": "invalid"}},
                        "/me": {"error": {"message": "Cannot parse access token"}}}
    res = await ic.connect("IGAA" + "z" * 120)
    assert res["ok"] is False
    assert "длина 124" in res["token_looks_like"]


# ── Проверка ключа на странице «Ключи» ────────────────────────────────────────
# Именно здесь жил самый дорогой по времени дефект: рабочий токен IGAA…
# проверялся на graph.facebook.com, где он не токен вовсе, и Meta отвечала
# «Cannot parse access token». Пользователь трижды менял исправный ключ.

@pytest.mark.asyncio
async def test_ig_login_token_is_checked_on_instagram_api(auth_client, routes):
    routes["routes"] = {"graph.instagram.com/v21.0/me": IG_LOGIN_OK,
                        "graph.facebook.com": {"error": {
                            "message": "Invalid OAuth access token - Cannot parse access token"}}}

    r = await auth_client.post("/api/connections/test",
                               json={"instagram_access_token": IG_TOKEN})
    res = r.json()["instagram_access_token"]

    assert res["ok"] is True, "токен Instagram Login проверен не на своём API"
    assert "pahon_ai" in res["message"]
    assert not any("graph.facebook.com" in u for u in routes["seen"])


@pytest.mark.asyncio
async def test_facebook_token_still_checked_on_facebook(auth_client, routes):
    routes["routes"] = {"graph.facebook.com": {"id": "1", "name": "Pakhon Studio"}}

    r = await auth_client.post("/api/connections/test",
                               json={"instagram_access_token": FB_TOKEN})

    assert r.json()["instagram_access_token"]["ok"] is True
    assert any("graph.facebook.com" in u for u in routes["seen"])


@pytest.mark.asyncio
async def test_pasted_token_is_cleaned_and_typed_on_save(auth_client):
    """Панель Meta переносит токен по строкам — переносы приезжают вместе с ним."""
    import os
    dirty = IG_TOKEN[:60] + "\n  " + IG_TOKEN[60:]

    r = await auth_client.post("/api/connections", json={"instagram_access_token": dirty})
    assert r.json()["ok"] is True

    assert os.environ["INSTAGRAM_ACCESS_TOKEN"] == IG_TOKEN
    assert os.environ["INSTAGRAM_TOKEN_TYPE"] == "instagram"
