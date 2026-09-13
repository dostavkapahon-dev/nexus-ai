"""Управление автоматикой из Telegram.

Выключатель автопубликации жил в вебе и в переменной окружения. Из Telegram —
главного интерфейса — автоматику нельзя было ни посмотреть, ни остановить,
хотя именно она тратит кредиты и публикует посты наружу.

Отдельно проверяется, что фабрика слушает тот же выключатель: раньше она
читала AUTO_PUBLISH, а очередь и публикация — настройку из базы, и выключение
в настройках фабрику не останавливало.
"""
import pytest

from core import telegram_bot as tb


async def _say(monkeypatch, cmd, settings):
    sent = []

    async def fake_send(chat_id, text, **kw):
        sent.append({"text": text, "kb": kw.get("reply_markup")})
        return {}

    async def fake_get():
        return settings

    saved = {}

    async def fake_set(enabled=None, platforms=None):
        saved["enabled"] = enabled
        return {"ok": True}

    monkeypatch.setattr(tb, "send_message", fake_send)
    monkeypatch.setattr("core.autopublish.get_settings", fake_get)
    monkeypatch.setattr("core.autopublish.set_settings", fake_set)
    await tb._handle_command("970", cmd)
    return sent, saved


def _state(enabled=True):
    return {"enabled": enabled,
            "platforms": {"telegram": "auto", "instagram": "confirm"}}


@pytest.mark.asyncio
async def test_auto_shows_schedule(monkeypatch):
    sent, _ = await _say(monkeypatch, "/autopost", _state())
    assert "09:30" in sent[0]["text"] and "19:00" in sent[0]["text"]


@pytest.mark.asyncio
async def test_auto_shows_state_on(monkeypatch):
    sent, _ = await _say(monkeypatch, "/autopost", _state(enabled=True))
    assert "включена" in sent[0]["text"]


@pytest.mark.asyncio
async def test_auto_shows_state_off(monkeypatch):
    sent, _ = await _say(monkeypatch, "/autopost", _state(enabled=False))
    assert "выключена" in sent[0]["text"]


@pytest.mark.asyncio
async def test_modes_are_human_readable(monkeypatch):
    """«confirm» человеку ничего не говорит."""
    sent, _ = await _say(monkeypatch, "/autopost", _state())
    assert "с подтверждением" in sent[0]["text"]
    assert "confirm" not in sent[0]["text"]


@pytest.mark.asyncio
async def test_button_offers_the_opposite_action(monkeypatch):
    sent, _ = await _say(monkeypatch, "/autopost", _state(enabled=True))
    buttons = str(sent[0]["kb"])
    assert "autopub_off" in buttons and "autopub_on" not in buttons


@pytest.mark.asyncio
async def test_turning_off_is_saved(monkeypatch):
    _, saved = await _say(monkeypatch, "/autopub_off", _state())
    assert saved["enabled"] is False


@pytest.mark.asyncio
async def test_turning_on_is_saved(monkeypatch):
    _, saved = await _say(monkeypatch, "/autopub_on", _state(enabled=False))
    assert saved["enabled"] is True


@pytest.mark.asyncio
async def test_factory_follows_the_same_switch(monkeypatch):
    """Выключатель в настройках обязан останавливать и фабрику."""
    seen = {}

    async def fake_factory(topic=None, dry_run=True):
        seen["dry_run"] = dry_run
        return {}

    async def off():
        return {"enabled": False, "platforms": {}}

    monkeypatch.setattr("core.content_factory.run_factory", fake_factory)
    monkeypatch.setattr("core.autopublish.get_settings", off)
    monkeypatch.setenv("AUTO_PUBLISH", "1")      # старый выключатель не должен побеждать

    from core.scheduler import run_daily_factory
    await run_daily_factory()
    assert seen["dry_run"] is True
