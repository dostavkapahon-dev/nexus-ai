"""«Отправлено» должно означать, что оно дошло.

Из Telegram пришло: «✅ ролик отправлен в Telegram на согласование», а ролика
нет — и картинки нет. Причина: отправка глотала любые ошибки и даже не читала
ответ Telegram, а кадры считались успешными по длине списка, а не по тому,
нарисовалось ли хоть что-то.
"""
import httpx
import pytest
import pytest_asyncio

from core import moderation


class _Resp:
    def __init__(self, status=200, data=None, text=""):
        self.status_code = status
        self._data = data if data is not None else {"ok": True}
        self.text = text

    def json(self):
        if self._data is None:
            raise ValueError("не json")
        return self._data


def _client(resp, seen):
    class C:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            seen.append({"method": url.rsplit("/", 1)[-1], "payload": json})
            return resp(len(seen)) if callable(resp) else resp
    return lambda *a, **k: C()


@pytest_asyncio.fixture(autouse=True)
async def bot(monkeypatch):
    # Очередь согласования лежит в базе — её надо создать.
    from database.db import init_db
    await init_db()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    yield


@pytest.mark.asyncio
async def test_rejection_by_telegram_is_an_error_not_a_tick(monkeypatch):
    seen = []
    monkeypatch.setattr(httpx, "AsyncClient", _client(
        _Resp(400, {"ok": False, "description": "wrong file identifier"}), seen))
    with pytest.raises(RuntimeError, match="wrong file identifier"):
        await moderation._tg("sendPhoto", {"chat_id": "42", "photo": "x"})


@pytest.mark.asyncio
async def test_missing_token_is_named(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
        await moderation._tg("sendMessage", {})


@pytest.mark.asyncio
async def test_photo_says_it_is_a_frame_not_a_video(monkeypatch):
    seen = []
    monkeypatch.setattr(httpx, "AsyncClient", _client(_Resp(), seen))
    await moderation.send_for_approval("текст", media_url="https://x/i.png")
    assert seen[0]["method"] == "sendPhoto"
    assert "кадр" in seen[0]["payload"]["caption"]
    assert "ролик" not in seen[0]["payload"]["caption"]


@pytest.mark.asyncio
async def test_video_is_called_a_video(monkeypatch):
    seen = []
    monkeypatch.setattr(httpx, "AsyncClient", _client(_Resp(), seen))
    await moderation.send_for_approval("текст", media_url="https://x/v.mp4")
    assert seen[0]["method"] == "sendVideo"
    assert "ролик" in seen[0]["payload"]["caption"]


@pytest.mark.asyncio
async def test_rejected_photo_falls_back_to_a_link(monkeypatch):
    """Файл создан — терять его из-за отказа доставки нельзя."""
    seen = []

    def answer(n):
        return (_Resp(400, {"ok": False, "description": "photo invalid"})
                if n == 1 else _Resp())

    monkeypatch.setattr(httpx, "AsyncClient", _client(answer, seen))
    pid = await moderation.send_for_approval("текст", media_url="https://x/i.png")
    assert pid
    assert seen[1]["method"] == "sendMessage"
    assert "https://x/i.png" in seen[1]["payload"]["text"]
    assert "photo invalid" in seen[1]["payload"]["text"]


@pytest.mark.asyncio
async def test_nobody_to_send_to_is_an_error(monkeypatch):
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    async def no_owner():
        return ""
    monkeypatch.setattr("core.telegram_owner.owner_id", no_owner)
    with pytest.raises(RuntimeError, match="некому отправлять"):
        await moderation.send_for_approval("текст")


# ── кадры раскадровки ─────────────────────────────────────────────────────────

def test_empty_frames_do_not_count_as_drawn():
    """Четыре записи с пустой ссылкой — это ноль нарисованного, а не «x4»."""
    frames = [{"t": "0-2", "image": ""}, {"t": "2-5", "image": None}]
    drawn = [f for f in frames if str(f.get("image") or "").startswith("http")]
    assert drawn == []


@pytest.mark.asyncio
async def test_drawn_frames_are_delivered(monkeypatch):
    from core import content_factory as cf
    sent = []

    async def fake_photo(chat, url, caption="", *a, **k):
        sent.append((chat, url, caption))

    monkeypatch.setattr("publishers.telegram_pub.send_photo", fake_photo)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    await cf._send_frames([{"t": "0-2", "overlay": "хук", "image": "https://x/1.png"},
                           {"t": "2-5", "overlay": "", "image": "https://x/2.png"}])
    assert [u for _, u, _ in sent] == ["https://x/1.png", "https://x/2.png"]
    assert "Кадр 1/2" in sent[0][2]


@pytest.mark.asyncio
async def test_frame_delivery_never_breaks_the_pipeline(monkeypatch):
    from core import content_factory as cf

    async def boom(*a, **k):
        raise RuntimeError("чат недоступен")

    monkeypatch.setattr("publishers.telegram_pub.send_photo", boom)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    await cf._send_frames([{"image": "https://x/1.png"}])   # не бросает
