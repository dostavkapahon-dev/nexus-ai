"""
Бот делает ролик, а не обещает его сделать.

Живой случай, из которого выросли эти проверки: «ИИ ролик» → бот расписал план
из четырёх пунктов и спросил тему, «1» → тишина, «Напиши» → тишина. Ни одного
ролика не создано. Здесь закрыт каждый обрыв этой цепочки.
"""
import pytest

from core import dialog, intent


# ─────────────────────── распознавание заявки на ролик ───────────────────────

@pytest.mark.parametrize("text", [
    "ИИ ролик",
    "нужен reels",
    "рилс",
    "видео про доставку еды",
    "сделай ролик про кофейню",
])
def test_reel_request_goes_to_factory(text):
    cmd = intent.quick_route(text)
    assert cmd and cmd.startswith("/factory"), f"«{text}» не запустил фабрику"


def test_topic_is_taken_from_the_phrase():
    assert intent.quick_route("видео про доставку еды") == "/factory доставку еды"
    # Тема не названа — фабрика без темы, её спросят отдельно.
    assert intent.quick_route("ИИ ролик") == "/factory"


def test_chat_never_promises_to_do_the_work():
    """Обещание «сейчас сгенерирую» никто не исполнит — модель не должна его давать."""
    assert "не обещай действие" in intent.CHAT_SYSTEM.lower()


@pytest.mark.asyncio
async def test_empty_model_answer_is_replaced_with_something_useful(monkeypatch):
    monkeypatch.setattr("core.ai_router.ai_available", lambda: True)

    async def empty(*a, **kw):
        return {"text": "   "}

    monkeypatch.setattr("core.ai_router.ai_router.call", empty)
    reply = await intent.chat_reply("что-то непонятное")
    assert reply.strip(), "пустой ответ уходит в Telegram как молчание"
    assert "/help" in reply


# ─────────────────────────── память диалога ───────────────────────────

@pytest.mark.asyncio
async def test_history_gives_meaning_to_short_answers(client):
    chat = "555"
    await dialog.clear(chat)
    await dialog.remember(chat, "agent", "Выберите: 1) ролик 2) тренды")
    await dialog.remember(chat, "user", "1")

    hist = await dialog.history(chat)
    assert "1) ролик" in hist and "Пользователь: 1" in hist


@pytest.mark.asyncio
async def test_history_is_passed_to_the_model(client, monkeypatch):
    seen = {}
    monkeypatch.setattr("core.ai_router.ai_available", lambda: True)

    async def capture(model, system, prompt, *a, **kw):
        seen["prompt"] = prompt
        return {"text": "/factory кофейня"}

    monkeypatch.setattr("core.ai_router.ai_router.call", capture)
    cmd = await intent.route("1", history="Бот: Выберите: 1) ролик про кофейню")
    assert "кофейню" in seen["prompt"], "модель решает без контекста прошлой реплики"
    assert cmd == "/factory кофейня"


@pytest.mark.asyncio
async def test_waiting_state_survives_between_messages(client):
    chat = "556"
    await dialog.clear(chat)
    await dialog.expect(chat, dialog.AWAIT_TOPIC)
    assert await dialog.awaiting(chat) == dialog.AWAIT_TOPIC
    await dialog.expect(chat, "")
    assert await dialog.awaiting(chat) == ""


# ─────────────────────────── поведение бота ───────────────────────────

@pytest.mark.asyncio
async def test_factory_without_topic_asks_once_then_starts(client, monkeypatch):
    """Один вопрос про тему — и следующее сообщение уже запускает конвейер."""
    from core import telegram_bot as tb

    sent, started = [], []

    async def fake_send(chat_id, text, **kw):
        sent.append(text)
        return {}

    async def fake_spawn(kind, goal, fn, **kw):
        started.append(goal)
        return "task1"

    monkeypatch.setattr(tb, "send_message", fake_send)
    monkeypatch.setattr("core.task_manager.spawn", fake_spawn)
    await dialog.clear("777")

    await tb._handle_command("777", "/factory")
    assert any("Какая тема" in s for s in sent)
    assert not started, "фабрику нельзя запускать, не зная темы"

    await tb._handle_plain_text("777", "доставка еды за 15 минут")
    assert started and "доставка еды" in started[0]


@pytest.mark.asyncio
async def test_by_trends_answer_starts_factory_without_topic(client, monkeypatch):
    from core import telegram_bot as tb

    started = []

    async def fake_send(chat_id, text, **kw):
        return {}

    async def fake_spawn(kind, goal, fn, **kw):
        started.append(goal)
        return "t"

    monkeypatch.setattr(tb, "send_message", fake_send)
    monkeypatch.setattr("core.task_manager.spawn", fake_spawn)

    await dialog.clear("778")
    await dialog.expect("778", dialog.AWAIT_TOPIC)
    await tb._handle_plain_text("778", "по трендам")
    assert started and "по трендам" in started[0].lower()


@pytest.mark.asyncio
async def test_factory_goes_to_approval_not_dry_run(client, monkeypatch):
    """Без слова «превью» конвейер обязан дойти до согласования."""
    from core import telegram_bot as tb

    calls = {}

    async def fake_send(chat_id, text, **kw):
        return {}

    async def fake_spawn(kind, goal, fn, **kw):
        calls["fn"] = fn
        return "t"

    async def fake_factory(topic=None, dry_run=False, **kw):
        calls["dry_run"] = dry_run
        return {"ok": True}

    monkeypatch.setattr(tb, "send_message", fake_send)
    monkeypatch.setattr("core.task_manager.spawn", fake_spawn)
    monkeypatch.setattr("core.content_factory.run_factory", fake_factory)

    await tb._handle_command("779", "/factory кофейня")
    await calls["fn"]()
    assert calls["dry_run"] is False, "ролик собран, но согласование пропущено"

    await tb._handle_command("779", "/factory кофейня превью")
    await calls["fn"]()
    assert calls["dry_run"] is True


@pytest.mark.asyncio
async def test_create_without_plans_runs_factory(client, monkeypatch):
    """Пустой контент-план — не повод отказывать: тему придумает конвейер."""
    from core import telegram_bot as tb

    sent, started = [], []

    async def fake_send(chat_id, text, **kw):
        sent.append(text)
        return {}

    async def fake_spawn(kind, goal, fn, **kw):
        started.append(kind)
        return "t"

    monkeypatch.setattr(tb, "send_message", fake_send)
    monkeypatch.setattr("core.task_manager.spawn", fake_spawn)

    await tb._handle_command("780", "/create кофейня")
    assert not any("/analyze" in s for s in sent), "старый тупик вернулся"
    assert "factory" in started


@pytest.mark.asyncio
async def test_broken_handler_answers_instead_of_going_silent(client, monkeypatch):
    from core import telegram_bot as tb

    sent = []

    async def fake_send(chat_id, text, **kw):
        sent.append(text)
        return {}

    async def boom(chat_id, text):
        raise RuntimeError("база отвалилась")

    monkeypatch.setattr(tb, "send_message", fake_send)
    monkeypatch.setattr(tb, "_plain_text", boom)

    await tb._handle_plain_text("781", "привет")
    assert sent and "база отвалилась" in sent[0]


@pytest.mark.asyncio
async def test_send_message_never_sends_empty_text(client, monkeypatch):
    from core import telegram_bot as tb

    posted = {}

    class FakeResp:
        def json(self):
            return {"ok": True}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            posted.update(json or {})
            return FakeResp()

    monkeypatch.setattr(tb.httpx, "AsyncClient", lambda *a, **kw: FakeClient())
    await tb.send_message("782", "")
    assert posted.get("text", "").strip(), "пустое сообщение = молчание бота"
