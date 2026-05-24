"""
АГЕНТ 6: Daily Trend Analyst
Запускается каждый день в 09:00.
Ищет тренды через DuckDuckGo, анализирует через Gemini,
корректирует завтрашний контент-план, отправляет отчёт в Telegram.
"""
import json
from agents.base_agent import BaseAgent
from core.duckduckgo import search_trends

class TrendAnalyst(BaseAgent):
    name = "trend_analyst"

    async def analyze_trends(self, db, niche_id: str, niche: str, city: str = "") -> dict:
        # Step 1: fetch real trends via DuckDuckGo (free, no key)
        raw_trends = await search_trends(niche, city)

        # Step 2: AI analysis of what patterns mean for content
        text = await self.call_ai(db, niche_id, {
            "niche": niche,
            "city": city or "не указан",
            "raw_trends": raw_trends,
        })

        try:
            start = text.find('{')
            end = text.rfind('}') + 1
            return json.loads(text[start:end])
        except Exception:
            return {
                "top_topics": [niche + " тренды"],
                "best_hooks": ["Ты знаешь об этом?"],
                "recommended_format": "список",
                "corrections": [],
                "summary": raw_trends[:300]
            }
