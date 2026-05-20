from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database.db import get_db
from database.models import CustomPrompt
from core.prompt_store import DEFAULT_PROMPTS, get_prompt, save_prompt, reset_prompt
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/prompts", tags=["prompts"])

class PromptUpdate(BaseModel):
    system_prompt: Optional[str] = None
    user_prompt_template: Optional[str] = None
    ai_model: Optional[str] = None

@router.get("")
async def list_prompts(db: AsyncSession = Depends(get_db)):
    result = {}
    for agent_name in DEFAULT_PROMPTS:
        p = await get_prompt(db, agent_name)
        result[agent_name] = {"system": p.get("system",""), "template": p.get("template",""), "model": p.get("model","")}
    return result

@router.get("/{agent_name}")
async def get_agent_prompt(agent_name: str, db: AsyncSession = Depends(get_db)):
    p = await get_prompt(db, agent_name)
    return {"system": p.get("system",""), "template": p.get("template",""), "model": p.get("model","")}

@router.patch("/{agent_name}")
async def update_prompt(agent_name: str, body: PromptUpdate, db: AsyncSession = Depends(get_db)):
    current = await get_prompt(db, agent_name)
    await save_prompt(db, agent_name,
        body.system_prompt or current.get("system",""),
        body.user_prompt_template or current.get("template",""),
        body.ai_model or current.get("model","")
    )
    return {"ok": True}

@router.post("/{agent_name}/reset")
async def reset_agent_prompt(agent_name: str, db: AsyncSession = Depends(get_db)):
    default = await reset_prompt(db, agent_name)
    return {"ok": True, "prompt": {"system": default.get("system",""), "template": default.get("template",""), "model": default.get("model","")}}
