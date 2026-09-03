"""
Шифрование доступов и единый слой их чтения.

Главное, что здесь проверяется: включение шифрования ничего не ломает.
Код по всей системе читает ключи через `os.getenv`, поэтому в окружении всегда
должно оказываться открытое значение — независимо от того, как оно лежит в базе.
"""
import os

import pytest
from sqlalchemy import select

from core import credentials, secrets
from database.db import AsyncSessionLocal
from database.models import Connection


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setenv("NEXUS_SECRET_KEY", "тестовый-ключ-шифрования")
    return "тестовый-ключ-шифрования"


async def _raw(key_name: str) -> str:
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Connection).where(Connection.key_name == key_name))
        c = r.scalar_one_or_none()
        return c.key_value if c else ""


def test_without_key_values_stay_as_is(monkeypatch):
    monkeypatch.delenv("NEXUS_SECRET_KEY", raising=False)
    assert secrets.enabled() is False
    assert secrets.encrypt("sk-test") == "sk-test"
    assert secrets.decrypt("sk-test") == "sk-test"


def test_round_trip(with_key):
    box = secrets.encrypt("sk-secret-value")
    assert box.startswith("enc:v1:") and "sk-secret-value" not in box
    assert secrets.decrypt(box) == "sk-secret-value"


def test_encrypted_value_is_unreadable_without_key(with_key, monkeypatch):
    box = secrets.encrypt("sk-secret-value")
    monkeypatch.delenv("NEXUS_SECRET_KEY", raising=False)
    # None, а не пустая строка: «нечем прочитать» и «ключа нет» — разные вещи.
    assert secrets.decrypt(box) is None


def test_wrong_key_does_not_crash(with_key, monkeypatch):
    box = secrets.encrypt("sk-secret-value")
    monkeypatch.setenv("NEXUS_SECRET_KEY", "другой-ключ")
    assert secrets.decrypt(box) is None


@pytest.mark.asyncio
async def test_set_encrypts_but_env_stays_plain(client, with_key):
    await credentials.set("openai_api_key", "sk-plain-123456")
    assert secrets.is_encrypted(await _raw("openai_api_key"))
    # Весь остальной код читает ключ отсюда — значит здесь он открытый.
    assert os.getenv("OPENAI_API_KEY") == "sk-plain-123456"
    assert await credentials.get("openai_api_key") == "sk-plain-123456"
    await credentials.delete("openai_api_key")


@pytest.mark.asyncio
async def test_startup_encrypts_previously_saved_keys(client, monkeypatch):
    """Включили шифрование — старые записи должны дошифроваться, иначе
    пользователь считает, что защитил ключи, а они лежат открытым текстом."""
    monkeypatch.delenv("NEXUS_SECRET_KEY", raising=False)
    await credentials.set("groq_api_key", "gsk-old-value")
    assert await _raw("groq_api_key") == "gsk-old-value"

    monkeypatch.setenv("NEXUS_SECRET_KEY", "новый-ключ")
    res = await credentials.load_into_env()
    assert res["encrypted_now"] >= 1
    assert secrets.is_encrypted(await _raw("groq_api_key"))
    assert os.getenv("GROQ_API_KEY") == "gsk-old-value"
    await credentials.delete("groq_api_key")


@pytest.mark.asyncio
async def test_startup_survives_missing_key(client, monkeypatch):
    """Пропавший ключ шифрования не должен ронять старт сервера."""
    monkeypatch.setenv("NEXUS_SECRET_KEY", "ключ-который-потеряется")
    await credentials.set("mistral_api_key", "mk-123456")
    os.environ.pop("MISTRAL_API_KEY", None)

    monkeypatch.delenv("NEXUS_SECRET_KEY", raising=False)
    res = await credentials.load_into_env()
    assert res["unreadable"] >= 1
    assert os.getenv("MISTRAL_API_KEY") is None

    monkeypatch.setenv("NEXUS_SECRET_KEY", "ключ-который-потеряется")
    await credentials.delete("mistral_api_key")


@pytest.mark.asyncio
async def test_api_shows_masked_plain_value_when_encrypted(auth_client, with_key):
    """В интерфейсе видна маска настоящего ключа, а не обрывок шифротекста."""
    await auth_client.post("/api/connections", json={"openai_api_key": "sk-abcdefgh1234"})
    got = (await auth_client.get("/api/connections")).json()
    assert got["openai_api_key"] == "sk-a****1234"
    await auth_client.delete("/api/connections/openai_api_key")


def test_schema_covers_groups_from_spec():
    groups = {f["group"] for f in credentials.schema()}
    assert {"instagram", "tiktok", "telegram", "google", "ai", "storage"} <= groups


@pytest.mark.asyncio
async def test_status_endpoint_reports_source_and_date(auth_client, with_key):
    await auth_client.post("/api/connections", json={"vk_access_token": "vk1.a-token-123"})

    body = (await auth_client.get("/api/connections/status")).json()
    item = next(i for i in body["items"] if i["key"] == "vk_access_token")
    assert item["connected"] and item["source"] == "db"
    assert item["masked"] == "vk1.****-123"        # маска настоящего ключа, не шифротекста
    assert item["connected_at"]                     # дата подключения видна
    assert body["storage"]["enabled"] is True

    await auth_client.delete("/api/connections/vk_access_token")
    body = (await auth_client.get("/api/connections/status")).json()
    item = next(i for i in body["items"] if i["key"] == "vk_access_token")
    assert item["connected"] is False


@pytest.mark.asyncio
async def test_status_marks_unreadable_key(auth_client, with_key, monkeypatch):
    """Ключ, который нечем расшифровать, — это не «не подключено»."""
    await auth_client.post("/api/connections", json={"groq_api_key": "gsk-1234567890"})
    monkeypatch.delenv("NEXUS_SECRET_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    body = (await auth_client.get("/api/connections/status")).json()
    item = next(i for i in body["items"] if i["key"] == "groq_api_key")
    assert item["unreadable"] is True and item["connected"] is True
    assert body["storage"]["enabled"] is False


@pytest.mark.asyncio
async def test_recheck_unknown_key(auth_client):
    r = await auth_client.post("/api/connections/нет_такого/recheck")
    assert r.json()["ok"] is False
