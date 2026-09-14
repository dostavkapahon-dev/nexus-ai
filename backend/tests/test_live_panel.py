"""Один растущий экран вместо россыпи сообщений (§21–23).

Каждый шаг уходил отдельным сообщением: чат засыпало, а общей картины всё
равно не было — «сейчас молчит» и «непонятно, что происходит» это одна и та же
болезнь. Плюс ни одно сообщение не называло, кто дирижирует: при отсутствии
ключа Anthropic система молча переходит на Gemini.
"""
import pytest

from core import telegram_bot as tb
from core import marketing_director as md


class _Fake:
    """Ловит и sendMessage, и editMessageText."""

    def __init__(self):
        self.sent, self.edited = [], []

    def post(self, url, json=None):
        body = json or {}
        if "editMessageText" in url:
            self.edited.append(body["text"])
            return _Resp({"ok": True})
        self.sent.append(body["text"])
        return _Resp({"ok": True, "result": {"message_id": 77}})


class _Resp:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


@pytest.fixture
def fake(monkeypatch):
    f = _Fake()

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            return f.post(url, json)

    monkeypatch.setattr(tb.httpx, "AsyncClient", lambda **kw: _Client())
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    return f


@pytest.mark.asyncio
async def test_only_one_message_is_sent(fake):
    progress, finish = tb._live_panel("1", "Задача")
    for label in ("Беру задачу", "Исследую", "Пишу сценарий", "Генерирую"):
        await progress(label)
    await finish(ok=True)
    assert len(fake.sent) == 1          # остальное — правки


@pytest.mark.asyncio
async def test_every_step_reaches_the_screen(fake):
    progress, finish = tb._live_panel("1", "Задача")
    await progress("Исследую")
    await progress("Пишу сценарий")
    await finish(ok=True)
    last = fake.edited[-1]
    assert "Исследую" in last and "Пишу сценарий" in last


@pytest.mark.asyncio
async def test_current_step_is_marked_as_running(fake):
    progress, _ = tb._live_panel("1", "Задача")
    await progress("Исследую")
    await progress("Генерирую")
    assert "⏳ Генерирую" in fake.edited[-1]
    assert "✅ Исследую" in fake.edited[-1]


@pytest.mark.asyncio
async def test_same_step_twice_is_not_progress(fake):
    progress, _ = tb._live_panel("1", "Задача")
    await progress("Исследую")
    before = len(fake.edited)
    await progress("Исследую")
    assert len(fake.edited) == before


@pytest.mark.asyncio
async def test_orchestrator_is_named_in_the_header(fake):
    progress, _ = tb._live_panel("1", "Задача", "🧠 Дирижёр: Gemini gemini-2.5-flash")
    await progress("Беру задачу")
    assert "Gemini" in fake.sent[0]


@pytest.mark.asyncio
async def test_failure_is_visible(fake):
    progress, finish = tb._live_panel("1", "Задача")
    await progress("Генерирую")
    await finish(ok=False)
    assert "⚠️" in fake.edited[-1]


@pytest.mark.asyncio
async def test_panel_failure_does_not_raise(monkeypatch):
    """Панель — удобство, а не задача: её сбой не должен ронять работу."""
    class _Boom:
        async def __aenter__(self):
            raise RuntimeError("сеть легла")

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(tb.httpx, "AsyncClient", lambda **kw: _Boom())
    progress, finish = tb._live_panel("1", "Задача")
    await progress("Беру задачу")
    await finish(ok=True)


def test_orchestrator_prefers_anthropic(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    assert md.current_orchestrator()["provider"] == "anthropic"


def test_orchestrator_falls_back_to_gemini(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    who = md.current_orchestrator()
    assert who["provider"] == "google" and "Gemini" in who["human"]


def test_no_keys_is_honest(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    who = md.current_orchestrator()
    assert not who["ok"] and "нет ключа" in who["human"]
