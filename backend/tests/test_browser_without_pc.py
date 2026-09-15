"""Higgsfield через браузер не должен требовать включённого компьютера.

`send_to_desktop` давно умеет исполнять команды серверным браузером, но путь
отпирался проверкой `desktop_connected()` — и до фолбэка дело не доходило.
Получалось «работает только когда включён мой ПК» при живом облачном браузере.

Здесь же проверяется режим исполнения: человек может потребовать конкретный
путь, и система обязана его соблюдать, а не молча выбрать другой.
"""
import pytest

from core import hixiit


def _logged_in(monkeypatch, yes=True):
    """Вход в аккаунт Higgsfield: без него браузерный путь отказывает сразу.

    Кладём cookies в ту же переменную, из которой их читает сам браузер, —
    подменять внутренние функции незачем.
    """
    monkeypatch.setenv(
        "NEXUS_BROWSER_STORAGE_STATE",
        '[{"name": "sid", "value": "x", "domain": ".higgsfield.ai"}]'
        if yes else "")


def _browser(monkeypatch, desktop=False, server=False):
    monkeypatch.setattr("api.routes_desktop.desktop_connected", lambda: desktop)

    # Подменять надо атрибут пакета: `from core import server_browser` берёт
    # именно его, а не запись в sys.modules, — иначе подмена работает только
    # пока модуль не импортирован соседним тестом.
    monkeypatch.setattr("core.server_browser.enabled", lambda: True)
    monkeypatch.setattr("core.server_browser._cdp_endpoint", lambda: "wss://cdp" if server else "")
    monkeypatch.setattr("core.version.browser_ready", lambda: False)


@pytest.mark.asyncio
async def test_cloud_browser_counts_as_available(monkeypatch):
    _browser(monkeypatch, desktop=False, server=True)
    seen = await hixiit.browser_available()
    assert seen["available"] and seen["where"] == "облако"


@pytest.mark.asyncio
async def test_pc_browser_is_named_as_pc(monkeypatch):
    _browser(monkeypatch, desktop=True, server=False)
    seen = await hixiit.browser_available()
    assert seen["available"] and seen["where"] == "ПК"


@pytest.mark.asyncio
async def test_no_browser_explains_why(monkeypatch):
    _browser(monkeypatch, desktop=False, server=False)
    seen = await hixiit.browser_available()
    assert not seen["available"]
    assert "NEXUS_BROWSER_CDP" in seen["why"]


@pytest.mark.asyncio
async def test_browser_path_accepts_images(monkeypatch):
    """Картинки раньше до браузера не доходили — только видео."""
    _logged_in(monkeypatch)
    _browser(monkeypatch, desktop=False, server=True)
    got = {}

    async def fake_agent(task, start_url=None, max_steps=25):
        got["task"] = task
        return {"status": "done", "summary": "https://cdn.test/pic.png"}

    monkeypatch.setattr("core.browser_agent.run_agent", fake_agent)
    from core.skills import higgsfield_via_browser
    res = await higgsfield_via_browser("шашлык на мангале", kind="image")
    assert res["ok"] and res["kind"] == "image"
    assert "ИЗОБРАЖЕНИЕ" in got["task"]


@pytest.mark.asyncio
async def test_image_prompt_asks_for_unlimited_model(monkeypatch):
    """На сайте действует безлимит — кадр не должен списывать кредиты."""
    _logged_in(monkeypatch)
    _browser(monkeypatch, desktop=False, server=True)
    got = {}

    async def fake_agent(task, start_url=None, max_steps=25):
        got["task"] = task
        return {"status": "done", "summary": "https://cdn.test/pic.png"}

    monkeypatch.setattr("core.browser_agent.run_agent", fake_agent)
    from core.skills import higgsfield_via_browser
    await higgsfield_via_browser("кофе", kind="image")
    assert "Unlimited" in got["task"]


@pytest.mark.asyncio
async def test_browser_refusal_names_the_reason(monkeypatch):
    _browser(monkeypatch, desktop=False, server=False)
    from core.skills import higgsfield_via_browser
    res = await higgsfield_via_browser("кофе", kind="image")
    assert not res["ok"] and "NEXUS_BROWSER_CDP" in res["error"]


@pytest.mark.asyncio
async def test_mode_defaults_to_auto(monkeypatch):
    monkeypatch.delenv("HIGGSFIELD_EXECUTION_MODE", raising=False)
    assert await hixiit.execution_mode() == "auto"


@pytest.mark.asyncio
async def test_mode_can_come_from_env(monkeypatch):
    monkeypatch.setenv("HIGGSFIELD_EXECUTION_MODE", "browser")
    assert await hixiit.execution_mode() == "browser"


@pytest.mark.asyncio
async def test_unknown_mode_falls_back_to_auto(monkeypatch):
    monkeypatch.setenv("HIGGSFIELD_EXECUTION_MODE", "телепатия")
    assert await hixiit.execution_mode() == "auto"


@pytest.mark.asyncio
async def test_browser_mode_skips_mcp_and_rest(monkeypatch):
    """Выбранный человеком путь обязан соблюдаться, а не подменяться молча."""
    _logged_in(monkeypatch)
    monkeypatch.setattr(hixiit, "execution_mode", _const("browser"))
    monkeypatch.setattr(hixiit, "mcp_configured", lambda: True)
    _browser(monkeypatch, desktop=False, server=True)

    async def boom(*a, **kw):
        raise AssertionError("MCP не должен вызываться в режиме browser")

    monkeypatch.setattr(hixiit, "_generate_via_mcp", boom)

    async def fake_browser(prompt, seed=None, max_steps=32, kind="video"):
        return {"ok": True, "url": "https://cdn.test/x.png", "kind": kind}

    monkeypatch.setattr("core.skills.higgsfield_via_browser", fake_browser)
    res = await hixiit._generate_once("кофе", kind="image")
    assert res["ok"] and res["provider"] == "higgsfield_browser"


@pytest.mark.asyncio
async def test_mcp_mode_does_not_fall_through_to_browser(monkeypatch):
    monkeypatch.setattr(hixiit, "execution_mode", _const("mcp"))
    monkeypatch.setattr(hixiit, "mcp_configured", lambda: True)
    _browser(monkeypatch, desktop=False, server=True)

    async def boom(*a, **kw):
        raise RuntimeError("MCP лёг")

    monkeypatch.setattr(hixiit, "_generate_via_mcp", boom)
    res = await hixiit._generate_once("кофе", kind="image", allow_free=False)
    assert not res["ok"]
    assert any("только MCP" in t for t in res["tried"])


def _const(value):
    async def _f():
        return value

    return _f


@pytest.mark.asyncio
async def test_flag_alone_is_not_availability(monkeypatch):
    """NEXUS_SERVER_BROWSER=1 стоит по умолчанию и ничего не доказывает:
    без Chromium и без адреса облака браузера нет."""
    monkeypatch.setattr("api.routes_desktop.desktop_connected", lambda: False)
    monkeypatch.setattr("core.server_browser.enabled", lambda: True)
    monkeypatch.setattr("core.server_browser._cdp_endpoint", lambda: "")
    monkeypatch.setattr("core.version.browser_ready", lambda: False)
    seen = await hixiit.browser_available()
    assert not seen["available"]
    assert "Chromium" in seen["why"]


@pytest.mark.asyncio
async def test_installed_chromium_counts_as_server_browser(monkeypatch):
    monkeypatch.setattr("api.routes_desktop.desktop_connected", lambda: False)
    monkeypatch.setattr("core.server_browser.enabled", lambda: True)
    monkeypatch.setattr("core.server_browser._cdp_endpoint", lambda: "")
    monkeypatch.setattr("core.version.browser_ready", lambda: True)
    # Установленных файлов теперь недостаточно: браузер обязан ещё и стартовать.
    monkeypatch.setattr(hixiit, "_BROWSER_START", None)

    async def starts():
        return True

    monkeypatch.setattr("core.server_browser.ensure_browser", starts)
    seen = await hixiit.browser_available()
    assert seen["available"] and seen["where"] == "на сервере"


@pytest.mark.asyncio
async def test_disabled_by_flag_says_so(monkeypatch):
    monkeypatch.setattr("api.routes_desktop.desktop_connected", lambda: False)
    monkeypatch.setattr("core.server_browser.enabled", lambda: False)
    seen = await hixiit.browser_available()
    assert not seen["available"] and "NEXUS_SERVER_BROWSER" in seen["why"]
