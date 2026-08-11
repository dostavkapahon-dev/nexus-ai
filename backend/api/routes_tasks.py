"""
Задачи: список, детали, отмена, повтор. Единая точка наблюдения за фоновой работой.
Защищено auth на уровне main.py.
"""
from fastapi import APIRouter
from typing import Optional

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("")
async def list_tasks_endpoint(status: Optional[str] = None, kind: Optional[str] = None,
                              limit: int = 50):
    """Последние задачи. Фильтры: status (CREATED/RUNNING/COMPLETED/FAILED/CANCELLED), kind."""
    from core.task_manager import list_tasks
    return {"tasks": await list_tasks(status or "", kind or "", limit)}


@router.get("/stats")
async def tasks_stats():
    """Сводка по статусам + суммарный расход — для дашборда."""
    from core.task_manager import list_tasks
    tasks = await list_tasks(limit=200)
    by_status: dict = {}
    for t in tasks:
        by_status[t["status"]] = by_status.get(t["status"], 0) + 1
    return {
        "total": len(tasks),
        "by_status": by_status,
        "cost_usd": round(sum(t.get("cost_usd") or 0 for t in tasks), 4),
        "tokens": sum(t.get("tokens") or 0 for t in tasks),
        "failed_recent": [t["id"] for t in tasks if t["status"] == "FAILED"][:10],
    }


@router.get("/errors")
async def tasks_errors(hours: int = 24, limit: int = 10):
    """Что сломалось за период: провалившиеся задачи и ошибки вызовов моделей.

    Объявлено выше `/{task_id}`: иначе FastAPI примет «errors» за id задачи.
    """
    from core.notify import recent_errors
    return await recent_errors(hours, limit)


@router.get("/{task_id}")
async def get_task_endpoint(task_id: str):
    from core.task_manager import get
    task = await get(task_id)
    return task or {"error": "задача не найдена"}


@router.post("/{task_id}/cancel")
async def cancel_task_endpoint(task_id: str):
    from core.task_manager import cancel
    ok = await cancel(task_id)
    return {"ok": ok, "error": None if ok else "задача уже завершена или не найдена"}
