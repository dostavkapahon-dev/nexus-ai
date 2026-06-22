import json
from agents.base_agent import BaseAgent

class PlatformAdapter(BaseAgent):
    name = "adapter"

    async def adapt(self, db, niche_id: str, text: str, niche: str) -> dict:
        raw = await self.call_ai(db, niche_id, {"text": text, "niche": niche})
        try:
            start = raw.find('{')
            end = raw.rfind('}') + 1
            data = json.loads(raw[start:end])
        except Exception:
            data = {}
        # Гарантируем версии для всех поддерживаемых платформ.
        defaults = {
            "telegram": text,
            "instagram": text,
            "vk": text,
            "youtube": text,
            "tiktok": text,
            "threads": text,
        }
        for k, v in defaults.items():
            data.setdefault(k, v)
        return data

