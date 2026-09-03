"""Главная цепочка: Telegram → Cloud Opus → агенты → HIXIIT → Telegram.

Сайт в ней не участвует: раньше дирижёр запускался только из веб-роута,
и при выключенном сайте сложная задача из Telegram никуда не доходила.
"""
import pytest

from core import intent, marketing_director as md, telegram_bot as tg


def test_router_knows_about_the_director():
    """Роутер намерений должен уметь отдать задачу дирижёру, иначе всё, что не
    покрыто готовыми командами, превращается в разговор без действия."""
    assert "/director" in intent.INTENT_SYSTEM


def test_director_offers_generation_tools():
    names = {t["name"] for t in md.TOOLS}
    assert {"make_image", "make_video"} <= names


@pytest.mark.asyncio
async def test_generation_goes_through_hixiit(monkeypatch):
    """make_video без озвучки ведёт HIXIIT — он сам выбирает модель."""
    called = {}

    async def fake_generate(prompt, kind=None, ratio=None, image_url=None):
        called.update(prompt=prompt, kind=kind)
        return {"ok": True, "url": "https://x/y.mp4", "kind": kind}

    monkeypatch.setattr("core.hixiit.generate", fake_generate)

    res = await md._exec_tool("make_video", {"prompt": "кофе на столе"})

    assert res["url"] == "https://x/y.mp4"
    assert called["kind"] == "video"


@pytest.mark.asyncio
async def test_avatar_voiceover_still_goes_to_heygen(monkeypatch):
    """HeyGen незаменим для говорящего аватара — эту ветку ломать нельзя."""
    monkeypatch.setenv("HEYGEN_API_KEY", "test")
    used = {}

    async def fake_clip(prompt, script="", provider="auto", **kw):
        used.update(provider=provider, script=script)
        return {"ok": True, "url": "https://x/avatar.mp4"}

    monkeypatch.setattr("core.media_generator.generate_clip", fake_clip)

    await md._exec_tool("make_video", {"prompt": "ведущий", "script": "Привет!"})

    assert used["provider"] == "heygen"


@pytest.mark.asyncio
async def test_created_media_reaches_the_chat(monkeypatch):
    """Картинка и видео должны приходить файлом, а не ссылкой в тексте отчёта."""
    sent = []

    async def fake_photo(chat_id, photo, caption="", **kw):
        sent.append(("photo", photo))
        return {}

    async def fake_video(chat_id, video, caption="", **kw):
        sent.append(("video", video))
        return {}

    monkeypatch.setattr("publishers.telegram_pub.send_photo", fake_photo)
    monkeypatch.setattr("publishers.telegram_pub.send_video", fake_video)

    await tg._send_director_media("55", {"steps": [
        {"action": "make_image", "media_url": "https://x/a.png"},
        {"action": "make_video", "media_url": "https://x/b.mp4"},
        {"action": "publish", "media_url": "https://x/ignored.png"},
        {"action": "make_image"},
    ]})

    assert sent == [("photo", "https://x/a.png"), ("video", "https://x/b.mp4")]
