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
