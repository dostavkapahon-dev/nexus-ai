import time
from abc import ABC, abstractmethod
from sqlalchemy.ext.asyncio import AsyncSession
from core.ai_router import ai_router
from core.prompt_store import get_prompt
from database.models import AgentLog

class BaseAgent(ABC):
    name: str = "base"

    async def call_ai(self, db: AsyncSession, niche_id: str, variables: dict) -> str:
        prompt_data = await get_prompt(db, self.name)
        system = prompt_data.get("system", "")
        template = prompt_data.get("template", "")
        model = prompt_data.get("model", "claude-sonnet-4-20250514")

        user_prompt = template
        for k, v in variables.items():
            user_prompt = user_prompt.replace("{" + k + "}", str(v))

        try:
            result = await ai_router.call(model, system, user_prompt)
            await self.log(db, niche_id, "success", result.get("model_used"), result.get("tokens", 0), result.get("cost", 0), result.get("duration_sec", 0))
            return result["text"]
        except Exception as e:
            await self.log(db, niche_id, "error", model, 0, 0, 0, str(e))
            raise

    async def log(self, db: AsyncSession, niche_id: str, status: str, model: str, tokens: int, cost: float, duration: float, error: str = None):
        db.add(AgentLog(
            niche_id=niche_id,
            agent_name=self.name,
            status=status,
            model_used=model,
            tokens_used=tokens,
            cost_usd=cost,
            duration_sec=duration,
            error=error
        ))
        await db.commit()
