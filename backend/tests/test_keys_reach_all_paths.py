"""Ключи из дашборда должны работать на всех путях Telegram, а не только в командах.

Симптом: в Подключениях ключи стоят, а свободный текст отвечает «нет ни одной
модели для анализа». Причина — окружение процесса обновлялось только в
обработчике слэш-команд, поэтому ключ, добавленный после старта сервера,
свободному тексту и медиа был не виден.
"""
import os

import pytest

from core import credentials, telegram_bot as tg
from core.ai_router import ai_available


@pytest.mark.asyncio
async def test_key_saved_in_dashboard_is_visible_at_once(client, monkeypatch):
    """Сохранение в дашборде сразу кладёт ключ в окружение процесса."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert not ai_available()

    await credentials.set("groq_api_key", "test-key")

    assert os.environ.get("GROQ_API_KEY") == "test-key"
    assert ai_available()


@pytest.mark.asyncio
async def test_free_text_picks_up_keys_added_after_start(client, monkeypatch):
    """Главный случай: ключ добавлен после старта, человек пишет текстом.

    Окружение процесса эмулирует «сервер стартовал раньше»: значение в базе есть,
    в os.environ — нет.
    """
    await credentials.set("groq_api_key", "test-key")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert not ai_available(), "подготовка: модель не должна быть видна"

    said = []
    monkeypatch.setattr(tg, "send_message",
                        lambda *a, **kw: said.append(a) or (lambda: None)())

    async def fake_plain(chat_id, text):
        # К этому моменту ключи уже должны быть подтянуты из базы.
        assert ai_available(), "свободный текст не увидел ключ из дашборда"

    monkeypatch.setattr(tg, "_plain_text", fake_plain)

    await tg._handle_plain_text("55", "проанализируй мою нишу")

    assert os.environ.get("GROQ_API_KEY") == "test-key"


@pytest.mark.asyncio
async def test_media_path_picks_up_keys_too(client, monkeypatch):
    """Голос и картинки тоже разбираются моделями — им нужны те же ключи."""
    await credentials.set("groq_api_key", "test-key")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    async def fake_handle_media(msg):
        assert ai_available(), "разбор медиа не увидел ключ из дашборда"
        return {}

    import core.tg_input as tg_input
    monkeypatch.setattr(tg_input, "handle_media", fake_handle_media)

    await tg._handle_media("55", {"voice": {"file_id": "x"}})

    assert os.environ.get("GROQ_API_KEY") == "test-key"
