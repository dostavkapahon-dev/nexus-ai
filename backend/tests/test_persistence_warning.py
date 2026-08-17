"""
Про временное хранилище система обязана говорить вслух.

Главная жалоба владельца — «ключи и настройки сбрасываются сами». Причина одна:
без внешней базы всё лежит в файле внутри контейнера Render, и деплой стирает
его вместе с ключами, памятью и проектами. Раньше об этом не сообщалось нигде,
поэтому потеря выглядела мистикой. Эти проверки следят, чтобы предупреждение
было видно во всех четырёх местах: в API здоровья, на главной, в общем
вердикте и в отчёте бота.
"""
import pytest

from database import db as dbmod


def test_sqlite_is_reported_as_temporary():
    """В тестах БД именно такая — файловая, то есть непостоянная."""
    info = dbmod.storage_info()
    assert info["kind"] == "sqlite"
    assert info["persistent"] is False
    assert "будут стёрты" in info["warning"], "предупреждение должно быть понятным"


def test_postgres_is_reported_as_persistent(monkeypatch):
    monkeypatch.setattr(dbmod, "DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    monkeypatch.setattr(dbmod, "PERSISTENT", True)
    info = dbmod.storage_info()
    assert info["persistent"] is True and info["warning"] == ""


@pytest.mark.asyncio
async def test_public_health_shows_storage(client):
    r = await client.get("/api/health")
    body = r.json()
    assert body["storage"]["persistent"] is False
    assert body["storage"]["warning"]


@pytest.mark.asyncio
async def test_home_summary_shows_storage(auth_client):
    body = (await auth_client.get("/api/system/summary")).json()
    assert body["storage"]["persistent"] is False, "главная не узнает о потере данных"


@pytest.mark.asyncio
async def test_system_is_not_green_on_temporary_storage(auth_client):
    """Зелёный светофор при хранилище, которое вот-вот всё сотрёт, — обман."""
    body = (await auth_client.get("/api/system/health")).json()
    assert body["storage"]["persistent"] is False
    assert body["verdict"] != "ok"


@pytest.mark.asyncio
async def test_bot_status_warns_too(client, monkeypatch):
    from core import telegram_bot as tb

    sent = []

    async def fake_send(chat_id, text, **kw):
        sent.append(text)
        return {}

    async def fake_report(db):
        return "Отчёт о системе"

    monkeypatch.setattr(tb, "send_message", fake_send)
    from agents.reporter import reporter
    monkeypatch.setattr(reporter, "build_status_report", fake_report)

    await tb._handle_command("1", "/status")
    assert sent and "Данные временные" in sent[0]
