import os
import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from database.db import get_db
from database.models import Connection, AgentLog, ContentPlan, GeneratedContent, Publication
from pydantic import BaseModel
from typing import Dict, Optional

router = APIRouter(tags=["settings"])

class ConnectionsBody(BaseModel):
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    youtube_api_key: Optional[str] = None

@router.get("/api/connections")
async def get_connections(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Connection))
    connections = result.scalars().all()
    return {c.key_name: c.key_value for c in connections}

@router.post("/api/connections")
async def save_connections(body: ConnectionsBody, db: AsyncSession = Depends(get_db)):
    data = body.model_dump(exclude_none=True)
    for key_name, key_value in data.items():
        if not key_value:
            continue
        result = await db.execute(select(Connection).where(Connection.key_name == key_name))
        conn = result.scalar_one_or_none()
        if conn:
            conn.key_value = key_value
        else:
            db.add(Connection(key_name=key_name, key_value=key_value))
        os.environ[key_name.upper()] = key_value
    await db.commit()
    return {"ok": True}

@router.post("/api/connections/test")
async def test_connections(body: ConnectionsBody):
    results = {}
    data = body.model_dump(exclude_none=True)

    if key := data.get("anthropic_api_key"):
        try:
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=key)
            await client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=10, messages=[{"role":"user","content":"hi"}])
            results["anthropic_api_key"] = {"ok": True, "message": "Claude подключён"}
        except Exception as e:
            results["anthropic_api_key"] = {"ok": False, "message": str(e)[:100]}

    if key := data.get("openai_api_key"):
        try:
            import openai
            client = openai.AsyncOpenAI(api_key=key)
            await client.models.list()
            results["openai_api_key"] = {"ok": True, "message": "OpenAI подключён"}
        except Exception as e:
            results["openai_api_key"] = {"ok": False, "message": str(e)[:100]}

    if key := data.get("telegram_bot_token"):
        try:
            async with httpx.AsyncClient() as c:
                r = await c.get(f"https://api.telegram.org/bot{key}/getMe")
                if r.json().get("ok"):
                    results["telegram_bot_token"] = {"ok": True, "message": f"Bot: @{r.json()['result']['username']}"}
                else:
                    results["telegram_bot_token"] = {"ok": False, "message": "Неверный токен"}
        except Exception as e:
            results["telegram_bot_token"] = {"ok": False, "message": str(e)[:100]}

    return results

@router.get("/api/analytics/{niche_id}")
async def get_analytics(niche_id: str, db: AsyncSession = Depends(get_db)):
    total_planned = await db.scalar(select(func.count(ContentPlan.id)).where(ContentPlan.niche_id == niche_id))
    total_generated = await db.scalar(select(func.count(ContentPlan.id)).where(ContentPlan.niche_id == niche_id, ContentPlan.status == 'generated'))
    total_published = await db.scalar(select(func.count(ContentPlan.id)).where(ContentPlan.niche_id == niche_id, ContentPlan.status == 'published'))
    total_tokens = await db.scalar(select(func.sum(AgentLog.tokens_used)).where(AgentLog.niche_id == niche_id)) or 0
    total_cost = await db.scalar(select(func.sum(AgentLog.cost_usd)).where(AgentLog.niche_id == niche_id)) or 0

    logs_result = await db.execute(
        select(AgentLog).where(AgentLog.niche_id == niche_id).order_by(AgentLog.created_at.desc()).limit(20)
    )
    logs = [{"agent_name": l.agent_name, "status": l.status, "model_used": l.model_used, "tokens_used": l.tokens_used, "duration_sec": l.duration_sec} for l in logs_result.scalars()]

    return {
        "total_planned": total_planned,
        "total_generated": total_generated,
        "total_published": total_published,
        "total_tokens": total_tokens,
        "total_cost": total_cost,
        "recent_logs": logs
    }
