"""Откуда взялся ключ Higgsfield — видно из Telegram, а не только из логов Render.

Значение из дашборда перекрывает переменную хостинга. Это правильное поведение,
но молчаливое: человек кладёт новый ключ в Render, ничего не меняется, и чинить
он идёт не туда. Раньше об этом сообщала одна строка в логе при старте.
"""
import pytest

from core import credentials, hixiit


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ("HIGGSFIELD_API_KEY", "HIGGSFIELD_SECRET", "HIGGSFIELD_MCP_URL"):
        monkeypatch.delenv(var, raising=False)
    credentials.LAST_LOAD.update({"shadowed": []})
    yield
    credentials.LAST_LOAD.update({"shadowed": []})


@pytest.mark.asyncio
async def test_missing_halves_are_named(client):
    src = {s["env"]: s for s in await hixiit._key_sources()}
    assert src["HIGGSFIELD_API_KEY"]["filled"] is False
    assert src["HIGGSFIELD_SECRET"]["source"] == "не задан"


@pytest.mark.asyncio
async def test_env_only_value_is_attributed_to_hosting(client, monkeypatch):
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "abcdefgh")

    src = {s["env"]: s for s in await hixiit._key_sources()}
    assert src["HIGGSFIELD_API_KEY"]["source"] == "переменная хостинга"
    # Хвост нужен, чтобы сверить с Render, не раскрывая ключ целиком.
    assert src["HIGGSFIELD_API_KEY"]["tail"] == "efgh"


@pytest.mark.asyncio
async def test_dashboard_shadowing_render_is_reported(client, monkeypatch):
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "from-dashboard")
    credentials.LAST_LOAD.update({"shadowed": ["HIGGSFIELD_API_KEY"]})

    src = {s["env"]: s for s in await hixiit._key_sources()}
    assert "перекрывает" in src["HIGGSFIELD_API_KEY"]["source"]


@pytest.mark.asyncio
async def test_load_into_env_records_the_conflict(client, monkeypatch):
    """Сам факт перекрытия фиксируется загрузчиком, а не выводится в лог и теряется."""
    await credentials.set("higgsfield_api_key", "dashboard-value")
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "render-value")

    res = await credentials.load_into_env()

    assert "HIGGSFIELD_API_KEY" in res["shadowed"]
    assert "HIGGSFIELD_API_KEY" in credentials.LAST_LOAD["shadowed"]
    await credentials.delete("higgsfield_api_key")
