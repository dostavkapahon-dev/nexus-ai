"""Система задач: статусы, ошибки, retry, восстановление после рестарта, API."""
import pytest

from core import task_manager as tm


@pytest.mark.asyncio
async def test_task_completes_and_records_result(client):
    task_id = await tm.create("factory", "тестовая задача", source="api")
    assert task_id.startswith("TASK-")

    created = await tm.get(task_id)
    assert created["status"] == tm.CREATED

    async def work():
        return {"ok": True, "theme": "тема"}

    out = await tm.run(task_id, work)
    assert out["ok"] is True

    done = await tm.get(task_id)
    assert done["status"] == tm.COMPLETED
    assert done["attempts"] == 1
    assert done["result"]["theme"] == "тема"
    assert done["error"] is None
    assert done["finished_at"] is not None


@pytest.mark.asyncio
async def test_failure_is_recorded_not_swallowed(client):
    """Упавшая задача обязана оставить статус FAILED и текст ошибки."""
    task_id = await tm.create("publish", "падающая задача")

    async def boom():
        raise RuntimeError("публикация отвалилась")

    out = await tm.run(task_id, boom)
    assert out["ok"] is False

    failed = await tm.get(task_id)
    assert failed["status"] == tm.FAILED
    assert "публикация отвалилась" in failed["error"]


@pytest.mark.asyncio
async def test_retry_succeeds_on_second_attempt(client):
    task_id = await tm.create("publish", "со второй попытки")
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("временный сбой")
        return {"ok": True}

    out = await tm.run(task_id, flaky, max_attempts=2)
    assert out["ok"] is True

    t = await tm.get(task_id)
    assert t["status"] == tm.COMPLETED
    assert t["attempts"] == 2


@pytest.mark.asyncio
async def test_recover_stuck_marks_lost_tasks(client):
    """Задача, зависшая в RUNNING с прошлого запуска, не должна висеть вечно."""
    from datetime import datetime, timedelta

    task_id = await tm.create("pipeline", "зависшая")
    old = datetime.utcnow() - timedelta(minutes=tm.STUCK_AFTER_MIN + 5)
    await tm._patch(task_id, status=tm.RUNNING, started_at=old)

    n = await tm.recover_stuck()
    assert n >= 1

    t = await tm.get(task_id)
    assert t["status"] == tm.FAILED
    assert "перезапуск" in (t["error"] or "").lower()


@pytest.mark.asyncio
async def test_steps_and_cost_accumulate(client):
    task_id = await tm.create("director", "с шагами")
    await tm.add_step(task_id, "анализ аккаунта", ok=True, agent="analyze")
    await tm.add_step(task_id, "генерация", ok=False, agent="copywriter", error="нет ключа")
    await tm.add_cost(task_id, model="deepseek-chat", tokens=1200, cost=0.0014)
    await tm.add_cost(task_id, model="gemini-2.0-flash", tokens=800, cost=0.0002)

    t = await tm.get(task_id)
    assert len(t["steps"]) == 2
    assert t["steps"][1]["ok"] is False
    assert set(t["agents"]) == {"analyze", "copywriter"}
    assert t["tokens"] == 2000
    assert t["cost_usd"] == pytest.approx(0.0016)
    assert len(t["models"]) == 2


@pytest.mark.asyncio
async def test_cancel_only_active_tasks(client):
    task_id = await tm.create("factory", "к отмене")
    assert await tm.cancel(task_id) is True
    assert (await tm.get(task_id))["status"] == tm.CANCELLED
    # Повторная отмена уже завершённой задачи не проходит.
    assert await tm.cancel(task_id) is False


@pytest.mark.asyncio
async def test_api_lists_and_filters_tasks(auth_client):
    await tm.create("factory", "для списка")
    failed_id = await tm.create("publish", "для фильтра")
    await tm._patch(failed_id, status=tm.FAILED, error="тест")

    r = await auth_client.get("/api/tasks")
    assert r.status_code == 200
    assert any(t["id"] == failed_id for t in r.json()["tasks"])

    r2 = await auth_client.get("/api/tasks", params={"status": "FAILED"})
    assert all(t["status"] == tm.FAILED for t in r2.json()["tasks"])

    r3 = await auth_client.get(f"/api/tasks/{failed_id}")
    assert r3.json()["error"] == "тест"

    r4 = await auth_client.get("/api/tasks/stats")
    assert r4.json()["total"] >= 2


@pytest.mark.asyncio
async def test_tasks_require_auth(client):
    r = await client.get("/api/tasks")
    assert r.status_code == 401
