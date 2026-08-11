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

        # Режим экономии из профиля реально выбирает модель. Явно заданная
        # пользователем модель (кастомный промпт) остаётся приоритетнее.
        if not prompt_data.get("custom_model"):
            from core.ai_router import pick_model
            model = await pick_model(self.name, default=model)

        user_prompt = template
        for k, v in variables.items():
            user_prompt = user_prompt.replace("{" + k + "}", str(v))

        # Расход пишет сам ai_router; контекст говорит ему, чей это вызов —
        # так исключается двойной учёт и сохраняется привязка к агенту и нише.
        from core.cost_tracker import current_agent, current_niche_id
        a_token = current_agent.set(self.name)
        n_token = current_niche_id.set(niche_id or "")
        try:
            result = await ai_router.call(model, system, user_prompt)
            return result["text"]
        finally:
            current_agent.reset(a_token)
            current_niche_id.reset(n_token)

    async def log(self, db: AsyncSession, niche_id: str, status: str, model: str, tokens: int, cost: float, duration: float, error: str = None):
        """Пишет лог в ОТДЕЛЬНОЙ сессии.

        Раньше здесь был commit по общей сессии конвейера — он публиковал и чужие
        незавершённые изменения. Своя сессия делает лог независимым от вызывающего.
        """
        from database.db import AsyncSessionLocal
        entry = dict(niche_id=niche_id, agent_name=self.name, status=status,
                     model_used=model, tokens_used=tokens, cost_usd=cost,
                     duration_sec=duration, error=error)
        try:
            async with AsyncSessionLocal() as log_db:
                log_db.add(AgentLog(**entry))
                await log_db.commit()
        except Exception:
            pass
