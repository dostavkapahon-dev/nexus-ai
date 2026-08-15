"""
Профиль Главного агента: что пользователь задаёт «дирижёру» перед работой.
Защищено auth на уровне main.py.
"""
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/agent-profile", tags=["agent-profile"])


class ProfileBody(BaseModel):
    niche: Optional[str] = None
    brand_name: Optional[str] = None
    brand_location: Optional[str] = None
    goals: Optional[str] = None
    audience: Optional[str] = None
    style: Optional[str] = None
    tone_of_voice: Optional[str] = None
    platforms: Optional[list[str]] = None
    posts_per_day: Optional[int] = None
    rules: Optional[str] = None
    constraints: Optional[str] = None
    tasks: Optional[str] = None
    strategy: Optional[str] = None
    timezone: Optional[str] = None
    brand_voice: Optional[str] = None


@router.get("")
async def get_profile():
    from core.agent_profile import get
    return await get()


@router.put("")
async def save_profile(body: ProfileBody):
    from core.agent_profile import save
    return {"ok": True, "profile": await save(body.model_dump(exclude_none=True))}


@router.get("/preview")
async def preview():
    """Текст, который реально уедет в модель.

    Настройки бесполезны, если непонятно, влияют ли они на что-нибудь: здесь
    видно ровно тот блок, который получает дирижёр и каждый агент.
    """
    from core.agent_profile import as_prompt
    text = await as_prompt()
    return {"empty": not text, "prompt": text or
            "Профиль пуст — агент работает по общим правилам, зашитым в систему."}
