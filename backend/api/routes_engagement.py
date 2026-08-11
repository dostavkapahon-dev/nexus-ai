"""
Комментарии и воронка: разбор, подготовка ответов, согласование.
Защищено auth на уровне main.py.
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/engagement", tags=["engagement"])


@router.get("")
async def engagement_stats():
    from core.engagement import stats
    return await stats()


@router.get("/comments")
async def engagement_comments(platform: str = "instagram", limit: int = 20):
    """Новые комментарии, которые ещё не обрабатывались."""
    from core.engagement import fetch_new_comments
    return {"comments": await fetch_new_comments(platform, limit)}


class ProcessBody(BaseModel):
    platform: Optional[str] = "instagram"
    limit: Optional[int] = 10
    auto_send: Optional[bool] = False


@router.post("/process")
async def engagement_process(body: ProcessBody):
    """Разобрать комментарии и подготовить ответы (по умолчанию — на согласование)."""
    from core.engagement import process_comments
    return await process_comments(body.platform or "instagram",
                                  body.limit or 10, bool(body.auto_send))


@router.get("/pending")
async def engagement_pending():
    """Ответы, ждущие подтверждения человека."""
    from core.engagement import pending
    return {"pending": await pending()}


@router.post("/approve")
async def engagement_approve():
    from core.engagement import approve_all
    return await approve_all()


@router.post("/discard")
async def engagement_discard():
    from core.engagement import discard_pending
    return {"discarded": await discard_pending()}
