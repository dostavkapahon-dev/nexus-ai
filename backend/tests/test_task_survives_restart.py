"""
Задача должна переживать перезапуск сервера.

С живого сервера: человек запустил ролик, на шаге «6/7 Проверка» прошёл деплой,
и пришло «Сервер перезапустился, незавершённые задачи потеряны (2)». Работа
умирала вместе с процессом, и всё приходилось начинать заново.

Саму корутину сохранить нельзя — это замыкание. Поэтому сохраняется РЕЦЕПТ:
имя обработчика и аргументы. При старте задача собирается заново и продолжается.
"""
import asyncio

import pytest

from core import task_manager as tm
from database.db import AsyncSessionLocal
from database.models import Task


@pytest.fixture(autouse=True)
def clean_resumers():
    before = dict(tm._RESUMERS)
    yield
    tm._RESUMERS.clear()
    tm._RESUMERS.update(before)


async def _make_running(task_id_goal: str, recipe: dict | None, attempts: int = 0):
    task_id = await tm.create("factory", task_id_goal, source="test")
    if recipe:
        await tm._save_recipe(task_id, recipe)
    async with AsyncSessionLocal() as db:
        t = await db.get(Task, task_id)
        t.status = tm.RUNNING
        t.attempts = attempts
        await db.commit()
    return task_id


@pytest.mark.asyncio
async def test_task_with_a_recipe_is_continued(client, monkeypatch):
    """Главный случай: деплой посреди работы не должен убивать задачу."""
    done = []

    async def handler(topic=None, dry_run=False):
        done.append(topic)
        return {"ok": True}

    monkeypatch.setattr("core.notify.notify_owner", _quiet)
    tm.register_resumer("factory", handler)
    task_id = await _make_running("Ролик: ИИ ТРЕНДЫ",
                                  {"handler": "factory",
                                   "args": {"topic": "ИИ ТРЕНДЫ", "dry_run": False}})

    await tm.recover_stuck()
    await asyncio.sleep(0.05)          # даём фоновой задаче отработать

    assert done == ["ИИ ТРЕНДЫ"], "работа обязана продолжиться, а не пропасть"
    assert (await tm.get(task_id))["status"] == tm.COMPLETED


@pytest.mark.asyncio
async def test_task_without_a_recipe_is_honestly_closed(client, monkeypatch):
    """Продолжить нечем — честно закрыть, а не делать вид, что идёт."""
    monkeypatch.setattr("core.notify.notify_owner", _quiet)
    task_id = await _make_running("Задача без рецепта", None)

    await tm.recover_stuck()

    task = await tm.get(task_id)
    assert task["status"] == tm.FAILED
    assert "перезапуск" in task["error"].lower()


@pytest.mark.asyncio
async def test_repeatedly_failing_task_is_not_looped_forever(client, monkeypatch):
    """Задача, падающая вместе с сервером, не должна крутить цикл рестартов."""
    tries = []

    async def handler(topic=None):
        tries.append(topic)
        return {"ok": True}

    monkeypatch.setattr("core.notify.notify_owner", _quiet)
    tm.register_resumer("factory", handler)
    task_id = await _make_running("Падучая", {"handler": "factory",
                                              "args": {"topic": "x"}}, attempts=2)

    await tm.recover_stuck()
    await asyncio.sleep(0.05)

    assert tries == [], "третья попытка — это уже бесконечный цикл"
    assert (await tm.get(task_id))["status"] == tm.FAILED


@pytest.mark.asyncio
async def test_unknown_handler_does_not_break_startup(client, monkeypatch):
    """Рецепт от удалённого обработчика не должен ронять запуск сервера."""
    monkeypatch.setattr("core.notify.notify_owner", _quiet)
    task_id = await _make_running("Старый рецепт",
                                  {"handler": "которого_больше_нет", "args": {}})

    await tm.recover_stuck()

    assert (await tm.get(task_id))["status"] == tm.FAILED


@pytest.mark.asyncio
async def test_recipe_is_forgotten_when_the_task_ends(client):
    """Иначе рецепты копятся вечно и задача «воскресает» после завершения."""
    async def work():
        return {"ok": True}

    task_id = await tm.spawn("factory", "разовая", work, source="test",
                             recipe={"handler": "factory", "args": {}})
    await asyncio.sleep(0.05)

    assert await tm._recipe(task_id) is None


@pytest.mark.asyncio
async def test_spawn_without_recipe_saves_nothing(client):
    async def work():
        return {"ok": True}

    task_id = await tm.spawn("factory", "без рецепта", work, source="test")

    assert await tm._recipe(task_id) is None


async def _quiet(text, **kw):
    return None
