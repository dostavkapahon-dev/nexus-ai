import os
import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database.db import get_db
from database.models import UserProfile, Connection
from pydantic import BaseModel
from typing import Optional
from core.ai_router import estimate_cost

router = APIRouter(tags=["profile"])

class ProfileBody(BaseModel):
    product_description: Optional[str] = None
    brand_style: Optional[str] = None
    strategy_focus: Optional[str] = None
    strategy_duration: Optional[int] = None
    ai_mode: Optional[str] = None
    google_drive_folder_id: Optional[str] = None

@router.get("/api/profile")
async def get_profile(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserProfile).limit(1))
    p = result.scalar_one_or_none()
    if not p:
        return {"product_description": "", "brand_style": "", "strategy_focus": "subscribers",
                "strategy_duration": 30, "ai_mode": "economy", "google_drive_folder_id": ""}
    return {
        "product_description": p.product_description,
        "brand_style": p.brand_style,
        "strategy_focus": p.strategy_focus,
        "strategy_duration": p.strategy_duration,
        "ai_mode": p.ai_mode,
        "google_drive_folder_id": p.google_drive_folder_id,
    }

@router.post("/api/profile")
async def save_profile(body: ProfileBody, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserProfile).limit(1))
    p = result.scalar_one_or_none()
    data = body.model_dump(exclude_none=True)
    if p:
        for k, v in data.items():
            setattr(p, k, v)
    else:
        p = UserProfile(**data)
        db.add(p)
    await db.commit()
    return {"ok": True}

@router.get("/api/profile/cost-estimate")
async def cost_estimate(ai_mode: str = "economy", posts_per_day: int = 1, days: int = 30):
    cost = estimate_cost(ai_mode, posts_per_day, days)
    return {"estimated_cost_usd": cost, "ai_mode": ai_mode, "posts": posts_per_day * days}

@router.post("/api/infrastructure/check")
async def check_infrastructure(db: AsyncSession = Depends(get_db)):
    results = {}

    # Load keys from DB
    conn_result = await db.execute(select(Connection))
    db_keys = {c.key_name: c.key_value for c in conn_result.scalars()}
    def key(name): return os.getenv(name.upper()) or db_keys.get(name, "")

    # 1. Anthropic
    if k := key("anthropic_api_key"):
        try:
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=k)
            await client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=5,
                                          messages=[{"role": "user", "content": "hi"}])
            results["anthropic"] = {"ok": True, "message": "Claude ✓"}
        except Exception as e:
            results["anthropic"] = {"ok": False, "message": str(e)[:80]}
    else:
        results["anthropic"] = {"ok": False, "message": "Ключ не задан"}

    # 2. OpenAI
    if k := key("openai_api_key"):
        try:
            import openai
            client = openai.AsyncOpenAI(api_key=k)
            await client.models.list()
            results["openai"] = {"ok": True, "message": "OpenAI ✓"}
        except Exception as e:
            results["openai"] = {"ok": False, "message": str(e)[:80]}
    else:
        results["openai"] = {"ok": False, "message": "Ключ не задан"}

    # 3. Perplexity
    if k := key("perplexity_api_key"):
        try:
            import openai
            client = openai.AsyncOpenAI(api_key=k, base_url="https://api.perplexity.ai")
            await client.chat.completions.create(
                model="sonar", max_tokens=5,
                messages=[{"role": "user", "content": "hi"}]
            )
            results["perplexity"] = {"ok": True, "message": "Perplexity ✓"}
        except Exception as e:
            results["perplexity"] = {"ok": False, "message": str(e)[:80]}
    else:
        results["perplexity"] = {"ok": False, "message": "Ключ не задан"}

    # 4. Gemini
    if k := key("gemini_api_key"):
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={k}")
                results["gemini"] = {"ok": r.status_code == 200, "message": "Gemini ✓" if r.status_code == 200 else "Ошибка"}
        except Exception as e:
            results["gemini"] = {"ok": False, "message": str(e)[:80]}
    else:
        results["gemini"] = {"ok": False, "message": "Ключ не задан"}

    # 5. Telegram
    if k := key("telegram_bot_token"):
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.get(f"https://api.telegram.org/bot{k}/getMe")
                d = r.json()
                if d.get("ok"):
                    results["telegram"] = {"ok": True, "message": f"@{d['result']['username']} ✓"}
                else:
                    results["telegram"] = {"ok": False, "message": d.get("description", "Ошибка")}
        except Exception as e:
            results["telegram"] = {"ok": False, "message": str(e)[:80]}
    else:
        results["telegram"] = {"ok": False, "message": "Токен не задан"}

    # 6. Instagram
    if k := key("instagram_access_token"):
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.get("https://graph.facebook.com/v19.0/me",
                                params={"access_token": k, "fields": "id,name"})
                d = r.json()
                if "error" in d:
                    results["instagram"] = {"ok": False, "message": d["error"]["message"][:80]}
                else:
                    results["instagram"] = {"ok": True, "message": f"{d.get('name', d.get('id'))} ✓"}
        except Exception as e:
            results["instagram"] = {"ok": False, "message": str(e)[:80]}
    else:
        results["instagram"] = {"ok": False, "message": "Токен не задан"}

    # 7. Google Drive
    if db_keys.get("google_service_account_json") or os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"):
        try:
            from core.google_drive import _get_service
            await _get_service()
            results["google_drive"] = {"ok": True, "message": "Google Drive ✓"}
        except Exception as e:
            results["google_drive"] = {"ok": False, "message": str(e)[:80]}
    else:
        results["google_drive"] = {"ok": False, "message": "Service Account не задан"}

    # 8. TikTok
    if k := key("tiktok_access_token"):
        try:
            from publishers.tiktok_pub import get_tiktok_creator_info
            d = await get_tiktok_creator_info()
            ok = d.get("error", {}).get("code") == "ok"
            results["tiktok"] = {"ok": ok, "message": "TikTok ✓" if ok else d.get("error", {}).get("message", "Ошибка")[:80]}
        except Exception as e:
            results["tiktok"] = {"ok": False, "message": str(e)[:80]}
    else:
        results["tiktok"] = {"ok": False, "message": "Токен не задан"}

    total_ok = sum(1 for v in results.values() if v["ok"])
    return {"results": results, "summary": f"{total_ok}/{len(results)} подключений активны"}