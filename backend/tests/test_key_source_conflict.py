"""Ключ, заданный и в дашборде, и в переменных хостинга.

Побеждает дашборд — это правильно, человек редактирует именно там. Но молчать
об этом нельзя: положив новый ключ в Render поверх старого, сохранённого на
сайте, человек не увидит никакого эффекта и будет искать поломку не там.
"""
import os

import pytest

from core import credentials


@pytest.mark.asyncio
async def test_dashboard_value_wins_and_conflict_is_reported(client):
    os.environ["VK_ACCESS_TOKEN"] = "из-хостинга"
    await credentials.set("vk_access_token", "из-дашборда")
    os.environ["VK_ACCESS_TOKEN"] = "из-хостинга"  # хостинг выставляет своё при старте

    res = await credentials.load_into_env()

    assert os.environ["VK_ACCESS_TOKEN"] == "из-дашборда"
    assert "VK_ACCESS_TOKEN" in res["shadowed"], "конфликт источников должен быть виден"


@pytest.mark.asyncio
async def test_same_value_in_both_places_is_not_a_conflict(client):
    """Одинаковое значение — не повод тревожить человека."""
    await credentials.set("tiktok_access_token", "один-и-тот-же")
    os.environ["TIKTOK_ACCESS_TOKEN"] = "один-и-тот-же"

    res = await credentials.load_into_env()

    assert "TIKTOK_ACCESS_TOKEN" not in res["shadowed"]


@pytest.mark.asyncio
async def test_hosting_value_used_when_dashboard_is_empty(client):
    """Если в дашборде ничего нет — работает значение из хостинга."""
    await credentials.delete("threads_access_token")
    os.environ["THREADS_ACCESS_TOKEN"] = "только-хостинг"

    res = await credentials.load_into_env()

    assert os.environ["THREADS_ACCESS_TOKEN"] == "только-хостинг"
    assert "THREADS_ACCESS_TOKEN" not in res["shadowed"]


@pytest.mark.asyncio
async def test_deleting_in_dashboard_frees_the_hosting_value(client):
    """Способ отдать управление хостингу: удалить ключ в Подключениях.

    После удаления запись из базы больше не перекрывает переменную, и при
    следующем старте работает значение хостинга.
    """
    await credentials.set("vk_group_id", "из-дашборда")
    await credentials.delete("vk_group_id")

    os.environ["VK_GROUP_ID"] = "из-хостинга"
    await credentials.load_into_env()

    assert os.environ["VK_GROUP_ID"] == "из-хостинга"
