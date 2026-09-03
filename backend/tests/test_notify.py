"""Отчёты о задачах в Telegram и сводка ошибок."""
import pytest
from sqlalchemy import delete

from core import notify
from core import task_manager as tm
from database.db import AsyncSessionLocal
from database.models import Task, AgentLog


@pytest.fixture(autouse=True)
async def _clean(client):
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Task))
        await db.execute(delete(AgentLog))
        await db.commit()
    yield


@pytest.fixture
def sent(monkeypatch):
    """Перехватываем отправку в Telegram: сеть в тестах не трогаем."""
    box = []
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")

    async def fake_send(chat_id, text, *a, **kw):
        box.append((chat_id, text))

    import core.telegram_bot as tb
    monkeypatch.setattr(tb, "send_message", fake_send)
    return box


async def _boom():
    raise RuntimeError("провайдер вернул 500")


async def _ok():
    return {"ok": True}


async def _awaiting():
    return {"ok": True, "awaiting_approval": True}


@pytest.mark.asyncio
async def test_failed_task_reports_itself(client, sent):
    """Раньше о провале ночного джоба узнавали только зайдя в /tasks."""
    task_id = await tm.create("factory", "Ночная фабрика", source="scheduler")
    await tm.run(task_id, lambda: _boom())

    assert len(sent) == 1
    chat, text = sent[0]
    assert chat == "42"
    assert "провалилась" in text
    assert "провайдер вернул 500" in text     # причина в отчёте, иначе чинить нечего
    assert task_id in text


@pytest.mark.asyncio
async def test_successful_background_job_is_silent(client, sent):
    """Успех фонового джоба молчалив — иначе в потоке «всё хорошо» тонут проблемы."""
    task_id = await tm.create("metrics", "Сбор метрик", source="scheduler")
    await tm.run(task_id, lambda: _ok())
    assert sent == []


@pytest.mark.asyncio
async def test_waiting_task_asks_for_approval(client, sent):
    task_id = await tm.create("factory", "Ролик про доставку", source="scheduler")
    await tm.run(task_id, lambda: _awaiting())

    assert len(sent) == 1
    assert "согласовани" in sent[0][1].lower()


@pytest.mark.asyncio
async def test_telegram_started_task_does_not_duplicate(client, sent):
    """Ручной запуск из Telegram отвечает сам — второй отчёт был бы дублем."""
    task_id = await tm.create("factory", "Сделай рилс", source="telegram")
    await tm.run(task_id, lambda: _boom())
    assert sent == []


@pytest.mark.asyncio
async def test_no_token_no_crash(client, monkeypatch):
    """Без настроенного бота задача обязана отработать как обычно."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    task_id = await tm.create("factory", "Без бота", source="scheduler")
    res = await tm.run(task_id, lambda: _ok())
    assert res["ok"] is True


@pytest.mark.asyncio
async def test_recent_errors_collects_tasks_and_models(client):
    task_id = await tm.create("publish", "Публикация", source="scheduler")
    await tm.run(task_id, lambda: _boom())

    from core.cost_tracker import record
    await record(model="deepseek-chat", status="error", error="rate limit", agent="copywriter")

    data = await notify.recent_errors(24)
    assert any(t["id"] == task_id for t in data["tasks"])
    assert any("rate limit" in a["error"] for a in data["agents"])
    assert data["total"] >= 2


@pytest.mark.asyncio
async def test_errors_api(auth_client):
    task_id = await tm.create("publish", "Публикация", source="scheduler")
    await tm.run(task_id, lambda: _boom())

    r = await auth_client.get("/api/tasks/errors")
    assert r.status_code == 200
    assert any(t["id"] == task_id for t in r.json()["tasks"])


@pytest.mark.asyncio
async def test_errors_route_is_not_shadowed_by_task_id(auth_client):
    """`/api/tasks/errors` не должен приниматься за id задачи."""
    r = await auth_client.get("/api/tasks/errors")
    assert "tasks" in r.json() and "agents" in r.json()
