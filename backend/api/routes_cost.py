"""
Расходы на AI: сколько потрачено, на что и не пора ли тормозить.
Защищено auth на уровне main.py.
"""
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/cost", tags=["cost"])


@router.get("")
async def cost_overview(hours: int = 24):
    """Сводка: расход за период, бюджет, разбивка по моделям и агентам."""
    from core.cost_tracker import budget_status, spend, by_model, by_agent
    return {
        "budget": await budget_status(),
        "period": await spend(hours),
        "by_model": await by_model(hours),
        "by_agent": await by_agent(hours),
    }


class BudgetBody(BaseModel):
    budget_usd_day: float


@router.post("/budget")
async def set_budget(body: BudgetBody):
    """Дневной лимит расходов. 0 — брать из AI_BUDGET_USD_DAY."""
    from sqlalchemy import select
    from database.db import AsyncSessionLocal
    from database.models import UserProfile

    value = max(0.0, float(body.budget_usd_day or 0))
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(UserProfile).limit(1))
        prof = r.scalar_one_or_none()
        if not prof:
            prof = UserProfile()
            db.add(prof)
        prof.budget_usd_day = value
        await db.commit()
    return {"ok": True, "budget_usd_day": value}
