"""Зелёный статус означает подтверждённую работу, а не принятый ключ.

Главная претензия V2.3 (§5, §13, §62): Higgsfield показывает Connected, но
изображение не генерируется. Так и было: статус зеленел по факту авторизации.
«Ключ принят» и «картинка получилась» — разные вещи, и человек читал первое как
второе.
"""
import pytest

from core import health


def _st(**over):
    st = {"mcp_ok": False, "api_ok": True, "browser_agent": False,
          "credits": None, "api_error": "", "mcp_error": ""}
    st.update(over)
    return st


def _wire(monkeypatch, st, last):
    async def fake_status():
        return st

    async def fake_last(hours=24):
        return last

    monkeypatch.setattr("core.hixiit.status", fake_status)
    monkeypatch.setattr("core.hixiit.last_generation", fake_last)


@pytest.mark.asyncio
async def test_failed_generation_is_red_even_with_working_key(monkeypatch):
    """Главный дефект: доступ исправен, генерация падает — это не зелёный."""
    _wire(monkeypatch, _st(), {"state": "failed", "when": "14.09 10:12",
                               "what": "image", "error": "400 Unavailable model"})
    res = await health._probe_hixiit()
    assert res["ok"] is False
    assert "Unavailable model" in res["detail"]


@pytest.mark.asyncio
async def test_failed_generation_still_mentions_access(monkeypatch):
    """Человеку важно знать, что ключ ни при чём."""
    _wire(monkeypatch, _st(), {"state": "failed", "when": "14.09 10:12",
                               "what": "image", "error": "400"})
    assert "доступ есть" in (await health._probe_hixiit())["detail"]


@pytest.mark.asyncio
async def test_untested_generation_is_yellow_not_green(monkeypatch):
    _wire(monkeypatch, _st(), {"state": "never", "when": "", "what": "", "error": ""})
    res = await health._probe_hixiit()
    assert res.get("warn") is True
    assert "не проверялась" in res["detail"]


@pytest.mark.asyncio
async def test_successful_generation_is_green(monkeypatch):
    _wire(monkeypatch, _st(), {"state": "ok", "when": "14.09 11:00",
                               "what": "image", "error": ""})
    res = await health._probe_hixiit()
    assert res["ok"] and not res.get("warn")
    assert "прошла" in res["detail"]


@pytest.mark.asyncio
async def test_no_access_is_red_without_asking_about_generation(monkeypatch):
    called = {"last": False}

    async def fake_status():
        return _st(api_ok=False, api_error="401 Invalid credentials")

    async def fake_last(hours=24):
        called["last"] = True
        return {"state": "never"}

    monkeypatch.setattr("core.hixiit.status", fake_status)
    monkeypatch.setattr("core.hixiit.last_generation", fake_last)
    res = await health._probe_hixiit()
    assert not res["ok"] and "401" in res["detail"]
    assert not called["last"]        # незачем спрашивать, доступа и так нет


@pytest.mark.asyncio
async def test_mcp_access_follows_the_same_rule(monkeypatch):
    """MCP тоже не даёт зелёного сам по себе."""
    _wire(monkeypatch, _st(mcp_ok=True, credits=1200),
          {"state": "failed", "when": "14.09", "what": "image", "error": "сбой"})
    assert not (await health._probe_hixiit())["ok"]
