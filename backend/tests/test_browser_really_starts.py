"""Браузер считается доступным, только если он реально запускается.

На хостинге без прав администратора Chromium скачивается, но не стартует:
не хватает системных библиотек. Проверка «папка на месте» в этом случае
показывала зелёное, а задача падала уже в работе — та же болезнь «Connected,
но не работает», что и у Higgsfield.
"""
import pytest

from core import hixiit


@pytest.fixture(autouse=True)
def _forget_cache(monkeypatch):
    monkeypatch.setattr(hixiit, "_BROWSER_START", None)


def _no_desktop(monkeypatch):
    import sys, types
    mod = types.ModuleType("api.routes_desktop")
    mod.desktop_connected = lambda: False
    monkeypatch.setitem(sys.modules, "api.routes_desktop", mod)


@pytest.fixture
def server(monkeypatch):
    from core import server_browser
    monkeypatch.setattr(server_browser, "enabled", lambda: True)
    monkeypatch.setattr(server_browser, "_cdp_endpoint", lambda: "")
    return server_browser


@pytest.mark.asyncio
async def test_files_present_but_browser_fails_is_not_available(monkeypatch, server):
    _no_desktop(monkeypatch)
    monkeypatch.setattr("core.version.browser_ready", lambda: True)

    async def cannot_start():
        raise RuntimeError("error while loading shared libraries: libnss3.so")

    monkeypatch.setattr(server, "ensure_browser", cannot_start)
    res = await hixiit.browser_available()
    assert res["available"] is False
    assert "libnss3" in res["why"]
    assert "NEXUS_BROWSER_CDP" in res["why"]


@pytest.mark.asyncio
async def test_browser_that_starts_is_available(monkeypatch, server):
    _no_desktop(monkeypatch)
    monkeypatch.setattr("core.version.browser_ready", lambda: True)

    async def starts():
        return True

    monkeypatch.setattr(server, "ensure_browser", starts)
    res = await hixiit.browser_available()
    assert res["available"] is True and res["where"] == "на сервере"


@pytest.mark.asyncio
async def test_hanging_browser_is_not_available(monkeypatch, server):
    """Зависший запуск — это отказ, а не бесконечное ожидание."""
    import asyncio

    async def hangs():
        await asyncio.sleep(10)

    monkeypatch.setattr(server, "ensure_browser", hangs)
    res = await hixiit._browser_starts(timeout=0.05)
    assert res["ok"] is False and "не запустился" in res["why"]


@pytest.mark.asyncio
async def test_start_check_runs_once(monkeypatch, server):
    """Запуск браузера дорогой: проверяем один раз за процесс."""
    calls = []

    async def starts():
        calls.append(1)

    monkeypatch.setattr(server, "ensure_browser", starts)
    await hixiit._browser_starts()
    await hixiit._browser_starts()
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_cloud_browser_skips_the_start_check(monkeypatch, server):
    """Облачный браузер проверять запуском незачем — он не наш процесс."""
    _no_desktop(monkeypatch)
    monkeypatch.setattr(server, "_cdp_endpoint", lambda: "ws://cloud")

    async def boom():
        raise AssertionError("не должно вызываться")

    monkeypatch.setattr(server, "ensure_browser", boom)
    res = await hixiit.browser_available()
    assert res["available"] is True and res["where"] == "облако"


@pytest.mark.asyncio
async def test_status_does_not_touch_the_browser(monkeypatch, server):
    """Статус не только не ждёт браузер — он его и не поднимает.

    Chromium забирает память у всего процесса: статус, поднимающий его в фоне,
    и есть причина, по которой сервер начинал таймаутить на обычных запросах.
    """
    import asyncio
    _no_desktop(monkeypatch)
    monkeypatch.setattr("core.version.browser_ready", lambda: True)

    async def must_not_run():
        raise AssertionError("статус не должен поднимать браузер")

    monkeypatch.setattr(server, "ensure_browser", must_not_run)
    res = await asyncio.wait_for(hixiit.browser_available(quick=True), timeout=1.0)
    assert res["available"] is False and res["pending"] is True
    assert "при первой генерации" in res["why"]


@pytest.mark.asyncio
async def test_known_result_is_returned_without_waiting(monkeypatch, server):
    monkeypatch.setattr(hixiit, "_BROWSER_START", {"ok": True, "why": ""})
    _no_desktop(monkeypatch)
    monkeypatch.setattr("core.version.browser_ready", lambda: True)

    async def must_not_run():
        raise AssertionError("повторный запуск не нужен: ответ уже известен")

    monkeypatch.setattr(server, "ensure_browser", must_not_run)
    res = await hixiit.browser_available(quick=True)
    assert res["available"] is True


@pytest.mark.asyncio
async def test_real_work_still_waits_for_the_browser(monkeypatch, server):
    """В работе ждать браузер надо: там нужен сам браузер, а не быстрый ответ."""
    _no_desktop(monkeypatch)
    monkeypatch.setattr("core.version.browser_ready", lambda: True)
    calls = []

    async def starts():
        calls.append(1)

    monkeypatch.setattr(server, "ensure_browser", starts)
    res = await hixiit.browser_available()
    assert res["available"] is True and calls == [1]
