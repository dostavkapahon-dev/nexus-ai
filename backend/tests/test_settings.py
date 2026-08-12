import os

import pytest

from api.routes_settings import mask

KEY = "sk-test-1234567890abcdef"


def test_mask_hides_middle():
    assert mask(KEY) == "sk-t****cdef"


def test_mask_skips_short_and_empty():
    assert mask("short") == ""
    assert mask("") == ""
    assert mask(None) == ""


async def test_save_then_get_returns_masked(auth_client):
    r = await auth_client.post("/api/connections", json={"openai_api_key": KEY})
    assert r.status_code == 200 and r.json() == {"ok": True}

    got = (await auth_client.get("/api/connections")).json()
    assert got["openai_api_key"] == mask(KEY)
    # сырой ключ наружу не уходит
    assert KEY not in str(got)
    # но попадает в окружение процесса — им пользуются ai_router/публикаторы
    assert os.environ["OPENAI_API_KEY"] == KEY


async def test_masked_value_does_not_overwrite_saved_key(auth_client):
    await auth_client.post("/api/connections", json={"gemini_api_key": KEY})
    # фронт присылает обратно маску — она не должна затереть настоящий ключ
    await auth_client.post("/api/connections", json={"gemini_api_key": mask(KEY)})
    assert os.environ["GEMINI_API_KEY"] == KEY
    assert (await auth_client.get("/api/connections")).json()["gemini_api_key"] == mask(KEY)


async def test_update_existing_key(auth_client):
    await auth_client.post("/api/connections", json={"deepseek_api_key": KEY})
    new = "sk-new-0987654321zyxwv"
    await auth_client.post("/api/connections", json={"deepseek_api_key": new})
    assert (await auth_client.get("/api/connections")).json()["deepseek_api_key"] == mask(new)


async def test_env_key_visible_without_db(auth_client, monkeypatch):
    """На бесплатном Render файловая БД обнуляется — ключ из env всё равно виден."""
    monkeypatch.setenv("RUNWAY_API_KEY", KEY)
    assert (await auth_client.get("/api/connections")).json()["runway_api_key"] == mask(KEY)


async def test_connections_requires_auth(client):
    assert (await client.get("/api/connections")).status_code == 401
    assert (await client.post("/api/connections", json={})).status_code == 401


async def test_test_connections_without_keys_is_empty(auth_client, monkeypatch):
    """Без ключей проверка ничего не дёргает во внешний мир."""
    r = await auth_client.post("/api/connections/test", json={})
    assert r.status_code == 200
    for name, res in r.json().items():
        assert set(res) >= {"ok", "message"}, name


async def test_bot_status_reports_missing_token(auth_client):
    r = await auth_client.get("/api/bot/status")
    assert r.status_code == 200
    assert "ok" in r.json() or "configured" in r.json() or r.json()


@pytest.mark.asyncio
async def test_connections_test_works_without_free_provider_keys(auth_client):
    """Найдено пользователем: «cannot access local variable 'httpx'».

    Внутри функции стоял `import httpx` в цикле по бесплатным провайдерам.
    Локальный import делает имя локальным для ВСЕГО тела функции, поэтому если
    цикл не сделал ни одной итерации (ключей нет), любое обращение к httpx ниже
    падало с UnboundLocalError — проверка подключений не работала вовсе.
    """
    r = await auth_client.post("/api/connections/test",
                               json={"telegram_bot_token": "123:fake"})
    assert r.status_code == 200
    body = r.json()
    assert "httpx" not in str(body)          # никакого UnboundLocalError
    assert "telegram_bot_token" in body      # проверка реально дошла до площадки
