"""Задача, роняющая сервис, не должна поднимать его снова и снова.

Симптом с сервера: «♻️ Сервер перезапустился. Продолжаю задачи (1): Изображение»
каждые четыре минуты. Защита «продолжаем не больше двух раз» существовала, но
не срабатывала: счётчик попыток переписывался единицей при каждом запуске.
"""
import pytest

from core import task_manager as tm


@pytest.mark.asyncio
async def test_attempts_grow_across_restarts():
    from database.db import init_db
    await init_db()
    task_id = await tm.create("factory", "кадр про ии", source="telegram")

    async def works():
        return {"ok": True}

    await tm.run(task_id, works)
    first = (await tm.get(task_id))["attempts"]
    await tm.run(task_id, works)
    second = (await tm.get(task_id))["attempts"]

    assert second > first, "счётчик попыток обнуляется — защита не сработает"


@pytest.mark.asyncio
async def test_task_that_kept_dying_is_not_resumed_again(monkeypatch):
    """Третий перезапуск подряд — это не «продолжаю», а «стоп»."""
    from database.db import init_db, AsyncSessionLocal
    from database.models import Task
    await init_db()
    task_id = await tm.create("factory", "кадр про ии", source="telegram")
    await tm._save_recipe(task_id, {"handler": "factory", "args": {}})
    async with AsyncSessionLocal() as db:
        t = await db.get(Task, task_id)
        t.status = tm.RUNNING
        t.attempts = 2               # два перезапуска уже пережила
        await db.commit()

    resumed = []
    monkeypatch.setattr(tm, "resumer_for", lambda h: (lambda **kw: resumed.append(h)))

    async def silent(text):
        return True
    monkeypatch.setattr("core.notify.notify_owner", silent)

    await tm.recover_stuck()

    assert not resumed, "задача, дважды уронившая сервер, не запускается снова"
    row = await tm.get(task_id)
    assert row["status"] == tm.FAILED
    assert "роняет" in (row["error"] or "")
