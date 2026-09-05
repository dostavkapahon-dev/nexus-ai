"""Разговор должен быть связным: «переделай второй вариант» — про то, что было.

Без истории дирижёр каждый раз начинает с чистого листа и не понимает, о каком
варианте речь. Реплики уже сохранялись, но до дирижёра не доходили.
"""
import pytest

from core import command_center, dialog, telegram_bot as tg


@pytest.mark.asyncio
async def test_director_receives_the_conversation(client, monkeypatch):
    seen = {}

    async def fake_director(goal, context="", max_steps=12):
        seen["goal"] = goal
        seen["context"] = context
        return {"status": "done", "summary": "готово", "steps": []}

    monkeypatch.setattr("core.marketing_director.run_director", fake_director)
    monkeypatch.setattr("core.ai_router.ai_available", lambda: True)
    monkeypatch.setattr("core.intent.route", _route_to_director)

    await command_center.run_command("переделай второй вариант", source="telegram",
                                     mirror=False, context="user: сделай три поста\nagent: готово")

    assert "три поста" in seen["context"], "дирижёр должен видеть предыдущие реплики"


async def _route_to_director(text, history=""):
    return "/director " + text


@pytest.mark.asyncio
async def test_telegram_passes_history_and_records_the_reply(client, monkeypatch):
    """Полная цепочка: история собрана, отдана дирижёру, ответ сохранён."""
    await dialog.remember("55", "user", "сделай три варианта поста")
    await dialog.remember("55", "agent", "вот три варианта")

    got = {}

    async def fake_run_command(text, source="dashboard", mirror=True, context=""):
        got["context"] = context
        return {"ok": True, "reply": "переделал второй", "steps": []}

    monkeypatch.setattr("core.command_center.run_command", fake_run_command)
    monkeypatch.setattr(tg, "send_message", _swallow)

    await tg._dispatch_command("55", "/director переделай второй вариант")

    assert "три варианта" in got["context"]

    # Ответ дирижёра тоже в истории — иначе следующая реплика повиснет в воздухе.
    history = await dialog.history("55")
    assert "переделал второй" in history


@pytest.mark.asyncio
async def test_empty_history_does_not_break_anything(client, monkeypatch):
    """Первое сообщение в чате — истории ещё нет, и это нормально."""
    await dialog.clear("77")
    got = {}

    async def fake_run_command(text, source="dashboard", mirror=True, context=""):
        got["context"] = context
        return {"ok": True, "reply": "готово", "steps": []}

    monkeypatch.setattr("core.command_center.run_command", fake_run_command)
    monkeypatch.setattr(tg, "send_message", _swallow)

    await tg._dispatch_command("77", "/director сделай пост")

    assert got["context"] == "" or isinstance(got["context"], str)


async def _swallow(chat_id, text, parse_mode="HTML", reply_markup=None, feed=False):
    return {}


@pytest.mark.asyncio
async def test_result_offers_feedback_buttons(client, monkeypatch):
    async def fake_run_command(text, source="dashboard", mirror=True, context=""):
        return {"ok": True, "reply": "готово", "steps": []}

    sent = []

    async def fake_send(chat_id, text, parse_mode="HTML", reply_markup=None, feed=False):
        sent.append((text, reply_markup))
        return {}

    monkeypatch.setattr("core.command_center.run_command", fake_run_command)
    monkeypatch.setattr(tg, "send_message", fake_send)

    await tg._dispatch_command("55", "/director сделай пост")

    with_buttons = [m for _, m in sent if m]
    assert with_buttons, "под результатом должны быть кнопки оценки"
    codes = [b["callback_data"] for row in with_buttons[-1]["inline_keyboard"] for b in row]
    assert {"fb_good", "fb_bad", "fb_again", "fb_edit"} <= set(codes)


@pytest.mark.asyncio
async def test_feedback_is_remembered_for_next_time(client, monkeypatch):
    monkeypatch.setattr(tg, "send_message", _swallow)
    await dialog.clear("88")

    await tg._dispatch_command("88", "/fb_good")

    assert "понравилось" in await dialog.history("88")


@pytest.mark.asyncio
async def test_negative_feedback_asks_what_was_wrong(client, monkeypatch):
    """«Не то» без объяснения бесполезно для следующей генерации."""
    said = []

    async def fake_send(chat_id, text, parse_mode="HTML", reply_markup=None, feed=False):
        said.append(text)
        return {}

    monkeypatch.setattr(tg, "send_message", fake_send)

    await tg._dispatch_command("55", "/fb_bad")

    assert said and "не подошло" in said[-1]


@pytest.mark.asyncio
async def test_another_variant_reuses_the_original_task(client, monkeypatch):
    calls = []

    async def fake_run_command(text, source="dashboard", mirror=True, context=""):
        calls.append(text)
        return {"ok": True, "reply": "готово", "steps": []}

    monkeypatch.setattr("core.command_center.run_command", fake_run_command)
    monkeypatch.setattr(tg, "send_message", _swallow)

    await tg._dispatch_command("55", "/director сделай пост про кофе")
    await tg._dispatch_command("55", "/fb_again")

    assert len(calls) == 2
    assert "кофе" in calls[1], "повтор должен идти по той же задаче"
