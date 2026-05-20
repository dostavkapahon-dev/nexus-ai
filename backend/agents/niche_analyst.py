import json
from agents.base_agent import BaseAgent

class NicheAnalyst(BaseAgent):
    name = "niche_analyst"

    async def analyze(self, db, niche_id: str, niche: str, city: str, goal: str, tone: str) -> dict:
        text = await self.call_ai(db, niche_id, {
            "niche": niche, "city": city, "goal": goal, "tone": tone
        })
        try:
            start = text.find('{')
            end = text.rfind('}') + 1
            return json.loads(text[start:end])
        except Exception:
            return {"audience": {}, "pain_points": [], "content_pillars": [], "competitors": [], "best_times": []}
