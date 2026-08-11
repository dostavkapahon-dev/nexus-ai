"""
Стратегии: версии, активация, сравнение по фактическому результату.
Защищено auth на уровне main.py.
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter(prefix="/api/strategy", tags=["strategy"])


@router.get("")
async def strategy_list(niche_id: str = "", status: str = "", limit: int = 30):
    from core.strategy_store import history
    return {"strategies": await history(niche_id, status, limit)}


@router.get("/current")
async def strategy_current(niche_id: str = ""):
    from core.strategy_store import current
    return await current(niche_id) or {"error": "активной стратегии нет"}


@router.get("/effectiveness")
async def strategy_effectiveness(niche_id: str = ""):
    """Сравнение стратегий по реальному отклику публикаций."""
    from core.strategy_store import effectiveness, best
    return {"strategies": await effectiveness(niche_id), "best": await best(niche_id)}


@router.post("/{strategy_id}/activate")
async def strategy_activate(strategy_id: str):
    """Сделать стратегию действующей. Прошлая уходит в архив."""
    from core.strategy_store import activate
    res = await activate(strategy_id)
    return res or {"error": "стратегия не найдена"}


class ManualStrategy(BaseModel):
    title: str
    angle: Optional[str] = ""
    plan: Optional[str] = ""
    pillars: Optional[List[str]] = None
    niche_id: Optional[str] = ""


@router.post("/manual")
async def strategy_manual(body: ManualStrategy):
    """Своя стратегия руками — равноправна с предложенными агентом."""
    from core.strategy_store import add_manual
    sid = await add_manual(body.title, body.angle or "", body.plan or "",
                           body.pillars, body.niche_id or "")
    return {"ok": True, "id": sid}
