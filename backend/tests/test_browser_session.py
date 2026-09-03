"""Браузерный путь без API-ключей: cookies из расширения и живость сессии.

Пользователь достаёт cookies расширением (Cookie-Editor, EditThisCookie), а те
экспортируют свой формат. Playwright на нём падает целиком — и это ровно та точка,
где путь «без ключей Meta» обычно и умирает.
"""
import json

import pytest

from core import server_browser as sb

# Реальный вид экспорта Cookie-Editor: expirationDate, sameSite "no_restriction",
# плюс поля hostOnly/session/storeId, которых Playwright не знает.
EXTENSION_EXPORT = [
    {"domain": ".instagram.com", "expirationDate": 1799999999.123, "hostOnly": False,
     "httpOnly": True, "name": "sessionid", "path": "/", "sameSite": "no_restriction",
     "secure": True, "session": False, "storeId": "0", "value": "abc123"},
    {"domain": ".instagram.com", "hostOnly": False, "httpOnly": False, "name": "ds_user_id",
     "path": "/", "sameSite": "unspecified", "secure": True, "session": True,
     "storeId": "0", "value": "42"},
]


def test_extension_export_is_accepted(monkeypatch):
    """Массив cookies из расширения — это то, что реально получается у человека."""
    monkeypatch.setenv("NEXUS_BROWSER_STORAGE_STATE", json.dumps(EXTENSION_EXPORT))
    state = sb._storage_state()
    assert state is not None
    assert len(state["cookies"]) == 2
    assert state["origins"] == []


def test_unsupported_fields_are_dropped(monkeypatch):
    """hostOnly/session/storeId роняют add_cookies — их быть не должно."""
    monkeypatch.setenv("NEXUS_BROWSER_STORAGE_STATE", json.dumps(EXTENSION_EXPORT))
    for c in sb._storage_state()["cookies"]:
        assert not ({"hostOnly", "session", "storeId", "expirationDate"} & set(c))


def test_samesite_is_translated():
    """«no_restriction» и «unspecified» — не значения Playwright."""
    cookies = sb.normalize_cookies(EXTENSION_EXPORT)
    assert cookies[0]["sameSite"] == "None"
    assert cookies[1]["sameSite"] == "Lax"
    assert all(c["sameSite"] in ("Strict", "Lax", "None") for c in cookies)


def test_expiration_becomes_int_expires():
    cookies = sb.normalize_cookies(EXTENSION_EXPORT)
    assert cookies[0]["expires"] == 1799999999
    assert "expires" not in cookies[1]      # сессионный cookie срока не имеет


def test_playwright_storage_state_still_works(monkeypatch):
    """Старый формат не должен сломаться — им пользуются те, кто уже настроил."""
    native = {"cookies": [{"name": "a", "value": "b", "domain": ".instagram.com",
                           "path": "/", "sameSite": "Lax"}],
              "origins": [{"origin": "https://www.instagram.com", "localStorage": []}]}
    monkeypatch.setenv("NEXUS_BROWSER_STORAGE_STATE", json.dumps(native))
    state = sb._storage_state()
    assert state["cookies"][0]["name"] == "a"
    assert state["origins"]


def test_garbage_does_not_crash(monkeypatch):
    for bad in ("не json", "{}", "[]", '[{"нет":"имени"}]', '"строка"'):
        monkeypatch.setenv("NEXUS_BROWSER_STORAGE_STATE", bad)
        assert sb._storage_state() is None


def test_cookie_without_domain_is_skipped():
    """Без домена cookie бесполезен и ломает загрузку остальных."""
    assert sb.normalize_cookies([{"name": "x", "value": "1"}]) == []


def test_session_domains_shows_where_we_are_logged_in(monkeypatch):
    monkeypatch.setenv("NEXUS_BROWSER_STORAGE_STATE", json.dumps(EXTENSION_EXPORT))
    assert sb.session_domains() == ["instagram.com"]


@pytest.mark.asyncio
async def test_check_session_without_cookies_says_so(client, monkeypatch):
    """Отказ должен называть причину, а не выглядеть как сбой агента."""
    monkeypatch.delenv("NEXUS_BROWSER_STORAGE_STATE", raising=False)
    res = await sb.check_session("instagram")
    assert res["logged_in"] is False
    assert "cookies" in res["error"]


@pytest.mark.asyncio
async def test_check_session_detects_logged_out(client, monkeypatch):
    """Форма входа на странице — это истёкшая сессия, а не «не смог опубликовать»."""
    monkeypatch.setenv("NEXUS_BROWSER_STORAGE_STATE", json.dumps(EXTENSION_EXPORT))

    async def fake_execute(cmd):
        if cmd["action"] == "navigate":
            return {"ok": True, "url": "https://www.instagram.com/accounts/login/"}
        return {"ok": True, "text": "Войти  Телефон, имя пользователя или эл. адрес"}

    monkeypatch.setattr(sb, "execute", fake_execute)
    res = await sb.check_session("instagram")
    assert res["logged_in"] is False
    assert "сессия истекла" in res["hint"]


@pytest.mark.asyncio
async def test_check_session_detects_logged_in(client, monkeypatch):
    monkeypatch.setenv("NEXUS_BROWSER_STORAGE_STATE", json.dumps(EXTENSION_EXPORT))

    async def fake_execute(cmd):
        if cmd["action"] == "navigate":
            return {"ok": True, "url": "https://www.instagram.com/"}
        return {"ok": True, "text": "Лента  Ваша история  Рекомендации"}

    monkeypatch.setattr(sb, "execute", fake_execute)
    res = await sb.check_session("instagram")
    assert res["logged_in"] is True
    assert res["hint"] is None


@pytest.mark.asyncio
async def test_browser_status_api(auth_client, monkeypatch):
    monkeypatch.setenv("NEXUS_BROWSER_STORAGE_STATE", json.dumps(EXTENSION_EXPORT))
    r = await auth_client.get("/api/social/browser/status")
    body = r.json()
    assert body["has_cookies"] is True
    assert body["domains"] == ["instagram.com"]


def test_missing_chromium_gets_actionable_message():
    """«Executable doesn't exist at /opt/pw-browsers/…» не говорит, что делать."""
    msg = sb.explain_error("BrowserType.launch: Executable doesn't exist at /opt/pw-browsers/x")
    assert "playwright install chromium" in msg
    assert "/opt/pw-browsers" not in msg


def test_out_of_memory_points_at_the_real_limit():
    msg = sb.explain_error("Target page crashed: out of memory")
    assert "памяти" in msg and "NEXUS_BROWSER_CDP" in msg


def test_unknown_error_is_passed_through():
    """Незнакомую ошибку не прячем — иначе потеряем причину."""
    assert "странный сбой" in sb.explain_error("странный сбой площадки")
