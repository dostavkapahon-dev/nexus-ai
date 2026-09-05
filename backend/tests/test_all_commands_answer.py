"""Каждая команда Telegram должна отвечать, а не молчать и не падать.

Молчание бота — худший исход: человек не понимает, приняли задачу или нет.
Раньше /strategy падал необработанным исключением, когда нет ключей моделей:
человек видел «Анализирую...» и больше ничего.
"""
import asyncio

import pytest

from core import telegram_bot as tg

# Команды из меню бота плюс те, что вызываются кнопками.
COMMANDS = [
    "menu", "diag", "hixiit", "tasks", "cost", "queue", "channels", "approve",
    "errors", "rivals", "strategies", "comments", "pc", "status", "strategy",
    "hunt", "viral", "factory", "create", "publish", "plan", "trend",
    "pause", "resume", "config", "plan7", "do", "help", "predict",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("cmd", COMMANDS)
async def test_command_answers_something(client, monkeypatch, cmd):
    said = []

    async def fake_send(chat_id, text, parse_mode="HTML", reply_markup=None, feed=False):
        said.append(text)
        return {}

    monkeypatch.setattr(tg, "send_message", fake_send)

    await asyncio.wait_for(tg._dispatch_command("55", f"/{cmd}"), timeout=60)

    assert said, f"/{cmd} промолчал — человек не узнает, что произошло"
    assert said[-1].strip(), f"/{cmd} ответил пустым сообщением"


@pytest.mark.asyncio
async def test_unknown_command_shows_help(client, monkeypatch):
    said = []

    async def fake_send(chat_id, text, parse_mode="HTML", reply_markup=None, feed=False):
        said.append(text)
        return {}

    monkeypatch.setattr(tg, "send_message", fake_send)

    await tg._dispatch_command("55", "/такой-команды-нет")

    assert said and "/" in said[-1], "на неизвестную команду нужно показать список команд"
