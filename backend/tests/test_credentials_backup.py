"""
Ключи вводятся один раз: копия, проверка сохранности, подключение Клода.

Живая жалоба: «каждый раз ввожу ключи». Причина — временная база на Render, и
пока она не заменена, восстановление должно занимать одно действие. Здесь
проверяется, что копия действительно защищена паролем (иначе файл с ключами —
это утечка, а не спасение) и что восстановление возвращает всё на место.
"""
import pytest

from core import credentials, credentials_backup as backup


@pytest.fixture
async def _saved(client):
    await credentials.set("groq_api_key", "gsk-test-123")
    await credentials.set("telegram_bot_token", "111:AAA-token")
    yield
    for key in ("groq_api_key", "telegram_bot_token"):
        await credentials.delete(key)


# ─────────────────────────── копия ───────────────────────────

@pytest.mark.asyncio
async def test_backup_requires_a_real_password(client, _saved):
    res = await backup.export_all("123")
    assert res["ok"] is False and "8 символов" in res["error"]


@pytest.mark.asyncio
async def test_backup_contains_no_readable_secrets(client, _saved):
    res = await backup.export_all("длинный-пароль")
    assert res["ok"] and res["count"] == 2

    dump = str(res["file"])
    assert "gsk-test-123" not in dump, "ключ лежит в файле открытым текстом"
    assert "111:AAA-token" not in dump


@pytest.mark.asyncio
async def test_wrong_password_does_not_open_the_backup(client, _saved):
    res = await backup.export_all("правильный-пароль")
    out = await backup.import_all(res["file"], "неправильный-пароль")
    assert out["ok"] is False and "Неверный пароль" in out["error"]


@pytest.mark.asyncio
async def test_restore_brings_every_key_back(client, _saved):
    res = await backup.export_all("длинный-пароль")

    await credentials.delete("groq_api_key")
    await credentials.delete("telegram_bot_token")
    assert await credentials.get("groq_api_key") is None

    out = await backup.import_all(res["file"], "длинный-пароль")
    assert out["ok"] and out["restored"] == 2
    assert await credentials.get("groq_api_key") == "gsk-test-123"
    assert await credentials.get("telegram_bot_token") == "111:AAA-token"


@pytest.mark.asyncio
async def test_foreign_file_is_refused(client):
    out = await backup.import_all({"format": "что-то другое"}, "пароль12345")
    assert out["ok"] is False and "не файл резервной копии" in out["error"]


@pytest.mark.asyncio
async def test_restored_values_are_encrypted_again(client, _saved, monkeypatch):
    """После восстановления ключи должны лежать в базе так же защищённо."""
    from sqlalchemy import select

    from database.db import AsyncSessionLocal
    from database.models import Connection

    monkeypatch.setenv("NEXUS_SECRET_KEY", "серверный-ключ-шифрования")
    res = await backup.export_all("длинный-пароль")
    await backup.import_all(res["file"], "длинный-пароль")

    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Connection).where(Connection.key_name == "groq_api_key"))
        stored = r.scalar_one().key_value
    assert stored.startswith("enc:v1:"), "восстановленный ключ лежит открытым текстом"


# ─────────────────────────── проверка сохранности ───────────────────────────

@pytest.mark.asyncio
async def test_verify_says_data_will_be_lost(auth_client):
    body = (await auth_client.post("/api/connections/verify")).json()
    assert body["ok"] is True, "запись в базу должна работать"
    assert body["persistent"] is False
    assert "стёрты" in body["verdict"], "человек должен понять, что ключи пропадут"


@pytest.mark.asyncio
async def test_verify_leaves_no_probe_behind(auth_client):
    await auth_client.post("/api/connections/verify")
    assert await credentials.get("nexus_persistence_probe") is None


# ─────────────────────────── подключение Клода ───────────────────────────

@pytest.mark.asyncio
async def test_bad_claude_key_is_not_saved(auth_client, monkeypatch):
    async def refuse(*a, **kw):
        raise RuntimeError("401 Unauthorized: invalid api key")

    monkeypatch.setattr("core.ai_router.ai_router._call_claude", refuse)

    r = await auth_client.post("/api/connections/claude", json={"api_key": "sk-ant-плохой"})
    body = r.json()
    assert body["ok"] is False
    assert "Ключ не принят" in body["error"], "человеку нужна причина, а не код 401"
    assert await credentials.get("anthropic_api_key") is None, "нерабочий ключ сохранён"


@pytest.mark.asyncio
async def test_working_claude_key_is_saved_once(auth_client, monkeypatch):
    async def ok(*a, **kw):
        return {"text": "готово", "tokens": 3, "cost": 0.0}

    monkeypatch.setattr("core.ai_router.ai_router._call_claude", ok)

    r = await auth_client.post("/api/connections/claude", json={"api_key": "sk-ant-рабочий"})
    body = r.json()
    assert body["ok"] and "вручную больше не нужно" in body["message"]
    assert await credentials.get("anthropic_api_key") == "sk-ant-рабочий"

    await credentials.delete("anthropic_api_key")


# ─────────────────── служебные вызовы не идут в очередь ───────────────────

@pytest.mark.asyncio
async def test_self_check_does_not_queue_a_question(client, monkeypatch):
    """Именно этот дешёвый вызов первым приехал владельцу на ручную пересылку."""
    from core import ai_escrow, production_queue as pq, self_critique

    async def dead(*a, **kw):
        raise RuntimeError("Нет ни одного ключа ИИ")

    monkeypatch.setattr("core.ai_router.ai_router.call", dead)
    ai_escrow.interactive(source="telegram", chat_id="1")

    res = await self_critique.pre_check("content_factory", "ии тренды")
    assert res["checked"] is False and res["ready"] is True

    assert [j for j in await pq.jobs() if j["kind"] == "ai_task"] == [], \
        "служебная самопроверка не должна попадать в ручную очередь"


@pytest.mark.asyncio
async def test_task_work_never_gets_escrow_placeholder(client, monkeypatch):
    """Заглушка «запрос ушёл Клоду» внутри задачи уехала бы в текст поста."""
    from core import ai_escrow, task_manager as tm

    seen = {}

    async def work():
        seen["wanted"] = ai_escrow.wanted()
        return {"ok": True}

    ai_escrow.interactive(source="telegram", chat_id="1")
    task_id = await tm.create("factory", "проверка")
    await tm.run(task_id, work)

    assert seen["wanted"] is False
