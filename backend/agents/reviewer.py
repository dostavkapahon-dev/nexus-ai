import json
from agents.base_agent import BaseAgent

class Reviewer(BaseAgent):
    name = "reviewer"

    async def review(self, db, niche_id: str, text: str, niche: str, goal: str, platform: str) -> dict:
        raw = await self.call_ai(db, niche_id, {
            "text": text, "niche": niche, "goal": goal, "platform": platform
        })
        try:
            start = raw.find('{')
            end = raw.rfind('}') + 1
            return json.loads(raw[start:end])
        except Exception:
            return {"text_reviewed": text, "score": 7.0, "improvements": []}
