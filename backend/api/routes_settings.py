import os
import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from database.db import get_db
from database.models import Connection, AgentLog, ContentPlan, GeneratedContent, Publication
from pydantic import BaseModel
from typing import Optional

router = APIRouter(tags=["settings"])

def mask(value):
    if not value or len(value) < 8:
        return ""
    return value[:4] + "****" + value[-4:]

class ConnectionsBody(BaseModel):
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    perplexity_api_key: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    instagram_access_token: Optional[str] = None
    instagram_account_id: Optional[str] = None
    tiktok_access_token: Optional[str] = None
    google_service_account_json: Optional[str] = None
    youtube_api_key: Optional[str] = None
    deepseek_api_key: Optional[str] = None
    vk_access_token: Optional[str] = None
    vk_group_id: Optional[str] = None
    threads_access_token: Optional[str] = None
    threads_user_id: Optional[str] = None
    heygen_api_key: Optional[str] = None
    heygen_avatar_id: Optional[str] = None
    heygen_voice_id: Optional[str] = None
    higgsfield_api_key: Optional[str] = None
    higgsfield_secret: Optional[str] = None
    runway_api_key: Optional[str] = None
    elevenlabs_api_key: Optional[str] = None
    nexus_token: Optional[str] = None

@router.get("/api/connections")
async def get_connections(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Connection))
    connections = result.scalars().all()
    return {c.key_name: mask(c.key_value) for c in connections}

@router.post("/api/connections")
async def save_connections(body: ConnectionsBody, db: AsyncSession = Depends(get_db)):
    data = body.model_dump(exclude_none=True)
    for key_name, key_value in data.items():
        if not key_value or "****" in key_value:
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
async def test_connections(body: ConnectionsBody, db: AsyncSession = Depends(get_db)):
    results = {}
    data = body.model_dump(exclude_none=True)
    db_result = await db.execute(select(Connection))
    db_map = {c.key_name: c.key_value for c in db_result.scalars()}

    def resolve(key):
        val = data.get(key, "")
        if val and "****" not in val:
            return val
        return db_map.get(key)

    if key := resolve("anthropic_api_key"):
        try:
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=key)
            await client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=10, messages=[{"role":"user","content":"hi"}])
            results["anthropic_api_key"] = {"ok": True, "message": "Claude подключён ✓"}
        except Exception as e:
            results["anthropic_api_key"] = {"ok": False, "message": str(e)[:120]}

    if key := resolve("openai_api_key"):
        try:
            import openai
            client = openai.AsyncOpenAI(api_key=key)
            await client.models.list()
            results["openai_api_key"] = {"ok": True, "message": "OpenAI подключён ✓"}
        except Exception as e:
            results["openai_api_key"] = {"ok": False, "message": str(e)[:120]}

    if key := resolve("gemini_api_key"):
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={key}")
                if r.status_code == 200:
                    results["gemini_api_key"] = {"ok": True, "message": "Gemini подключён ✓"}
                else:
                    results["gemini_api_key"] = {"ok": False, "message": r.json().get("error",{}).get("message","Ошибка")}
        except Exception as e:
            results["gemini_api_key"] = {"ok": False, "message": str(e)[:120]}

    if key := resolve("telegram_bot_token"):
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f"https://api.telegram.org/bot{key}/getMe")
                d = r.json()
                if d.get("ok"):
                    results["telegram_bot_token"] = {"ok": True, "message": f"@{d['result']['username']} ✓"}
                else:
                    results["telegram_bot_token"] = {"ok": False, "message": d.get("description","Неверный токен")}
        except Exception as e:
            results["telegram_bot_token"] = {"ok": False, "message": str(e)[:120]}

    if key := resolve("instagram_access_token"):
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get("https://graph.facebook.com/v19.0/me", params={"access_token": key, "fields": "id,name"})
                d = r.json()
                if "error" in d:
                    results["instagram_access_token"] = {"ok": False, "message": d["error"]["message"][:120]}
                else:
                    results["instagram_access_token"] = {"ok": True, "message": f"Аккаунт: {d.get('name', d.get('id'))} ✓"}
        except Exception as e:
            results["instagram_access_token"] = {"ok": False, "message": str(e)[:120]}

    return results

@router.get("/api/analytics/{niche_id}")
async def get_analytics(niche_id: str, db: AsyncSession = Depends(get_db)):
    total_planned = await db.scalar(select(func.count(ContentPlan.id)).where(ContentPlan.niche_id == niche_id))
    total_generated = await db.scalar(select(func.count(ContentPlan.id)).where(ContentPlan.niche_id == niche_id, ContentPlan.status == 'generated'))
    total_published = await db.scalar(select(func.count(ContentPlan.id)).where(ContentPlan.niche_id == niche_id, ContentPlan.status == 'published'))
    total_tokens = await db.scalar(select(func.sum(AgentLog.tokens_used)).where(AgentLog.niche_id == niche_id)) or 0
    total_cost = await db.scalar(select(func.sum(AgentLog.cost_usd)).where(AgentLog.niche_id == niche_id)) or 0
    logs_result = await db.execute(select(AgentLog).where(AgentLog.niche_id == niche_id).order_by(AgentLog.created_at.desc()).limit(20))
    logs = [{"agent_name": l.agent_name, "status": l.status, "model_used": l.model_used, "tokens_used": l.tokens_used, "duration_sec": l.duration_sec} for l in logs_result.scalars()]
    return {"total_planned": total_planned, "total_generated": total_generated, "total_published": total_published, "total_tokens": total_tokens, "total_cost": round(total_cost, 4), "recent_logs": logs}
