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
async def test_empty_request_asks_instead_of_generating(calls):
    await tb._run_single_generation("1", "", "image")
    assert not calls.generated
    assert any("/image" in m for m in calls.messages)


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
