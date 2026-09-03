"""
Ключи переживают деплой, а очередь наполняется только при живом исполнителе.

Две живые жалобы. Первая: «вставлял Groq и другие, а показывает 2» — ключи,
сохранённые в вебе, стирались вместе с диском контейнера при каждом деплое,
уцелевали только заданные в переменных Render. Вторая: Клод должен работать по
подписке, а не через оплату API, — значит вопросы имеет смысл складывать в
очередь лишь тогда, когда исполнитель действительно на связи.
"""
import json

import pytest

from core import ai_escrow, credentials, credentials_backup as backup


@pytest.fixture(autouse=True)
async def _no_worker(client):
    """Отметка «исполнитель на связи» не должна утекать в соседние проверки:
    иначе они увидят живого Клода там, где его нет."""
    from sqlalchemy import delete

    from database.db import AsyncSessionLocal
    from database.models import Connection

    from database.models import ProductionJob

    async def wipe():
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Connection).where(Connection.key_name == ai_escrow.BEAT))
            # Задания, созданные здесь, тоже не должны всплывать у соседей.
            await db.execute(delete(ProductionJob))
            await db.commit()

    await wipe()
    yield
    await wipe()


@pytest.fixture
async def _keys(client):
    await credentials.set("groq_api_key", "gsk-живой")
    await credentials.set("cerebras_api_key", "csk-живой")
    yield
    for key in ("groq_api_key", "cerebras_api_key"):
        await credentials.delete(key)


# ─────────────────── копия ключей в переменной окружения ───────────────────

@pytest.mark.asyncio
async def test_keys_come_back_from_env_after_wipe(client, _keys, monkeypatch):
    """Ровно то, что происходит при деплое: диск очищен, переменные на месте."""
    dump = await backup.export_all("длинный-пароль")
    assert dump["ok"]

    await credentials.delete("groq_api_key")
    await credentials.delete("cerebras_api_key")
    assert await credentials.get("groq_api_key") is None

    monkeypatch.setenv(backup.ENV_BLOB, json.dumps(dump["file"]))
    monkeypatch.setenv(backup.ENV_PASSWORD, "длинный-пароль")

    res = await backup.restore_from_env()
    assert res["ok"] and res["restored"] >= 2
    assert await credentials.get("groq_api_key") == "gsk-живой"
    assert await credentials.get("cerebras_api_key") == "csk-живой"


@pytest.mark.asyncio
async def test_missing_password_is_explained(client, monkeypatch):
    monkeypatch.setenv(backup.ENV_BLOB, '{"format": "nexus-credentials-v1"}')
    monkeypatch.delenv(backup.ENV_PASSWORD, raising=False)
    res = await backup.restore_from_env()
    assert res["ok"] is False and backup.ENV_PASSWORD in res["error"]


@pytest.mark.asyncio
async def test_no_backup_is_not_an_error(client, monkeypatch):
    """Копии нет — это обычная ситуация, а не поломка старта."""
    monkeypatch.delenv(backup.ENV_BLOB, raising=False)
    res = await backup.restore_from_env()
    assert res["ok"] is False and "skipped" in res


@pytest.mark.asyncio
async def test_broken_blob_does_not_break_startup(client, monkeypatch):
    monkeypatch.setenv(backup.ENV_BLOB, "не json")
    monkeypatch.setenv(backup.ENV_PASSWORD, "пароль12345")
    res = await backup.restore_from_env()
    assert res["ok"] is False and "не разобран" in res["error"]


# ─────────────────────────── видно все ИИ ───────────────────────────

@pytest.mark.asyncio
async def test_diag_lists_free_providers_with_source(client, _keys, monkeypatch):
    """Подключённый Groq раньше в диагностике не упоминался вовсе."""
    from core import telegram_bot as tb

    monkeypatch.setenv("GROQ_API_KEY", "gsk-живой")
    lines = await tb._provider_lines()
    text = "\n".join(lines)

    assert "Groq" in text, "бесплатные провайдеры не показываются"
    assert "база" in text, "не видно, что этот ключ пропадёт при деплое"


@pytest.mark.asyncio
async def test_env_key_is_marked_as_surviving(client, monkeypatch):
    from core import telegram_bot as tb

    monkeypatch.setenv("MISTRAL_API_KEY", "из-окружения")
    text = "\n".join(await tb._provider_lines())
    assert "Mistral" in text and "переменные Render" in text


# ─────────────────────── очередь и живой исполнитель ───────────────────────

@pytest.mark.asyncio
async def test_queue_waits_for_a_live_worker(client):
    """Без исполнителя вопрос в очередь не кладём: его никто не прочитает."""
    ai_escrow.interactive(source="telegram", chat_id="1")
    assert await ai_escrow.worker_alive() is False

    with pytest.raises(RuntimeError):
        await ai_escrow.ask("сис", "вопрос без исполнителя")


@pytest.mark.asyncio
async def test_worker_beat_opens_the_queue(client, monkeypatch):
    async def yes(text):
        return True

    monkeypatch.setattr("core.notify.notify_owner", yes)

    await ai_escrow.worker_beat()
    assert await ai_escrow.worker_alive() is True

    ai_escrow.interactive(source="telegram", chat_id="1")
    assert "Клоду" in await ai_escrow.ask("сис", "вопрос с исполнителем")


@pytest.mark.asyncio
async def test_stale_worker_is_not_alive(client, monkeypatch):
    from datetime import datetime, timedelta

    from sqlalchemy import select

    from database.db import AsyncSessionLocal
    from database.models import Connection

    await ai_escrow.worker_beat()
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Connection).where(Connection.key_name == ai_escrow.BEAT))
        row = r.scalar_one()
        row.key_value = (datetime.utcnow() - timedelta(minutes=10)).isoformat()
        await db.commit()

    assert await ai_escrow.worker_alive() is False, "ушедший исполнитель считается живым"


@pytest.mark.asyncio
async def test_worker_api(auth_client):
    assert (await auth_client.post("/api/production/worker/beat")).json()["ok"] is True
    body = (await auth_client.get("/api/production/worker")).json()
    assert body["alive"] is True and "на связи" in body["note"]
