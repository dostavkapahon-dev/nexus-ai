"""Команда /image: кадр приходит файлом, а не списком команд.

До этого команды не существовало — кнопка «▶️ Сгенерировать кадр» в пульте
/hf слала «/image ...», обработчик её не знал и печатал справку.
"""
import pytest

from core import telegram_bot as tb


class _Calls:
    def __init__(self):
        self.messages = []
        self.photos = []
        self.videos = []
        self.generated = []


@pytest.fixture
def calls(monkeypatch):
    c = _Calls()

    async def fake_send(chat_id, text, *a, **k):
        c.messages.append(text)

    async def fake_photo(chat_id, url, caption="", *a, **k):
        c.photos.append((url, caption))

    async def fake_video(chat_id, url, caption="", *a, **k):
        c.videos.append((url, caption))

    monkeypatch.setattr(tb, "send_message", fake_send)
    import publishers.telegram_pub as pub
    monkeypatch.setattr(pub, "send_photo", fake_photo)
    monkeypatch.setattr(pub, "send_video", fake_video)

    from core import hixiit
    async def fake_generate(task, kind="auto", ratio=None, **k):
        c.generated.append({"task": task, "kind": kind, "ratio": ratio})
        return {"ok": True, "url": "https://example.com/a.jpg", "kind": kind,
                "provider": "higgsfield", "model": "soul"}
    monkeypatch.setattr(hixiit, "generate", fake_generate)
    from core import artifacts
    async def fake_mark(*a, **k):
        return None
    monkeypatch.setattr(artifacts, "mark", fake_mark)
    return c


@pytest.fixture
def dialog_state(monkeypatch):
    """Состояние диалога в памяти, без базы."""
    from core import dialog
    state = {}

    async def fake_expect(chat_id, what, data=None):
        if what:
            state.update(awaiting=what, pending=data or {})
        else:
            state.clear()

    async def fake_awaiting(chat_id):
        return state.get("awaiting", "")

    async def fake_pending(chat_id):
        return state.get("pending", {})

    async def noop(*a, **k):
        return None

    monkeypatch.setattr(dialog, "expect", fake_expect)
    monkeypatch.setattr(dialog, "awaiting", fake_awaiting)
    monkeypatch.setattr(dialog, "pending", fake_pending)
    monkeypatch.setattr(dialog, "remember", noop)
    return state


@pytest.mark.asyncio
async def test_image_command_sends_a_photo(calls):
    await tb._run_single_generation("1", "шашлык на мангале", "image")
    assert calls.photos, "кадр должен прийти файлом"
    assert calls.generated[0]["kind"] == "image"
    assert calls.generated[0]["task"] == "шашлык на мангале"


@pytest.mark.asyncio
async def test_platform_sets_the_format(calls):
    await tb._run_single_generation("1", "фото шашлыка для youtube", "image")
    assert calls.generated[0]["ratio"] == "16:9"


@pytest.mark.asyncio
async def test_quality_word_is_temporary(calls, monkeypatch):
    from core import hixiit
    seen = []
    async def fake_quality():
        return "auto"
    async def fake_set(mode):
        seen.append(mode)
    monkeypatch.setattr(hixiit, "quality_mode", fake_quality)
    monkeypatch.setattr(hixiit, "set_quality_mode", fake_set)
    await tb._run_single_generation("1", "фото шашлыка подешевле", "image")
    # Включили экономию на задачу и вернули настройку человека обратно.
    assert seen == ["economy", "auto"]


@pytest.mark.asyncio
async def test_empty_request_asks_instead_of_generating(calls, dialog_state):
    await tb._run_single_generation("1", "", "image")
    assert not calls.generated
    assert any("Что нарисовать" in m for m in calls.messages)


@pytest.mark.asyncio
async def test_failure_names_the_step_and_reason(calls, monkeypatch):
    from core import hixiit
    async def fail(task, kind="auto", ratio=None, **k):
        return {"ok": False, "error": "вход не выполнен", "tried": ["mcp", "rest"]}
    monkeypatch.setattr(hixiit, "generate", fail)
    await tb._run_single_generation("1", "шашлык", "image")
    text = "\n".join(calls.messages)
    assert "вход не выполнен" in text and "mcp" in text
    assert not calls.photos


@pytest.mark.asyncio
async def test_delivery_failure_does_not_regenerate(calls, monkeypatch):
    import publishers.telegram_pub as pub
    async def boom(*a, **k):
        raise RuntimeError("file too big")
    monkeypatch.setattr(pub, "send_photo", boom)
    await tb._run_single_generation("1", "шашлык", "image")
    assert len(calls.generated) == 1
    assert any("example.com/a.jpg" in m for m in calls.messages)


@pytest.mark.asyncio
async def test_empty_command_waits_for_the_subject(calls, dialog_state, monkeypatch):
    """«/img» → «Что нарисовать?» → «САМСА»: ответ и есть предмет. Раньше он
    уходил в общий разбор, и бот отвечал «слова вместо команды не сработают»."""
    from core import autopilot, dialog

    async def no_interview():
        return {}
    monkeypatch.setattr(autopilot, "get_state", no_interview)

    await tb._run_single_generation("1", "", "image")
    assert not calls.generated
    assert dialog_state.get("awaiting") == dialog.AWAIT_TOPIC

    await tb._plain_text("1", "САМСА")
    assert calls.generated and calls.generated[0]["task"].lower() == "самса"
    assert calls.generated[0]["kind"] == "image"
    assert not dialog_state, "ожидание снимается после ответа"
