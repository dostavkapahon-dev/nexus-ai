import httpx
from agents.base_agent import BaseAgent

POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}?width=1024&height=1024&nologo=true"

class VisualCreator(BaseAgent):
    name = "visual_creator"

    async def create(self, db, niche_id: str, niche: str, topic: str, platform: str, text: str) -> dict:
        image_prompt = await self.call_ai(db, niche_id, {
            "niche": niche, "topic": topic, "platform": platform, "text": text
        })
        image_prompt = image_prompt.strip()[:500]
        encoded = image_prompt.replace(' ', '%20').replace('\n', '%20')
        image_url = POLLINATIONS_URL.format(prompt=encoded)
        return {"image_prompt": image_prompt, "image_url": image_url}
