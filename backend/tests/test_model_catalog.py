"""Каталог моделей для интерфейса.

Список моделей жил отдельной копией в React и отставал: бесплатных провайдеров
в нём не было вовсе, поэтому выбрать Groq или Cerebras в настройках агента было
нельзя, хотя роутер их поддерживает.
"""
import pytest


@pytest.mark.asyncio
async def test_catalog_endpoint_lists_models(auth_client):
    r = await auth_client.get("/api/prompts/models")
    assert r.status_code == 200

    models = r.json()["models"]
    values = {m["value"] for m in models}

    assert "claude-sonnet-4-6" in values
    assert "groq-free" in values, "бесплатные провайдеры должны быть доступны для выбора"
    assert all({"value", "label", "group", "connected"} <= set(m) for m in models)


@pytest.mark.asyncio
async def test_connected_flag_follows_the_keys(auth_client, monkeypatch):
    """Человек должен видеть, какая модель реально заработает."""
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    r = await auth_client.get("/api/prompts/models")
    by_value = {m["value"]: m for m in r.json()["models"]}

    assert by_value["groq-free"]["connected"] is True
    assert by_value["claude-sonnet-4-6"]["connected"] is False


@pytest.mark.asyncio
async def test_models_route_is_not_swallowed_by_agent_route(auth_client):
    """`/prompts/models` не должен попасть в обработчик `/prompts/{agent_name}`."""
    r = await auth_client.get("/api/prompts/models")
    assert "models" in r.json(), "маршрут перехвачен обработчиком агента"
