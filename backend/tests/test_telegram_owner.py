"""
Кто может командовать ботом и переживает ли бот подключение токена на ходу.

Раньше при незаданном TELEGRAM_CHAT_ID бот исполнял команды любого, кто его
нашёл: публикацию, запуск браузера на ПК владельца, генерацию за деньги.
А подключённый через веб токен не оживлял бота до перезапуска сервера.
"""
import asyncio

import pytest
from sqlalchemy import delete

from core import telegram_owner as owner
from core import telegram_bot as tb
from database.db import AsyncSessionLocal
from database.models import Connection


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    owner.invalidate()
    yield
    owner.invalidate()


async def _wipe():
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Connection).where(Connection.key_name == owner.OWNER_KEY))
        await db.commit()
    owner.invalidate()


@pytest.mark.asyncio
async def test_nobody_is_allowed_until_owner_is_known(client):
    await _wipe()
    assert await owner.owner_id() == ""
    assert await owner.allowed("777", "777") is False


@pytest.mark.asyncio
async def test_first_start_claims_the_bot(client):
    await _wipe()
    assert await owner.claim("111") is True
    assert await owner.owner_id() == "111"

    # Чужой не может перехватить бота, повторный вызов владельцем безвреден.
    assert await owner.claim("222") is False
    assert await owner.claim("111") is True
    assert await owner.allowed("111") is True
    assert await owner.allowed("222") is False


@pytest.mark.asyncio
async def test_owner_from_settings_wins(client, monkeypatch):
    await _wipe()
    await owner.claim("111")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
    owner.invalidate()
    assert await owner.owner_id() == "999"
    assert await owner.allowed("111") is False
    assert await owner.allowed("999") is True


@pytest.mark.asyncio
async def test_sender_matters_not_chat(client):
    """В группе сверять надо отправителя: иначе командовать может любой участник."""
    await _wipe()
    await owner.claim("111")
    group_chat = "-1005"
    assert await owner.allowed("222", group_chat) is False
    assert await owner.allowed("111", group_chat) is True


@pytest.mark.asyncio
async def test_owner_survives_restart(client):
    await _wipe()
    await owner.claim("111")
    owner.invalidate()                      # как будто процесс перезапустили
    assert await owner.owner_id() == "111"


# ─────────────────────────── цикл бота ───────────────────────────

class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _FakeClient:
    """Подменяет httpx.AsyncClient: отдаёт заранее заготовленные ответы Telegram."""

    def __init__(self, answers, seen):
        self._answers, self._seen = answers, seen

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None):
        self._seen.append(params)
        return _Resp(self._answers.pop(0) if self._answers else {"ok": True, "result": []})

    async def post(self, url, json=None):
        return _Resp({"ok": True, "result": {}})


async def _run_poll_briefly(monkeypatch, answers, seen, seconds=0.3):
    monkeypatch.setattr(tb.httpx, "AsyncClient",
                        lambda *a, **kw: _FakeClient(answers, seen))
    task = asyncio.create_task(tb.poll_updates())
    await asyncio.sleep(seconds)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_polling_waits_for_token_instead_of_exiting(client, monkeypatch):
    """Бот, запущенный без токена, должен ожить после подключения из веба."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    seen = []
    await _run_poll_briefly(monkeypatch, [], seen, seconds=0.2)
    assert seen == []                       # без токена в Telegram не ходим

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    await _run_poll_briefly(monkeypatch, [], seen, seconds=0.2)
    assert seen, "после подключения токена цикл обязан начать опрос"


@pytest.mark.asyncio
async def test_polling_survives_conflict(client, monkeypatch):
    """409 — не «сообщений нет»: раньше цикл крутился молча и бот выглядел мёртвым."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    seen = []
    answers = [{"ok": False, "error_code": 409, "description": "Conflict: terminated"}]
    await _run_poll_briefly(monkeypatch, answers, seen, seconds=0.2)
    assert seen, "цикл должен продолжать работу после 409"


@pytest.mark.asyncio
async def test_stranger_gets_refusal_and_owner_is_claimed(client, monkeypatch):
    await _wipe()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")

    sent = []

    async def fake_send(chat_id, text, *a, **kw):
        sent.append((str(chat_id), text))

    handled = []

    async def fake_handle(chat_id, text):
        handled.append((str(chat_id), text))

    monkeypatch.setattr(tb, "send_message", fake_send)
    monkeypatch.setattr(tb, "_handle_command", fake_handle)

    updates = {"ok": True, "result": [
        {"update_id": 1, "message": {"chat": {"id": 111}, "from": {"id": 111},
                                     "text": "/start"}},
        {"update_id": 2, "message": {"chat": {"id": 222}, "from": {"id": 222},
                                     "text": "/publish"}},
    ]}
    seen = []
    await _run_poll_briefly(monkeypatch, [updates], seen, seconds=0.3)

    assert await owner.owner_id() == "111"
    assert any(t == owner.CLAIMED for _, t in sent)
    assert any(c == "222" and t == owner.DENIED for c, t in sent)
    # Команда постороннего до обработчика не доходит.
    assert all(c != "222" for c, _ in handled)


@pytest.mark.asyncio
async def test_polling_remembers_channels_for_the_wizard(client, monkeypatch):
    """Мастер подключения берёт каналы отсюда — своего getUpdates у него нет."""
    from core import telegram_channels as tc

    await _wipe()
    await owner.claim("111")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    tc._seen_chats.clear()

    updates = {"ok": True, "result": [
        {"update_id": 5, "channel_post": {"chat": {"id": -1001, "title": "Канал",
                                                   "username": "ch", "type": "channel"}}},
    ]}
    await _run_poll_briefly(monkeypatch, [updates], [], seconds=0.3)

    assert "-1001" in tc._seen_chats
    await _wipe()
