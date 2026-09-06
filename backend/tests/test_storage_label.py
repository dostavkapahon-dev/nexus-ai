"""Пометка «пропадёт при деплое» должна зависеть от хранилища, а не от места.

Ключ в базе теряется только при временном хранилище. При подключённой внешней
базе (DATABASE_URL) он не пропадает — и приписка про деплой пугает зря: она
заставляет заново настраивать то, что уже настроено.
"""
import pytest

from core import telegram_bot


@pytest.fixture(autouse=True)
async def _key(client, monkeypatch):
    from core import credentials
    monkeypatch.setenv("MISTRAL_API_KEY", "тест")
    await credentials.set("mistral_api_key", "тест")
    yield
    await credentials.delete("mistral_api_key")


@pytest.mark.asyncio
async def test_persistent_storage_has_no_scary_note(client, monkeypatch):
    monkeypatch.setattr("database.db.storage_info",
                        lambda: {"kind": "postgres", "persistent": True, "warning": ""})

    lines = await telegram_bot._provider_lines()
    mistral = [l for l in lines if "Mistral" in l][0]

    assert "база" in mistral
    assert "пропадёт" not in mistral, "с внешней базой ключ не теряется"


@pytest.mark.asyncio
async def test_ephemeral_storage_still_warns(client, monkeypatch):
    """Предупреждение нужное — при временном диске его скрывать нельзя."""
    monkeypatch.setattr("database.db.storage_info",
                        lambda: {"kind": "sqlite", "persistent": False, "warning": "x"})

    lines = await telegram_bot._provider_lines()
    assert "пропадёт при деплое" in [l for l in lines if "Mistral" in l][0]
