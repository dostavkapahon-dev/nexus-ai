"""Отказ браузера обязан называть причину, а не ронять KeyError.

С живого сервера пришло «Браузер: KeyError: 'screenshot'». Это не причина: так
выглядит попытка прочитать снимок экрана, которого нет, — браузер ответил
отказом, а код взял ключ вслепую.
"""
import pytest

from core import browser_agent, skills


@pytest.mark.asyncio
async def test_missing_screenshot_becomes_a_named_reason(monkeypatch):
    async def refuses(body, timeout=30.0):
        return {"ok": False, "error": "Chromium не запустился: нет памяти"}

    monkeypatch.setattr(browser_agent, "send_to_desktop", refuses)
    with pytest.raises(browser_agent.NoScreenshot) as e:
        await browser_agent._screenshot()
    assert "Chromium не запустился" in str(e.value)


@pytest.mark.asyncio
async def test_silent_refusal_is_still_explained(monkeypatch):
    async def mute(body, timeout=30.0):
        return {"ok": False}

    monkeypatch.setattr(browser_agent, "send_to_desktop", mute)
    with pytest.raises(browser_agent.NoScreenshot) as e:
        await browser_agent._screenshot()
    assert "не смог запуститься" in str(e.value)


@pytest.mark.asyncio
async def test_good_screenshot_passes_through(monkeypatch):
    async def ok(body, timeout=30.0):
        return {"ok": True, "screenshot": "BASE64", "url": "https://x", "width": 1, "height": 2}

    monkeypatch.setattr(browser_agent, "send_to_desktop", ok)
    shot = await browser_agent._screenshot()
    assert shot["screenshot"] == "BASE64"


@pytest.mark.asyncio
async def test_agent_returns_the_reason_instead_of_crashing(monkeypatch):
    monkeypatch.setattr(browser_agent, "vision_provider", lambda: "google")

    async def boom(*a, **k):
        raise browser_agent.NoScreenshot("браузер не отдал снимок экрана: пусто")

    monkeypatch.setattr(browser_agent, "_run_gemini", boom)
    res = await browser_agent.run_agent("сделай кадр")
    assert res["status"] == "error"
    assert "не отдал снимок" in res["error"]


@pytest.mark.asyncio
async def test_reason_reaches_the_user_through_skills(monkeypatch):
    """Текст ошибки терялся по дороге, и наружу шло пустое «Браузер: None»."""
    from core import hixiit

    async def available(*a, **k):
        return {"available": True, "where": "на сервере", "why": ""}

    async def failing_agent(task, start_url=None, max_steps=25, on_step=None):
        return {"status": "error", "error": "браузер не отдал снимок экрана: нет памяти"}

    monkeypatch.setattr(hixiit, "browser_available", available)
    monkeypatch.setattr(hixiit, "higgsfield_session",
                        lambda: {"ok": True, "domains": ["higgsfield.ai"], "why": ""})
    monkeypatch.setattr("core.browser_agent.run_agent", failing_agent)
    res = await skills.higgsfield_via_browser("кадр", kind="image")
    assert res["ok"] is False
    assert "нет памяти" in res["detail"]
