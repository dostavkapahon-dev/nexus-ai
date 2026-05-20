import uuid
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database.db import get_db
from database.models import Niche, ContentPlan
from core.orchestrator import nexus_core
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter(prefix="/api/niches", tags=["niches"])

class NicheCreate(BaseModel):
    name: str
    city: str = ''
    goal: str = 'subscribers'
    budget_usd: float = 0
    posts_per_day: int = 1
    platforms: List[str] = ['telegram']
    tone_of_voice: str = 'neutral'
    about_user: str = ''

class NicheUpdate(BaseModel):
    status: Optional[str] = None
    posts_per_day: Optional[int] = None
    budget_usd: Optional[float] = None

def niche_to_dict(n: Niche):
    return {
        "id": n.id, "name": n.name, "city": n.city, "goal": n.goal,
        "budget_usd": n.budget_usd, "posts_per_day": n.posts_per_day,
        "platforms": n.platforms or [], "tone_of_voice": n.tone_of_voice,
        "about_user": n.about_user, "status": n.status,
        "created_at": n.created_at.isoformat() if n.created_at else None
    }

@router.post("")
async def create_niche(body: NicheCreate, bg: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    niche = Niche(id=str(uuid.uuid4()), **body.model_dump())
    db.add(niche)
    await db.commit()
    bg.add_task(nexus_core.run_full_pipeline, niche.id)
    return niche_to_dict(niche)

@router.get("")
async def list_niches(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Niche).order_by(Niche.created_at.desc()))
    return [niche_to_dict(n) for n in result.scalars()]

@router.get("/{niche_id}")
async def get_niche(niche_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Niche).where(Niche.id == niche_id))
    n = result.scalar_one_or_none()
    if not n:
        raise HTTPException(404)
    return niche_to_dict(n)

@router.patch("/{niche_id}")
async def update_niche(niche_id: str, body: NicheUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Niche).where(Niche.id == niche_id))
    n = result.scalar_one_or_none()
    if not n:
        raise HTTPException(404)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(n, k, v)
    await db.commit()
    return niche_to_dict(n)

@router.delete("/{niche_id}")
async def delete_niche(niche_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Niche).where(Niche.id == niche_id))
    n = result.scalar_one_or_none()
    if n:
        await db.delete(n)
        await db.commit()
    return {"ok": True}

@router.post("/{niche_id}/plan")
async def generate_plan(niche_id: str, bg: BackgroundTasks):
    bg.add_task(nexus_core.run_full_pipeline, niche_id)
    return {"ok": True}

@router.get("/{niche_id}/plan")
async def get_plan(niche_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ContentPlan).where(ContentPlan.niche_id == niche_id).order_by(ContentPlan.day_number))
    return [{"id": p.id, "day_number": p.day_number, "platform": p.platform, "topic": p.topic, "hook": p.hook, "format": p.format, "status": p.status} for p in result.scalars()]
