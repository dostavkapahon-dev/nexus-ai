"""Неработающий браузер экономит память лучше любых флагов — и бесполезен.

Симптом с сервера: «Chromium установлен, но не запускается». Экономные флаги
`--single-process` вместе с `--no-zygote` на многих образах Linux роняют
Chromium сразу после старта. Проверяем: запуск переходит на безопасный набор,
а не сдаётся, и причина по каждому набору остаётся видна.
"""
import pytest

from core import server_browser as sb


@pytest.fixture(autouse=True)
def reset():
    sb._working_args = ""
    sb._context = sb._page = sb._browser = None
    yield
    sb._working_args = ""
    sb._context = sb._page = sb._browser = None


class _Page:
    pass


class _Ctx:
    pages = [_Page()]


def _playwright(monkeypatch, fail_on):
    """fail_on — набор имён флагов, на которых запуск падает."""
    tried = []

    class _Chromium:
        async def launch_persistent_context(self, profile, **opts):
            args = opts["args"]
            tried.append(args)
            if any(flag in args for flag in fail_on):
                raise RuntimeError("Target page, context or browser has been closed")
            return _Ctx()

    class _PW:
        chromium = _Chromium()

    class _Starter:
        async def start(self):
            return _PW()

    monkeypatch.setattr("playwright.async_api.async_playwright", lambda: _Starter())
    monkeypatch.delenv("NEXUS_BROWSER_CDP", raising=False)
    monkeypatch.delenv("BROWSER_PATH", raising=False)
    return tried


@pytest.mark.asyncio
async def test_falls_back_to_safe_args(monkeypatch):
    tried = _playwright(monkeypatch, fail_on={"--single-process"})
    page = await sb.ensure_browser()
    assert page is not None
    assert len(tried) == 2, "должен был попробовать второй набор"
    assert "--single-process" not in tried[1]
    assert sb.launch_profile() == "безопасный"


@pytest.mark.asyncio
async def test_economical_set_is_kept_when_it_works(monkeypatch):
    tried = _playwright(monkeypatch, fail_on=set())
    await sb.ensure_browser()
    assert len(tried) == 1
    assert sb.launch_profile() == "экономный"


@pytest.mark.asyncio
async def test_both_failing_names_every_attempt(monkeypatch):
    _playwright(monkeypatch, fail_on={"--no-sandbox"})
    with pytest.raises(RuntimeError) as e:
        await sb.ensure_browser()
    assert "экономный" in str(e.value) and "безопасный" in str(e.value)


@pytest.mark.asyncio
async def test_known_good_set_is_not_re_probed(monkeypatch):
    sb._working_args = "безопасный"
    tried = _playwright(monkeypatch, fail_on=set())
    await sb.ensure_browser()
    assert len(tried) == 1 and "--single-process" not in tried[0]
