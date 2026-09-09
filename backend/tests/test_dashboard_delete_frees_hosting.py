"""
Удалил ключ на сайте — должна заработать переменная хостинга.

Значение из дашборда перекрывает переменную Render. Человек удаляет запись на
сайте именно затем, чтобы заработал ключ из Render. Раньше происходило
обратное: `delete()` выкидывал значение из окружения целиком, вместе с
переменной хостинга, а `load_into_env` не отменял ранее выгруженное — удалённая
запись продолжала жить в памяти процесса до перезапуска.
"""
import os

import pytest

from core import credentials as cr

ENV = "HIGGSFIELD_API_KEY"
HOSTING = "3f8c1a2b-4d5e-6f70-8192-a3b4c5d6e7f8"     # то, что вписали в Render
DASHBOARD = "a" * 64                                  # старое значение с сайта


@pytest.fixture
def hosting_value():
    """Процесс стартовал с переменной хостинга — как на Render."""
    before_env = os.environ.get(ENV)
    before_snapshot = cr._HOSTING_ENV.get(ENV)
    os.environ[ENV] = HOSTING
    cr._HOSTING_ENV[ENV] = HOSTING
    yield
    cr._EXPORTED.pop(ENV, None)
    if before_snapshot is None:
        cr._HOSTING_ENV.pop(ENV, None)
    else:
        cr._HOSTING_ENV[ENV] = before_snapshot
    if before_env is None:
        os.environ.pop(ENV, None)
    else:
        os.environ[ENV] = before_env


@pytest.mark.asyncio
async def test_deleting_on_the_site_brings_back_the_hosting_value(client, hosting_value):
    await cr.set(ENV.lower(), DASHBOARD)
    assert os.environ[ENV] == DASHBOARD, "дашборд перекрывает хостинг — так и задумано"

    await cr.delete(ENV.lower())

    assert os.environ[ENV] == HOSTING, \
        "именно ради этого значение и удаляют на сайте"


@pytest.mark.asyncio
async def test_reload_does_not_resurrect_the_deleted_value(client, hosting_value):
    """Следующая выгрузка не должна вернуть удалённое."""
    await cr.set(ENV.lower(), DASHBOARD)
    await cr.delete(ENV.lower())

    await cr.load_into_env()

    assert os.environ[ENV] == HOSTING


@pytest.mark.asyncio
async def test_value_removed_from_db_directly_is_also_undone(client, hosting_value):
    """Запись могли удалить мимо delete() — состояние всё равно обязано сойтись."""
    await cr.set(ENV.lower(), DASHBOARD)
    await cr.load_into_env()
    assert os.environ[ENV] == DASHBOARD

    from sqlalchemy import select
    from database.db import AsyncSessionLocal
    from database.models import Connection
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Connection).where(
            Connection.key_name == ENV.lower()))
        row = r.scalar_one_or_none()
        if row:
            await db.delete(row)
            await db.commit()

    res = await cr.load_into_env()

    assert ENV in (res.get("dropped") or [])
    assert os.environ[ENV] == HOSTING


@pytest.mark.asyncio
async def test_without_hosting_value_the_key_simply_disappears(client):
    """Переменной хостинга не было — после удаления не должно остаться ничего."""
    name = "RUNWAY_API_KEY"
    os.environ.pop(name, None)
    cr._HOSTING_ENV.pop(name, None)

    await cr.set(name.lower(), "some-value")
    assert os.environ[name] == "some-value"

    await cr.delete(name.lower())

    assert name not in os.environ
    cr._EXPORTED.pop(name, None)
