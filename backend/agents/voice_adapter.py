from agents.base_agent import BaseAgent

class VoiceAdapter(BaseAgent):
    name = "voice_adapter"

    async def adapt(self, db, niche_id: str, text: str, about_user: str, tone: str) -> str:
        if not about_user:
            return text
        return await self.call_ai(db, niche_id, {
            "text": text, "about_user": about_user, "tone": tone
        })
