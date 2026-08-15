"""
Хранение ключей: маскировка и удаление.

Проверяется то, из-за чего пользователь не мог доверять экрану подключений:
короткий ключ выглядел несохранённым, а удалить ключ было нечем.
"""
import os

import pytest
from sqlalchemy import select

from database.db import AsyncSessionLocal
from database.models import Connection


@pytest.mark.asyncio
async def test_save_then_delete_key(auth_client):
    r = await auth_client.post("/api/connections", json={"vk_group_id": "12345"})
    assert r.json()["ok"] is True

    r = await auth_client.get("/api/connections")
    assert r.json()["vk_group_id"] == "*****"
    assert os.getenv("VK_GROUP_ID") == "12345"

    r = await auth_client.delete("/api/connections/vk_group_id")
    assert r.json()["ok"] is True

    # Ушло и из БД, и из окружения — иначе «удалил, а оно работает».
    assert "vk_group_id" not in (await auth_client.get("/api/connections")).json()
    assert os.getenv("VK_GROUP_ID") is None
    async with AsyncSessionLocal() as db:
        rows = await db.execute(select(Connection).where(Connection.key_name == "vk_group_id"))
        assert rows.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_delete_missing_key_says_so(auth_client):
    r = await auth_client.delete("/api/connections/такого_нет")
    assert r.json() == {"ok": False, "error": "ключ не найден"}


@pytest.mark.asyncio
async def test_masked_value_does_not_overwrite_saved_key(auth_client):
    """Дашборд присылает маски обратно — они не должны затирать настоящий ключ."""
    await auth_client.post("/api/connections", json={"vk_access_token": "vk1.a-real-token"})
    await auth_client.post("/api/connections", json={"vk_access_token": "vk1.****oken"})
    assert os.getenv("VK_ACCESS_TOKEN") == "vk1.a-real-token"
    await auth_client.delete("/api/connections/vk_access_token")
