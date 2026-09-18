"""OAuth — основной путь: им подключаемся, им и генерируем.

Ключ и секрет ходят по одному адресу и знают одну модель; вход по OAuth
работает от имени человека и видит весь каталог аккаунта, его план и безлимит.
Поэтому при прочих равных первым пробуется он, а ключ остаётся запасным.
"""
import pytest

from core import exec_router, mcp_oauth


@pytest.mark.asyncio
async def test_oauth_goes_first_when_everything_is_available(monkeypatch):
    async def blank():
        return {c: exec_router._blank() for c in exec_router.CHANNELS}

    monkeypatch.setattr(exec_router, "stats", blank)
    rows = await exec_router.order(
        "auto", "auto", configured={"mcp": True, "rest": True, "browser": True})
    assert [r["channel"] for r in rows if r["use"]][0] == "mcp"


@pytest.mark.asyncio
async def test_rest_still_catches_the_task_when_oauth_is_not_connected(monkeypatch):
    async def blank():
        return {c: exec_router._blank() for c in exec_router.CHANNELS}

    monkeypatch.setattr(exec_router, "stats", blank)
    rows = await exec_router.order(
        "auto", "auto", configured={"mcp": False, "rest": True, "browser": True})
    live = [r["channel"] for r in rows if r["use"]]
    assert live and live[0] == "rest"
    mcp = next(r for r in rows if r["channel"] == "mcp")
    assert "/hfconnect" in mcp["why"]


@pytest.mark.asyncio
async def test_oauth_that_keeps_failing_loses_its_head_start(monkeypatch):
    """Преимущество основного пути — не индульгенция: если он не доводит
    задачу до файла, запасной должен идти раньше."""
    async def stats():
        blank = exec_router._blank()
        return {"mcp": {**blank, "ok": 0, "fail": 9},
                "rest": {**blank, "ok": 9, "fail": 0},
                "browser": dict(blank)}

    monkeypatch.setattr(exec_router, "stats", stats)
    rows = await exec_router.order(
        "auto", "auto", configured={"mcp": True, "rest": True, "browser": True})
    assert [r["channel"] for r in rows if r["use"]][0] == "rest"


@pytest.mark.asyncio
async def test_startup_refresh_without_login_does_nothing(monkeypatch):
    async def no_token(key):
        return ""
    monkeypatch.setattr(mcp_oauth, "_kv_get", no_token)
    res = await mcp_oauth.refresh_on_start()
    assert res["ok"] is False and "вход не выполнен" in res["error"]


@pytest.mark.asyncio
async def test_startup_refresh_never_breaks_the_service(monkeypatch):
    async def boom(key):
        raise RuntimeError("база недоступна")
    monkeypatch.setattr(mcp_oauth, "_kv_get", boom)
    res = await mcp_oauth.refresh_on_start()
    assert res["ok"] is False          # но исключение наружу не вышло


@pytest.mark.asyncio
async def test_startup_refresh_renews_the_token(monkeypatch):
    async def has_token(key):
        return "refresh-value"

    async def renewed():
        return {"ok": True, "expires_in": 3600}

    monkeypatch.setattr(mcp_oauth, "_kv_get", has_token)
    monkeypatch.setattr(mcp_oauth, "refresh", renewed)
    assert (await mcp_oauth.refresh_on_start())["ok"] is True


@pytest.mark.asyncio
async def test_explicit_economy_still_decides_for_itself(monkeypatch):
    """Преимущество основного пути работает в «авто». Явный выбор человека —
    дешевле, быстрее, качественнее — сильнее нашего умолчания."""
    async def blank():
        return {c: exec_router._blank() for c in exec_router.CHANNELS}

    monkeypatch.setattr(exec_router, "stats", blank)
    rows = await exec_router.order(
        "auto", "economy", configured={"mcp": True, "rest": True, "browser": True})
    assert [r["channel"] for r in rows if r["use"]][0] == "browser"
