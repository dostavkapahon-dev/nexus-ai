"""Долгая генерация должна быть видна в Telegram и не ждать мёртвых путей.

Две жалобы: «непонятно, идёт ли процесс» и «долго». Первая лечится отчётом о
ходе в уже существующее живое сообщение задачи, вторая — тем, что путь,
только что отказавший, не пробуют снова ближайшие минуты: каждая мёртвая
попытка стоит десятков секунд ожидания.
"""
import pytest

from core import hixiit


@pytest.fixture(autouse=True)
def _clean():
    hixiit._COLD.clear()
    yield
    hixiit._COLD.clear()


def _const(value):
    async def fn(*a, **k):
        return value
    return fn


@pytest.mark.asyncio
async def test_failed_path_is_skipped_next_time(monkeypatch):
    calls = []

    async def dead(*a, **k):
        calls.append(1)
        raise RuntimeError("ConnectTimeout")

    monkeypatch.setattr(hixiit, "execution_mode", _const("auto"))
    monkeypatch.setattr(hixiit, "mcp_configured", lambda: True)
    monkeypatch.setattr(hixiit, "_generate_via_mcp", dead)
    monkeypatch.setattr("core.higgsfield.credentials", lambda: None)
    monkeypatch.setattr(hixiit, "browser_available", _const(
        {"available": False, "where": "", "why": "нет"}))

    first = await hixiit._generate_once_raw("кадр", kind="video")
    second = await hixiit._generate_once_raw("кадр", kind="video")

    assert len(calls) == 1, "второй раз мёртвый путь пробовать не надо"
    assert any("MCP:" in t for t in first["tried"])
    assert any("пропущен — отказал недавно" in t for t in second["tried"])


@pytest.mark.asyncio
async def test_working_path_is_never_cooled(monkeypatch):
    monkeypatch.setattr(hixiit, "execution_mode", _const("auto"))
    monkeypatch.setattr(hixiit, "mcp_configured", lambda: True)
    monkeypatch.setattr(hixiit, "_generate_via_mcp", _const(
        {"ok": True, "url": "https://cdn/x.png", "kind": "image"}))
    for _ in range(3):
        res = await hixiit._generate_once_raw("кадр", kind="image")
        assert res["ok"]
    assert hixiit._cold("mcp") == 0


def test_cooldown_expires():
    """Отказ мог быть временным — через COOLDOWN путь проверяется заново."""
    import time
    hixiit._COLD["rest"] = time.monotonic() - 1
    assert hixiit._cold("rest") == 0


@pytest.mark.asyncio
async def test_progress_goes_into_the_live_message(monkeypatch):
    said = []

    async def fake_step(task_id, text, **kw):
        said.append((task_id, text))

    from core.cost_tracker import current_task_id
    token = current_task_id.set("TASK-1")
    monkeypatch.setattr("core.task_feed.watching", lambda tid: True)
    monkeypatch.setattr("core.task_feed.step", fake_step)
    try:
        await hixiit.tell("Пробую MCP")
    finally:
        current_task_id.reset(token)
    assert said == [("TASK-1", "Пробую MCP")]


@pytest.mark.asyncio
async def test_progress_is_silent_without_a_task(monkeypatch):
    """Вне задачи писать некуда — и это не ошибка."""
    async def must_not_run(*a, **k):
        raise AssertionError("писать некуда")

    from core.cost_tracker import current_task_id
    token = current_task_id.set("")
    monkeypatch.setattr("core.task_feed.step", must_not_run)
    try:
        await hixiit.tell("Пробую MCP")
    finally:
        current_task_id.reset(token)


@pytest.mark.asyncio
async def test_progress_failure_never_breaks_generation(monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("Telegram недоступен")

    from core.cost_tracker import current_task_id
    token = current_task_id.set("TASK-1")
    monkeypatch.setattr("core.task_feed.watching", lambda tid: True)
    monkeypatch.setattr("core.task_feed.step", boom)
    try:
        await hixiit.tell("Пробую MCP")      # не должно бросить
    finally:
        current_task_id.reset(token)


@pytest.mark.asyncio
async def test_browser_steps_are_reported(monkeypatch):
    """Шаги браузерного агента доходят до человека по одному."""
    from core import browser_agent
    seen = []

    async def watcher(number, thought, action):
        seen.append((number, thought, action))

    await browser_agent._report(watcher, 3, "выбираю модель", "click")
    assert seen == [(3, "выбираю модель", "click")]


@pytest.mark.asyncio
async def test_broken_watcher_does_not_stop_the_agent(monkeypatch):
    from core import browser_agent

    async def boom(*a):
        raise RuntimeError("чат недоступен")

    await browser_agent._report(boom, 1, "мысль", "click")
