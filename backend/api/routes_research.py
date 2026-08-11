"""
Исследования рынка и конкуренты: история, отслеживание, динамика.
Защищено auth на уровне main.py.
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/research", tags=["research"])


@router.get("")
async def research_history(kind: str = "", niche_id: str = "", limit: int = 20):
    """История исследований: тренды, разборы роликов, анализ конкурентов."""
    from core.research_store import history
    return {"items": await history(kind, niche_id, limit)}


@router.get("/stats")
async def research_stats():
    from core.research_store import stats
    return await stats()


@router.get("/latest")
async def research_latest(kind: str = "", niche_id: str = ""):
    from core.research_store import latest
    return await latest(kind, niche_id) or {"error": "исследований пока нет"}


@router.get("/context")
async def research_context(niche_id: str = ""):
    """Сводка рынка, которую агенты подмешивают в промпты."""
    from core.research_store import market_context
    return {"context": await market_context(niche_id)}


class CompetitorBody(BaseModel):
    platform: str
    handle: str
    niche_id: Optional[str] = ""


@router.get("/competitors")
async def competitors_list(niche_id: str = ""):
    """Отслеживаемые конкуренты: последний срез и динамика подписчиков."""
    from core.research_store import tracked_competitors
    return {"competitors": await tracked_competitors(niche_id)}


@router.post("/competitors")
async def competitors_track(body: CompetitorBody):
    """Добавить конкурента и сразу снять первый срез метрик."""
    from core.research_store import track_competitor
    return await track_competitor(body.platform, body.handle, body.niche_id or "")


@router.post("/competitors/refresh")
async def competitors_refresh(niche_id: str = ""):
    """Обновить срезы всех конкурентов (обычно это делает джоб раз в неделю)."""
    from core.research_store import refresh_all
    return await refresh_all(niche_id)


@router.get("/competitors/{platform}/{handle}")
async def competitor_dynamics(platform: str, handle: str, limit: int = 30):
    from core.research_store import competitor_history
    return {"history": await competitor_history(platform, handle, limit)}


@router.delete("/competitors/{platform}/{handle}")
async def competitor_stop(platform: str, handle: str):
    from core.research_store import stop_tracking
    return {"stopped": await stop_tracking(platform, handle)}
