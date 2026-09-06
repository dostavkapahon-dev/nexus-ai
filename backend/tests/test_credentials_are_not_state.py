"""Таблица доступов служит и KV-складом состояния. Смешивать их нельзя.

Лента Командного центра, история диалога и состояние автопилота лежат в той же
таблице `connections`, что и ключи. Раньше загрузчик выгружал их в переменные
окружения наравне с доступами, а меняющаяся лента выглядела как «ключ задан и в
дашборде, и в хостинге» — с советом удалить её в Подключениях.
"""
import os

import pytest
from sqlalchemy import delete

from core import credentials
from database.db import AsyncSessionLocal
from database.models import Connection


@pytest.fixture(autouse=True)
async def _clean(client):
    """Тесты трогают общую таблицу и общее окружение процесса — убираем за собой,
    иначе соседние проверки видят чужие ключи и ленту."""
    yield
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Connection).where(
            Connection.key_name.in_(["control_feed", "perplexity_api_key"])))
        await db.commit()
    os.environ.pop("PERPLEXITY_API_KEY", None)
    credentials._EXPORTED.pop("PERPLEXITY_API_KEY", None)


def test_internal_state_is_not_a_credential():
    assert credentials.is_credential("control_feed") is False
    assert credentials.is_credential("dialog_12345") is False
    assert credentials.is_credential("autopilot_state") is False


def test_real_credentials_are_still_recognised():
    for key in ("higgsfield_api_key", "instagram_access_token", "ig_handle",
                "nexus_browser_storage_state", "vk_group_id"):
        assert credentials.is_credential(key) is True, key


@pytest.mark.asyncio
async def test_feed_does_not_reach_the_environment(client, monkeypatch):
    """Лента событий в окружении никому не нужна и только мешает."""
    monkeypatch.delenv("CONTROL_FEED", raising=False)
    from core import command_center
    await command_center.log_event("telegram", "user", "привет")

    await credentials.load_into_env()

    assert "CONTROL_FEED" not in os.environ
    assert "CONTROL_FEED" not in credentials.LAST_LOAD["shadowed"]


@pytest.mark.asyncio
async def test_changing_state_is_not_reported_as_a_key_conflict(client, monkeypatch):
    """Именно это видел пользователь: совет удалить ленту как «лишний ключ»."""
    from core import command_center

    await command_center.log_event("telegram", "user", "первое")
    await credentials.load_into_env()
    await command_center.log_event("telegram", "user", "второе")

    res = await credentials.load_into_env()

    assert "CONTROL_FEED" not in res["shadowed"]


@pytest.mark.asyncio
async def test_own_previous_export_is_not_a_conflict(client, monkeypatch):
    """Правка ключа в дашборде — не конфликт с хостингом: прошлое значение в
    окружении положили мы сами на предыдущей загрузке."""
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

    await credentials.set("perplexity_api_key", "старый")
    await credentials.load_into_env()
    await credentials.set("perplexity_api_key", "новый")

    res = await credentials.load_into_env()

    assert "PERPLEXITY_API_KEY" not in res["shadowed"]
    assert os.environ["PERPLEXITY_API_KEY"] == "новый"


@pytest.mark.asyncio
async def test_real_conflict_with_hosting_is_still_reported(client, monkeypatch):
    """Настоящее перекрытие переменной хостинга скрывать нельзя."""
    # Порядок как в жизни: значение из дашборда лежит в базе, а переменная
    # хостинга уже стоит в окружении к моменту загрузки. monkeypatch здесь не
    # годится: он вернёт значение обратно после теста, и ключ утечёт к соседям.
    await credentials.set("perplexity_api_key", "из-дашборда")
    os.environ["PERPLEXITY_API_KEY"] = "из-render"

    res = await credentials.load_into_env()

    assert "PERPLEXITY_API_KEY" in res["shadowed"]
