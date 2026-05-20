import json
from agents.base_agent import BaseAgent

class Strategist(BaseAgent):
    name = "strategist"

    async def create_plan(self, db, niche_id: str, niche: str, platforms: list, goal: str, posts_per_day: int, viral_data: dict) -> list:
        text = await self.call_ai(db, niche_id, {
            "niche": niche,
            "platforms": ", ".join(platforms),
            "goal": goal,
            "posts_per_day": posts_per_day,
            "viral_data": json.dumps(viral_data, ensure_ascii=False)
        })
        try:
            start = text.find('[')
            end = text.rfind(']') + 1
            return json.loads(text[start:end])
        except Exception:
            return []
