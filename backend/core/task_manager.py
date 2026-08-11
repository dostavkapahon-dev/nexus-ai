"""
Менеджер задач — единый учёт всей фоновой работы.

Раньше фоновые запуски шли через `BackgroundTasks` и `asyncio.create_task` без
идентификаторов: упавшая работа исчезала бесследно, а статус в очереди зависал.
Теперь каждая работа получает Task: id, статус, журнал шагов, расход и текст ошибки.

Статусы: CREATED → RUNNING → COMPLETED | FAILED | CANCELLED (WAITING — ожидание ввода).

Использование:
    task = await create("factory", "Сделать рилс про доставку", source="telegram")
    await run(task.id, lambda: run_factory(topic="доставка"))
"""
import asyncio
import traceback
from datetime import datetime, timedelta

from sqlalchemy import select, func

from database.db import AsyncSessionLocal
from database.models import Task

CREATED, RUNNING, WAITING = "CREATED", "RUNNING", "WAITING"
COMPLETED, FAILED, CANCELLED = "COMPLETED", "FAILED", "CANCELLED"

# Задача, висящая в RUNNING дольше этого срока, считается потерянной при рестарте.
STUCK_AFTER_MIN = 30


async def new_id() -> str:
    """Человекочитаемый id вида TASK-2026-000001 (сквозная нумерация в пределах года)."""
    year = datetime.utcnow().year
    prefix = f"TASK-{year}-"
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(func.count(Task.id)).where(Task.id.like(f"{prefix}%")))
        n = (r.scalar() or 0) + 1
    return f"{prefix}{n:06d}"


async def create(kind: str, goal: str = "", source: str = "api", ref_id: str = "") -> str:
    """Регистрирует задачу в статусе CREATED. Возвращает task_id."""
    task_id = await new_id()
    async with AsyncSessionLocal() as db:
        db.add(Task(id=task_id, kind=kind, goal=(goal or "")[:2000], source=source,
                    ref_id=ref_id or "", status=CREATED, steps=[], agents=[], models=[]))
        await db.commit()
    return task_id


async def _patch(task_id: str, **fields):
    """Точечное обновление задачи (не роняет вызывающего при проблемах с БД)."""
    try:
        async with AsyncSessionLocal() as db:
            r = await db.execute(select(Task).where(Task.id == task_id))
            t = r.scalar_one_or_none()
            if not t:
                return
            for k, v in fields.items():
                setattr(t, k, v)
            await db.commit()
    except Exception:
        pass


async def add_step(task_id: str, action: str, ok: bool = True,
                   agent: str = "", error: str = ""):
    """Добавляет запись в журнал шагов задачи."""
    if not task_id:
        return
    try:
        async with AsyncSessionLocal() as db:
            r = await db.execute(select(Task).where(Task.id == task_id))
            t = r.scalar_one_or_none()
            if not t:
                return
            steps = list(t.steps or [])
            steps.append({"ts": datetime.utcnow().isoformat(), "agent": agent,
                          "action": action, "ok": ok, "error": (error or "")[:300]})
            t.steps = steps[-100:]          # журнал не должен расти бесконечно
            if agent:
                agents = list(t.agents or [])
                if agent not in agents:
                    agents.append(agent)
                    t.agents = agents
            await db.commit()
    except Exception:
        pass


async def add_cost(task_id: str, model: str = "", tokens: int = 0, cost: float = 0.0):
    """Накопление расхода по задаче (основа для BLOCK 02 — Cost Control)."""
    if not task_id:
        return
    try:
        async with AsyncSessionLocal() as db:
            r = await db.execute(select(Task).where(Task.id == task_id))
            t = r.scalar_one_or_none()
            if not t:
                return
            t.tokens = (t.tokens or 0) + int(tokens or 0)
            t.cost_usd = round((t.cost_usd or 0.0) + float(cost or 0.0), 6)
            if model:
                models = list(t.models or [])
                if model not in models:
                    models.append(model)
                    t.models = models
            await db.commit()
    except Exception:
        pass


async def run(task_id: str, coro_factory, max_attempts: int = 1) -> dict:
    """Выполняет работу под учётом задачи.

    coro_factory — функция без аргументов, возвращающая корутину (нужна именно фабрика,
    чтобы можно было повторить попытку). Возвращает {ok, task_id, result|error}.
    """
    started = datetime.utcnow()
    await _patch(task_id, status=RUNNING, started_at=started)

    last_error = ""
    for attempt in range(1, max(1, max_attempts) + 1):
        await _patch(task_id, attempts=attempt)
        try:
            result = await coro_factory()
            finished = datetime.utcnow()
            await _patch(task_id, status=COMPLETED, finished_at=finished,
                         duration_sec=round((finished - started).total_seconds(), 2),
                         result=_safe_result(result), error=None)
            return {"ok": True, "task_id": task_id, "result": result}
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            await add_step(task_id, f"попытка {attempt} провалилась", ok=False, error=last_error)
            traceback.print_exc()
            if attempt < max_attempts:
                await asyncio.sleep(2 ** attempt)

    finished = datetime.utcnow()
    await _patch(task_id, status=FAILED, finished_at=finished,
                 duration_sec=round((finished - started).total_seconds(), 2),
                 error=last_error[:2000])
    return {"ok": False, "task_id": task_id, "error": last_error}


def _safe_result(result) -> dict | None:
    """Готовит итог к записи в JSON-колонку, не раздувая её."""
    if result is None:
        return None
    if isinstance(result, dict):
        out = {}
        for k, v in list(result.items())[:20]:
            if isinstance(v, (str, int, float, bool)) or v is None:
                out[k] = v[:500] if isinstance(v, str) else v
            else:
                out[k] = f"<{type(v).__name__}>"
        return out
    return {"value": str(result)[:500]}


async def spawn(kind: str, goal: str, coro_factory, source: str = "api",
                ref_id: str = "", max_attempts: int = 1) -> str:
    """Создаёт задачу и запускает её в фоне. Возвращает task_id сразу.

    Замена «голому» asyncio.create_task: работа остаётся видимой и после падения.
    """
    task_id = await create(kind, goal, source, ref_id)
    asyncio.create_task(run(task_id, coro_factory, max_attempts))
    return task_id


async def recover_stuck() -> int:
    """При старте помечает задачи, зависшие в RUNNING, как потерянные при рестарте."""
    cutoff = datetime.utcnow() - timedelta(minutes=STUCK_AFTER_MIN)
    n = 0
    try:
        async with AsyncSessionLocal() as db:
            r = await db.execute(select(Task).where(Task.status == RUNNING))
            for t in r.scalars():
                if (t.started_at or t.created_at or cutoff) <= cutoff:
                    t.status = FAILED
                    t.error = "Задача потеряна при перезапуске сервера."
                    t.finished_at = datetime.utcnow()
                    n += 1
            await db.commit()
    except Exception:
        pass
    return n


async def get(task_id: str) -> dict | None:
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Task).where(Task.id == task_id))
        t = r.scalar_one_or_none()
    return _as_dict(t) if t else None


async def list_tasks(status: str = "", kind: str = "", limit: int = 50) -> list[dict]:
    async with AsyncSessionLocal() as db:
        q = select(Task).order_by(Task.created_at.desc()).limit(min(limit, 200))
        if status:
            q = q.where(Task.status == status.upper())
        if kind:
            q = q.where(Task.kind == kind)
        r = await db.execute(q)
        return [_as_dict(t) for t in r.scalars()]


async def cancel(task_id: str) -> bool:
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Task).where(Task.id == task_id))
        t = r.scalar_one_or_none()
        if not t or t.status in (COMPLETED, FAILED, CANCELLED):
            return False
        t.status = CANCELLED
        t.finished_at = datetime.utcnow()
        await db.commit()
    return True


def _as_dict(t: Task) -> dict:
    return {
        "id": t.id, "kind": t.kind, "goal": t.goal, "status": t.status,
        "source": t.source, "ref_id": t.ref_id, "steps": t.steps or [],
        "agents": t.agents or [], "models": t.models or [],
        "tokens": t.tokens or 0, "cost_usd": t.cost_usd or 0.0,
        "attempts": t.attempts or 0, "error": t.error, "result": t.result,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "started_at": t.started_at.isoformat() if t.started_at else None,
        "finished_at": t.finished_at.isoformat() if t.finished_at else None,
        "duration_sec": t.duration_sec or 0.0,
    }


STATUS_EMOJI = {CREATED: "🕓", RUNNING: "⚙️", WAITING: "⏸",
                COMPLETED: "✅", FAILED: "❌", CANCELLED: "🚫"}
