"""
Здоровье системы: агенты, площадки, планировщик, задачи, расходы, ошибки.
Защищено auth на уровне main.py (публичный `/api/health` живёт отдельно в main.py).
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/health")
async def system_health():
    """Полное состояние системы одним ответом — для страницы «Здоровье»."""
    from core.health import overview
    return await overview()


@router.get("/summary")
async def system_summary():
    """Только то, что нужно главной странице: система, подключения, текущая
    задача, публикации на сегодня, ошибки.

    Отдельный ответ, а не полный `overview`: главная не должна тянуть на себя
    десяток запросов и показывать всё подряд — по ТЗ на ней пять цифр.
    """
    from datetime import datetime, timedelta

    from sqlalchemy import select, func

    from core.ai_router import available_providers
    from core.notify import recent_errors
    from core.task_manager import list_tasks, RUNNING, CREATED
    from connectors import health_all
    from database.db import AsyncSessionLocal
    from database.models import Publication

    providers = available_providers()
    platforms = await health_all()

    tasks = await list_tasks(limit=50)
    active = [t for t in tasks if t["status"] in (RUNNING, CREATED)]
    current = active[0] if active else None
    if current:
        # «Прогресс» честно считаем по выполненным шагам задачи: другого
        # измерения у нас нет, а рисовать проценты из воздуха — врать.
        steps = current.get("steps") or []
        done = sum(1 for s in steps if s.get("ok"))
        current = {"id": current["id"], "kind": current["kind"], "goal": current["goal"],
                   "status": current["status"], "steps_done": done,
                   "steps_total": len(steps),
                   "percent": int(done * 100 / len(steps)) if steps else None}

    since = datetime.utcnow() - timedelta(days=1)
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(Publication.status, func.count(Publication.id))
            .where(Publication.published_at >= since)
            .group_by(Publication.status))
        today = {s or "—": int(n) for s, n in r.all()}

    errors = await recent_errors(24, 5)
    error_count = len(errors.get("tasks", [])) + len(errors.get("agents", []))

    return {
        "system": {"ok": True, "ai_available": bool(providers), "providers": providers,
                   "mode": "full" if providers else "control_only"},
        "connections": [{"platform": p["platform"], "ok": bool(p.get("ok")),
                         "configured": bool(p.get("configured")),
                         "error": p.get("error")} for p in platforms],
        "current_task": current,
        "publications_today": today,
        "published_today": today.get("published", 0),
        "errors": error_count,
    }


@router.get("/agents")
async def system_agents(hours: int = 24):
    """Агенты: доля успеха, расход, последний запуск, статус online/degraded/silent."""
    from core.health import agents
    return {"agents": await agents(hours)}


@router.get("/scheduler")
async def system_scheduler():
    """Планировщик и его джобы со временем следующего запуска."""
    from core.health import scheduler_jobs
    return scheduler_jobs()
