"""Здоровье системы: статусы агентов, вердикт, сводка планировщика."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import delete

from core import health
from database.db import AsyncSessionLocal
from database.models import AgentLog, Task


@pytest.fixture(autouse=True)
async def _clean(client):
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AgentLog))
        await db.execute(delete(Task))
        await db.commit()
    yield


async def _log(agent, status="success", cost=0.0, age_hours=1, error=None):
    async with AsyncSessionLocal() as db:
        db.add(AgentLog(niche_id="", agent_name=agent, status=status,
                        model_used="deepseek-chat", tokens_used=100, cost_usd=cost,
                        duration_sec=1.0, error=error,
                        created_at=datetime.utcnow() - timedelta(hours=age_hours)))
        await db.commit()


@pytest.mark.asyncio
async def test_healthy_agent_is_online(client):
    for _ in range(5):
        await _log("copywriter", cost=0.001)

    ag = {a["agent"]: a for a in await health.agents()}
    assert ag["copywriter"]["status"] == "online"
    assert ag["copywriter"]["success_rate"] == 100.0
    assert ag["copywriter"]["calls"] == 5
    assert ag["copywriter"]["cost_usd"] > 0


@pytest.mark.asyncio
async def test_failing_agent_is_degraded(client):
    """Агент, у которого падает больше пятой части вызовов, — не «онлайн»."""
    await _log("visual_creator")
    for _ in range(4):
        await _log("visual_creator", status="error", error="квота")

    ag = {a["agent"]: a for a in await health.agents()}
    assert ag["visual_creator"]["status"] == "degraded"
    assert ag["visual_creator"]["success_rate"] == 20.0


@pytest.mark.asyncio
async def test_silent_agent_is_visible_not_missing(client):
    """Молчащий агент обязан быть в списке: иначе сломанный джоб просто исчезает,
    и картина «всё зелено» врёт."""
    await _log("reporter", age_hours=72)

    ag = {a["agent"]: a for a in await health.agents(hours=24)}
    assert "reporter" in ag
    assert ag["reporter"]["status"] == "silent"
    assert ag["reporter"]["last_run"] is not None


@pytest.mark.asyncio
async def test_verdict_ok_when_everything_works(client, monkeypatch):
    await _log("copywriter")
    # «Всё работает» включает постоянную базу: с временным хранилищем зелёный
    # светофор обещал бы сохранность ключей, которой нет.
    monkeypatch.setattr("database.db.PERSISTENT", True)
    ov = await health.overview()
    assert ov["verdict"] == "ok"


@pytest.mark.asyncio
async def test_verdict_not_ok_on_temporary_storage(client):
    """В тестах база файловая — значит непостоянная, и это должно быть видно."""
    await _log("copywriter")
    ov = await health.overview()
    assert ov["storage"]["persistent"] is False
    assert ov["verdict"] == "degraded"


@pytest.mark.asyncio
async def test_verdict_degraded_on_failed_task(client):
    await _log("copywriter")
    from core import task_manager as tm
    task_id = await tm.create("factory", "Тест", source="scheduler")
    await tm.run(task_id, lambda: _boom())

    ov = await health.overview()
    assert ov["verdict"] in ("degraded", "broken")
    assert ov["tasks"]["failed"] == 1


async def _boom():
    raise RuntimeError("сломалось")


@pytest.mark.asyncio
async def test_scheduler_reports_honestly_when_not_running(client):
    """В тестах планировщик не поднят — это не ошибка, но и не «работает»."""
    st = health.scheduler_jobs()
    assert st["running"] is False
    assert st["jobs"] == []


@pytest.mark.asyncio
async def test_overview_api(auth_client):
    r = await auth_client.get("/api/system/health")
    assert r.status_code == 200
    body = r.json()
    for key in ("verdict", "agents", "social", "scheduler", "tasks",
                "publishing", "costs", "errors"):
        assert key in body


@pytest.mark.asyncio
async def test_agents_api(auth_client):
    await _log("strategist")
    r = await auth_client.get("/api/system/agents")
    assert any(a["agent"] == "strategist" for a in r.json()["agents"])


@pytest.mark.asyncio
async def test_system_health_requires_auth(client):
    r = await client.get("/api/system/health")
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_summary_is_short_and_answers_five_questions(auth_client):
    """Главная должна отвечать на пять вопросов ТЗ одним запросом."""
    body = (await auth_client.get("/api/system/summary")).json()
    assert set(body) >= {"system", "connections", "current_task",
                         "published_today", "errors"}
    assert isinstance(body["connections"], list)
    # Задач нет — значит и «текущей задачи» нет, а не выдуманный прогресс.
    assert body["current_task"] is None or "percent" in body["current_task"]
