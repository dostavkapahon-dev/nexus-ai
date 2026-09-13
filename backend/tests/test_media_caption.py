"""Под картинкой должно быть видно, кто её сделал и по какому тексту.

Жалоба: «создал не то, не из моих слов, качество плохое». Разобрать её было
нечем: наружу уходила голая картинка. А цепочка при отказе Higgsfield молча
съезжает вплоть до бесплатного Pollinations — результат заметно хуже, и
человек не знает почему. Плюс промпт по дороге переписывается обогатителем.
"""
import pytest

from core import telegram_bot as tb


def _step(provider="higgsfield_api", model="soul_2", prompt="шашлык", note=""):
    return {"action": "make_image", "media_url": "https://x/1.png",
            "media_provider": provider, "media_model": model,
            "media_prompt": prompt, "media_note": note}


def test_caption_names_the_provider():
    assert "Higgsfield" in tb._media_caption(_step())


def test_caption_names_the_model():
    assert "soul_2" in tb._media_caption(_step())


def test_caption_shows_the_prompt_actually_used():
    """«Не из моих слов» проверяется только так."""
    assert "шашлык" in tb._media_caption(_step(prompt="шашлык на мангале"))


def test_free_generator_is_flagged():
    text = tb._media_caption(_step(provider="pollinations_free", model="free"))
    assert "⚠️" in text and "качество ниже" in text


def test_free_generator_points_to_diagnosis():
    text = tb._media_caption(_step(provider="pollinations_free"))
    assert "/hixiit" in text


def test_paid_provider_is_not_flagged():
    assert "качество ниже" not in tb._media_caption(_step())


def test_note_is_shown():
    text = tb._media_caption(_step(note="выбрана другая модель"))
    assert "выбрана другая модель" in text


def test_unknown_provider_does_not_crash():
    assert tb._media_caption({"action": "make_image"})


def test_caption_fits_telegram_limit():
    long = tb._media_caption(_step(prompt="x" * 5000, note="y" * 5000))
    assert len(long) <= 1000


@pytest.mark.asyncio
async def test_caption_reaches_send_photo(monkeypatch):
    seen = {}

    async def fake_photo(chat_id, url, caption):
        seen["caption"] = caption
        return {}

    async def fake_video(chat_id, url, caption):
        return {}

    monkeypatch.setattr("publishers.telegram_pub.send_photo", fake_photo)
    monkeypatch.setattr("publishers.telegram_pub.send_video", fake_video)
    await tb._send_director_media("1", {"steps": [_step()]})
    assert "Higgsfield" in seen["caption"]
