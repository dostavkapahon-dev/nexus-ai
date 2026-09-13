"""«Группа постов» в /diag должна отражать то, чем публикация пользуется.

Публикация берёт канал, подключённый через /channels, и только потом смотрит
TELEGRAM_POST_CHAT_ID (connectors/telegram.py::_target). Диагностика же
проверяла одну переменную — и показывала ❌ при живом подключённом канале,
то есть отправляла человека настраивать то, что уже работает.
"""
import pytest

from core import telegram_bot as tb


async def _diag(monkeypatch, channel="", env=""):
    from database.db import init_db
    await init_db()
    sent = []

    async def fake_send(chat_id, text, **kw):
        sent.append(text)
        return {}

    async def fake_default_channel():
        return channel

    monkeypatch.setattr(tb, "send_message", fake_send)
    monkeypatch.setattr("core.telegram_channels.default_channel", fake_default_channel)
    if env:
        monkeypatch.setenv("TELEGRAM_POST_CHAT_ID", env)
    else:
        monkeypatch.delenv("TELEGRAM_POST_CHAT_ID", raising=False)
    monkeypatch.setattr("core.health.probe_all", _probes)
    await tb._handle_command("960", "/diag")
    return "\n".join(sent)


async def _probes(*a, **kw):
    return []


def _line(text):
    return next(l for l in text.split("\n") if "Группа постов" in l)


@pytest.mark.asyncio
async def test_connected_channel_counts(monkeypatch):
    line = _line(await _diag(monkeypatch, channel="@pahon_studio"))
    assert line.startswith("✅")


@pytest.mark.asyncio
async def test_connected_channel_wins_over_env(monkeypatch):
    """Публикация предпочитает подключённый канал — статус обязан совпадать."""
    line = _line(await _diag(monkeypatch, channel="@pahon_studio", env="-100500"))
    assert "канал подключён" in line


@pytest.mark.asyncio
async def test_env_still_counts_when_no_channel(monkeypatch):
    line = _line(await _diag(monkeypatch, channel="", env="-100500"))
    assert line.startswith("✅") and "Render" in line


@pytest.mark.asyncio
async def test_nothing_configured_tells_what_to_do(monkeypatch):
    line = _line(await _diag(monkeypatch, channel="", env=""))
    assert line.startswith("❌") and "/channels" in line
