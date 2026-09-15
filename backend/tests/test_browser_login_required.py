"""Браузер без входа в аккаунт — это не рабочий путь генерации.

С живого сервера: Chromium установлен и стартует, но генерация через сайт всё
равно невозможна — в браузере нет сессии higgsfield.ai. Агент уходил делать
задачу со словами «ты уже залогинен» и тратил десятки шагов, упираясь в форму
входа. Отказ должен наступать сразу и называть, чего не хватает.
"""
import pytest

from core import hixiit


def _cookies(monkeypatch, *domains):
    """Кладём cookies в ту же переменную, из которой их читает браузер."""
    import json
    monkeypatch.setenv("NEXUS_BROWSER_STORAGE_STATE", json.dumps(
        [{"name": "sid", "value": "x", "domain": d} for d in domains]))


def test_no_cookies_means_no_login(monkeypatch):
    monkeypatch.setenv("NEXUS_BROWSER_STORAGE_STATE", "")
    res = hixiit.higgsfield_session()
    assert res["ok"] is False
    assert "NEXUS_BROWSER_STORAGE_STATE" in res["why"]


def test_foreign_cookies_do_not_count(monkeypatch):
    _cookies(monkeypatch, ".instagram.com", ".youtube.com")
    assert hixiit.higgsfield_session()["ok"] is False


def test_higgsfield_cookies_count(monkeypatch):
    _cookies(monkeypatch, ".higgsfield.ai", ".instagram.com")
    res = hixiit.higgsfield_session()
    assert res["ok"] is True and res["domains"] == ["higgsfield.ai"]


def test_subdomain_counts(monkeypatch):
    _cookies(monkeypatch, ".cloud.higgsfield.ai")
    assert hixiit.higgsfield_session()["ok"] is True


def test_broken_browser_module_is_not_a_login(monkeypatch):
    _cookies(monkeypatch, ".higgsfield.ai")

    def boom():
        raise RuntimeError("нет доступа к настройкам")

    monkeypatch.setattr("core.server_browser._storage_state", boom)
    res = hixiit.higgsfield_session()
    assert res["ok"] is False and res["why"]


@pytest.mark.asyncio
async def test_browser_skill_refuses_before_spending_steps(monkeypatch):
    from core import skills

    async def available():
        return {"available": True, "where": "на сервере", "why": ""}

    monkeypatch.setattr(hixiit, "browser_available", available)
    monkeypatch.setattr(hixiit, "higgsfield_session",
                        lambda: {"ok": False, "domains": [], "why": "нет входа"})

    async def agent_must_not_run(*a, **k):
        raise AssertionError("агент не должен запускаться без входа в аккаунт")

    monkeypatch.setattr("core.browser_agent.run_agent", agent_must_not_run)
    res = await skills.higgsfield_via_browser("кадр", kind="image")
    assert res["ok"] is False and res["error"] == "нет входа"


@pytest.mark.asyncio
async def test_generation_names_missing_login_as_the_reason(monkeypatch):
    """В списке путей причина отказа браузера должна быть названа словами."""
    async def available():
        return {"available": True, "where": "на сервере", "why": ""}

    monkeypatch.setattr(hixiit, "browser_available", available)
    monkeypatch.setattr(hixiit, "higgsfield_session",
                        lambda: {"ok": False, "domains": [],
                                 "why": "в браузере нет входа в higgsfield.ai"})
    monkeypatch.setattr(hixiit, "mcp_configured", lambda: False)
    monkeypatch.setattr("core.higgsfield.credentials", lambda: None)

    async def mode():
        return "auto"

    monkeypatch.setattr(hixiit, "execution_mode", mode)
    res = await hixiit._generate_once_raw("кадр", kind="video")
    assert res["ok"] is False
    assert any("нет входа в higgsfield.ai" in t for t in res["tried"])


def _env(monkeypatch, value):
    monkeypatch.setenv("NEXUS_BROWSER_STORAGE_STATE", value)


def test_missing_variable_is_named_as_such(monkeypatch):
    monkeypatch.delenv("NEXUS_BROWSER_STORAGE_STATE", raising=False)
    res = hixiit.higgsfield_session()
    assert res["ok"] is False
    assert "не задана" in res["why"]


def test_unparsable_value_says_what_to_paste(monkeypatch):
    """Cookie-Editor умеет отдавать строку заголовка — это не тот формат."""
    _env(monkeypatch, "session=abc; token=def")
    res = hixiit.higgsfield_session()
    assert res["ok"] is False
    assert "Export as JSON" in res["why"]


def test_cookies_from_another_site_name_the_domains(monkeypatch):
    _env(monkeypatch, '[{"name": "sid", "value": "x", "domain": ".instagram.com"}]')
    res = hixiit.higgsfield_session()
    assert res["ok"] is False
    assert "instagram.com" in res["why"]
    assert "не от higgsfield.ai" in res["why"]


def test_real_higgsfield_cookies_pass(monkeypatch):
    _env(monkeypatch, '[{"name": "sid", "value": "x", "domain": ".higgsfield.ai"}]')
    res = hixiit.higgsfield_session()
    assert res["ok"] is True and res["domains"] == ["higgsfield.ai"]


def test_cookie_values_are_never_printed(monkeypatch):
    """В диагностике не должно быть секретов — только имена доменов."""
    _env(monkeypatch, '[{"name": "sid", "value": "СЕКРЕТ", "domain": ".instagram.com"}]')
    res = hixiit.higgsfield_session()
    assert "СЕКРЕТ" not in res["why"]
