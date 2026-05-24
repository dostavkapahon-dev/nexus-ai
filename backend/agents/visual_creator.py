from agents.base_agent import BaseAgent

class VisualCreator(BaseAgent):
    name = "visual_creator"

    async def create(self, db, niche_id: str, niche: str, topic: str, platform: str, text: str) -> dict:
        # AI generates English image prompt
        image_prompt = await self.call_ai(db, niche_id, {
            "niche": niche, "topic": topic, "platform": platform, "text": text
        })
        image_prompt = image_prompt.strip()[:500]

        # Try DALL-E 3 → Stability AI → Pollinations (free fallback)
        try:
            from core.media_generator import generate_image
            image_url = await generate_image(image_prompt, platform=platform)
        except Exception:
            encoded = image_prompt.replace(' ', '%20').replace('\n', '%20')
            image_url = f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&nologo=true"

        return {"image_prompt": image_prompt, "image_url": image_url}
