import os
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database.db import get_db
from database.models import ContentPlan, GeneratedContent, Publication
from core.orchestrator import nexus_core
from publishers.telegram_pub import publish_telegram
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/queue", tags=["queue"])

def plan_to_dict(p: ContentPlan, content: GeneratedContent = None):
    d = {
        "id": p.id, "niche_id": p.niche_id, "day_number": p.day_number,
        "platform": p.platform, "topic": p.topic, "hook": p.hook,
        "format": p.format, "status": p.status,
        "content": None
    }
    if content:
        d["content"] = {
            "text": content.text_reviewed or content.text,
            "image_url": content.image_url,
            "score": content.score
        }
    return d

@router.get("")
async def list_queue(niche_id: Optional[str] = None, status: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    q = select(ContentPlan).order_by(ContentPlan.day_number)
    if niche_id:
        q = q.where(ContentPlan.niche_id == niche_id)
    if status:
        q = q.where(ContentPlan.status == status)
    result = await db.execute(q)
    plans = result.scalars().all()
    items = []
    for p in plans:
        cr = await db.execute(select(GeneratedContent).where(GeneratedContent.plan_id == p.id))
        content = cr.scalar_one_or_none()
        items.append(plan_to_dict(p, content))
    return items

class QueueUpdate(BaseModel):
    text_reviewed: Optional[str] = None

@router.patch("/{plan_id}")
async def update_queue(plan_id: str, body: QueueUpdate, db: AsyncSession = Depends(get_db)):
    cr = await db.execute(select(GeneratedContent).where(GeneratedContent.plan_id == plan_id))
    content = cr.scalar_one_or_none()
    if content and body.text_reviewed:
        content.text_reviewed = body.text_reviewed
        await db.commit()
    return {"ok": True}

@router.delete("/{plan_id}")
async def delete_queue(plan_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ContentPlan).where(ContentPlan.id == plan_id))
    p = result.scalar_one_or_none()
    if p:
        await db.delete(p)
        await db.commit()
    return {"ok": True}

@router.post("/{plan_id}/generate")
async def generate(plan_id: str, bg: BackgroundTasks):
    bg.add_task(nexus_core.generate_content_for_plan, plan_id)
    return {"ok": True}

@router.post("/{plan_id}/publish")
async def publish(plan_id: str, db: AsyncSession = Depends(get_db)):
    pr = await db.execute(select(ContentPlan).where(ContentPlan.id == plan_id))
    plan = pr.scalar_one_or_none()
    if not plan:
        raise HTTPException(404)
    cr = await db.execute(select(GeneratedContent).where(GeneratedContent.plan_id == plan_id))
    content = cr.scalar_one_or_none()
    if not content:
        raise HTTPException(400, "No content generated")

    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id:
        raise HTTPException(400, "TELEGRAM_CHAT_ID not configured")

    text = content.text_reviewed or content.text or ""
    await publish_telegram(chat_id, text, content.image_url)

    plan.status = "published"
    db.add(Publication(plan_id=plan_id, platform=plan.platform))
    await db.commit()
    return {"ok": True}
