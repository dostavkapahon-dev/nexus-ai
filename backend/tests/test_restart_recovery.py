"""
Что происходит с работой, начатой до перезапуска сервера.

Сервер запускается одним воркером, а работа живёт в asyncio-задаче внутри
процесса. Значит после рестарта её никто не продолжит. Здесь проверяется, что
это не выглядит как «задача всё ещё идёт»: незавершённое честно закрывается и о
нём сообщают, а производственное ТЗ, взятое пропавшим исполнителем, возвращается
в очередь, а не пропадает из неё навсегда.
"""
from datetime import datetime, timedelta

import pytest

from core import task_manager as tm
from core import production_queue as pq
from database.db import AsyncSessionLocal
from database.models import Task


async def _make(status: str, started_ago_min: int = 0) -> str:
    task_id = await tm.create("factory", f"тест {status}", source="test")
    async with AsyncSessionLocal() as db:
        t = await db.get(Task, task_id)
        t.status = status
        if started_ago_min:
            t.started_at = datetime.utcnow() - timedelta(minutes=started_ago_min)
        await db.commit()
    return task_id


@pytest.mark.asyncio
async def test_fresh_running_task_is_not_left_hanging(client, monkeypatch):
    """Задача, запущенная за минуту до рестарта, тоже потеряна — процесса нет."""
    monkeypatch.setattr("core.notify.notify_owner", _quiet)
    task_id = await _make(tm.RUNNING, started_ago_min=1)

    await tm.recover_stuck()

    task = await tm.get(task_id)
    assert task["status"] == tm.FAILED, "свежая RUNNING висела бы полчаса и врала"
    assert "перезапуск" in task["error"].lower()


@pytest.mark.asyncio
async def test_created_task_is_recovered_too(client, monkeypatch):
    """CREATED не разбирал никто: зарегистрирована — и висит вечно."""
    monkeypatch.setattr("core.notify.notify_owner", _quiet)
    task_id = await _make(tm.CREATED)

    await tm.recover_stuck()

    assert (await tm.get(task_id))["status"] == tm.FAILED


@pytest.mark.asyncio
async def test_finished_tasks_are_untouched(client, monkeypatch):
    """Завершённое переписывать нельзя — иначе история задач станет ложью."""
    monkeypatch.setattr("core.notify.notify_owner", _quiet)
    done = await _make(tm.COMPLETED)
    waiting = await _make(tm.WAITING)

    await tm.recover_stuck()

    assert (await tm.get(done))["status"] == tm.COMPLETED
    assert (await tm.get(waiting))["status"] == tm.WAITING, \
        "задача ждёт согласования человека, а не выполнения сервером"


@pytest.mark.asyncio
async def test_owner_is_told_once_about_all_losses(client, monkeypatch):
    """Десять потерянных задач — одно сообщение, а не десять."""
    sent = []

    async def fake_notify(text, **kw):
        sent.append(text)

    monkeypatch.setattr("core.notify.notify_owner", fake_notify)
    for _ in range(3):
        await _make(tm.RUNNING, started_ago_min=1)

    n = await tm.recover_stuck()

    assert n >= 3
    assert len(sent) == 1, "по сообщению на задачу — это спам после каждого деплоя"


@pytest.mark.asyncio
async def test_abandoned_production_job_returns_to_queue(client):
    """Исполнитель взял ТЗ и пропал — задание должно вернуться в очередь."""
    await pq.enqueue({"topic": "шашлык"}, kind="reel")
    job = await pq.claim()
    assert job and job["status"] == pq.TAKEN

    assert await pq.reclaim_stale() == [], "свежее задание отбирать рано"

    async with AsyncSessionLocal() as db:
        from database.models import ProductionJob
        row = await db.get(ProductionJob, job["id"])
        row.taken_at = datetime.utcnow() - timedelta(hours=3)
        await db.commit()

    back = await pq.reclaim_stale()

    assert [j["id"] for j in back] == [job["id"]]
    assert (await pq.get(job["id"]))["status"] == pq.QUEUED
    assert (await pq.claim())["id"] == job["id"], "задание снова выдаётся исполнителю"


@pytest.mark.asyncio
async def test_done_job_is_never_reclaimed(client):
    """Готовое медиа переделывать не нужно — это лишняя генерация."""
    await pq.enqueue({"topic": "кофе"}, kind="reel")
    job = await pq.claim()
    await pq.submit(job["id"], {"video_url": "https://x/v.mp4"})

    assert await pq.reclaim_stale(minutes=1) == []
    assert (await pq.get(job["id"]))["status"] == pq.DONE


async def _quiet(text, **kw):
    return None
