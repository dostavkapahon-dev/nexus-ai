"""Браузер не должен держать память после работы.

С живого сервера пришёл диагноз: после установки Chromium начало таймаутить
ВСЁ — поиск («не ответил за 10 с» у трёх источников подряд) и Higgsfield («не
ответила за 60 секунд»), хотя раньше те же вызовы проходили. `shutdown()` не
вызывался нигде: поднятый однажды Chromium жил до перезапуска сервиса и
забирал память у самого сервера.
"""
import asyncio

import pytest

from core import server_browser as sb


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.setattr(sb, "_context", None)
    monkeypatch.setattr(sb, "_browser", None)
    monkeypatch.setattr(sb, "_page", None)
    monkeypatch.setattr(sb, "_idle_task", None)
    yield


def test_launch_args_are_lean():
    """На маленьком инстансе процесс на вкладку — непозволительная роскошь."""
    args = set(sb._LAUNCH_ARGS)
    assert "--single-process" in args
    assert "--disable-dev-shm-usage" in args
    assert any(a.startswith("--renderer-process-limit") for a in args)


@pytest.mark.asyncio
async def test_idle_browser_is_closed(monkeypatch):
    closed = []

    async def fake_shutdown():
        closed.append(True)
        monkeypatch.setattr(sb, "_context", None)
        monkeypatch.setattr(sb, "_browser", None)

    monkeypatch.setattr(sb, "shutdown", fake_shutdown)
    monkeypatch.setattr(sb, "IDLE_CLOSE_SEC", 0.0)
    monkeypatch.setattr(sb, "_context", object())

    async def instant(_):
        return None

    monkeypatch.setattr(asyncio, "sleep", instant)
    await sb._close_when_idle()
    assert closed == [True]


@pytest.mark.asyncio
async def test_busy_browser_is_not_closed(monkeypatch):
    """Закрыть браузер посреди работы — хуже, чем подержать его лишнюю минуту."""
    async def must_not_close():
        raise AssertionError("браузер ещё нужен")

    monkeypatch.setattr(sb, "shutdown", must_not_close)
    monkeypatch.setattr(sb, "IDLE_CLOSE_SEC", 300.0)
    monkeypatch.setattr(sb, "_context", object())

    calls = []

    async def instant(_):
        calls.append(1)
        if len(calls) > 2:
            monkeypatch.setattr(sb, "_context", None)
            monkeypatch.setattr(sb, "_browser", None)
        return None

    monkeypatch.setattr(asyncio, "sleep", instant)
    sb._touch()
    await sb._close_when_idle()


@pytest.mark.asyncio
async def test_every_command_postpones_the_closing(monkeypatch):
    monkeypatch.setattr(sb, "enabled", lambda: True)
    monkeypatch.setattr(sb, "_last_use", 0.0)

    async def fake_ensure():
        raise RuntimeError("браузер не нужен для этой проверки")

    monkeypatch.setattr(sb, "ensure_browser", fake_ensure)
    await sb.execute({"action": "screenshot"})
    assert sb._last_use > 0, "работа должна продлевать жизнь браузера"
