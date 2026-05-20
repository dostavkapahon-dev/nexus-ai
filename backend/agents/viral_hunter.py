import json
from agents.base_agent import BaseAgent

class ViralHunter(BaseAgent):
    name = "viral_hunter"

    async def hunt(self, db, niche_id: str, niche: str, platforms: list, audience: dict) -> dict:
        text = await self.call_ai(db, niche_id, {
            "niche": niche,
            "platforms": ", ".join(platforms),
            "audience": json.dumps(audience, ensure_ascii=False)
        })
        try:
            start = text.find('{')
            end = text.rfind('}') + 1
            return json.loads(text[start:end])
        except Exception:
            return {"viral_topics": [], "hooks": [], "formats": [], "hashtags": []}
