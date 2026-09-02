"""Результат работы доходит до владельца — или об этом честно сообщается.

Три бага одной цепочки, из-за которых «сгенерировал, но в Telegram ничего не
прислал» выглядело как молчание системы:
  1) адресат уведомлений читался только из TELEGRAM_CHAT_ID, хотя владельца
     штатно закрепляет первый /start;
  2) ответ Telegram не проверялся: `ok:false` («не смог забрать картинку по
     ссылке») считался успехом;
  3) бесплатный генератор изображений отчитывался об успехе, ни разу не сходив
     по собственной ссылке.
"""
import pytest

from core import media_generator, moderation, notify
from database.db import init_db


# ─────────────────────────── 1. кому писать ───────────────────────────

@pytest.mark.asyncio
async def test_owner_from_start_is_a_valid_address(monkeypatch):
    """Владелец закреплён через /start, TELEGRAM_CHAT_ID не задан — это штатная
    установка, и она не должна означать «писать некому»."""
    await init_db()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    from core import telegram_owner
    telegram_owner._cache = None
    await telegram_owner.claim("555")

    assert await notify.owner_chat() == "555"


@pytest.mark.asyncio
async def test_env_owner_wins_over_claimed(monkeypatch):
    """Явно заданный владелец — ручное указание, оно сильнее самозахвата."""
    await init_db()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
    assert await notify.owner_chat() == "999"


@pytest.mark.asyncio
async def test_no_bot_token_means_nobody_to_write_to(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
    assert await notify.owner_chat() == ""


@pytest.mark.asyncio
async def test_approval_reaches_owner_claimed_by_start(monkeypatch):
    """Главный симптом: контент готов, а на согласование не уходит."""
    await init_db()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    from core import telegram_owner
    telegram_owner._cache = None
    await telegram_owner.claim("555")

    sent = []

    async def fake_tg(method, payload):
        sent.append((method, payload))
        return {"ok": True}

    monkeypatch.setattr(moderation, "_tg", fake_tg)
    pid = await moderation.send_for_approval("готовый пост")

    assert pid, "материал не ушёл на согласование"
    assert sent and sent[0][1]["chat_id"] == "555"


# ────────────────────── 2. отказ Telegram виден ──────────────────────

@pytest.mark.asyncio
async def test_unfetchable_image_still_delivers_the_post(monkeypatch):
    """Telegram не смог забрать картинку по ссылке. Текст с кнопками важнее
    картинки: без запасного хода вся работа пропадала молча."""
    await init_db()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")

    calls = []

    async def fake_tg(method, payload):
        calls.append((method, payload))
        if method == "sendPhoto":
            return {"ok": False, "description": "failed to get HTTP URL content"}
        return {"ok": True}

    monkeypatch.setattr(moderation, "_tg", fake_tg)
    await moderation.send_for_approval("текст поста", media_url="https://x/img.png")

    methods = [m for m, _ in calls]
    assert methods == ["sendPhoto", "sendMessage"], "не было запасной отправки текстом"
    fallback = calls[1][1]["text"]
    assert "текст поста" in fallback and "https://x/img.png" in fallback
    assert "failed to get HTTP URL content" in fallback, "причина не показана"
    assert calls[1][1]["reply_markup"], "кнопки согласования потерялись"


@pytest.mark.asyncio
async def test_queued_even_if_telegram_refuses(monkeypatch):
    """Отправка не удалась — материал всё равно в очереди, его видно в вебе."""
    await init_db()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")

    async def fake_tg(method, payload):
        return {"ok": False, "description": "chat not found"}

    monkeypatch.setattr(moderation, "_tg", fake_tg)
    pid = await moderation.send_for_approval("текст")

    assert await moderation._get_item(pid) is not None


# ─────────────── 3. «картинка готова» означает, что она есть ───────────────

@pytest.mark.asyncio
async def test_dead_image_link_is_not_reported_as_success(monkeypatch):
    """Ссылка собирается мгновенно, а рисуется картинка на первом запросе.
    Пока по ссылке никто не сходил, успех — это предположение, а не факт."""
    tracked = []

    async def fake_track(provider, kind, ok, elapsed=0.0, error=None):
        tracked.append({"provider": provider, "ok": ok, "error": error})

    async def dead(url, attempts=2):
        return False, "генератор изображений не отдал картинку (HTTP 502, тип «—»)"

    monkeypatch.setattr(media_generator, "_track_media", fake_track)
    monkeypatch.setattr(media_generator, "_image_responds", dead)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("STABILITY_API_KEY", raising=False)

    await media_generator.generate_image("кадр")

    assert tracked and tracked[-1]["ok"] is False
    assert "не отдал картинку" in tracked[-1]["error"]


@pytest.mark.asyncio
async def test_live_image_link_is_reported_as_success(monkeypatch):
    tracked = []

    async def fake_track(provider, kind, ok, elapsed=0.0, error=None):
        tracked.append(ok)

    async def alive(url, attempts=2):
        return True, ""

    monkeypatch.setattr(media_generator, "_track_media", fake_track)
    monkeypatch.setattr(media_generator, "_image_responds", alive)
    for k in ("GEMINI_API_KEY", "OPENAI_API_KEY", "STABILITY_API_KEY"):
        monkeypatch.delenv(k, raising=False)

    url = await media_generator.generate_image("кадр")

    assert url.startswith("https://image.pollinations.ai/")
    assert tracked == [True]
