from agents.base_agent import BaseAgent

class Copywriter(BaseAgent):
    name = "copywriter"

    async def write(self, db, niche_id: str, niche: str, topic: str, hook: str, tone: str, platform: str, goal: str) -> str:
        return await self.call_ai(db, niche_id, {
            "niche": niche, "topic": topic, "hook": hook,
            "tone": tone, "platform": platform, "goal": goal
        })
