import json
from agents.base_agent import BaseAgent

class PlatformAdapter(BaseAgent):
    name = "adapter"

    async def adapt(self, db, niche_id: str, text: str, niche: str) -> dict:
        raw = await self.call_ai(db, niche_id, {"text": text, "niche": niche})
        try:
            start = raw.find('{')
            end = raw.rfind('}') + 1
            return json.loads(raw[start:end])
        except Exception:
            return {"telegram": text, "instagram": text, "tiktok": text}
