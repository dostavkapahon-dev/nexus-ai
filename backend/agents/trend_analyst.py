"""
АГЕНТ 6: Daily Trend Analyst
Запускается каждый день в 09:00.
Ищет тренды в интернете (core/websearch — Perplexity, иначе DuckDuckGo),
анализирует через Gemini,
корректирует завтрашний контент-план, отправляет отчёт в Telegram.
"""
import json
from agents.base_agent import BaseAgent
from core.websearch import search

class TrendAnalyst(BaseAgent):
    name = "trend_analyst"

    async def analyze_trends(self, db, niche_id: str, niche: str, city: str = "") -> dict:
        # Шаг 1: живые тренды из интернета. Через общий поиск, а не напрямую
        # через хрупкий скрейпинг DuckDuckGo: если он сломается, остаётся
        # Perplexity, и агент не остаётся без данных совсем.
        where = f"{niche} {city}".strip()
        found = await search(f"{where} тренды и вирусные форматы сейчас", max_results=8)
        raw_trends = "\n".join(
            f"- {i['title']}: {i.get('snippet', '')}" for i in found.get("items", []))

        # Step 2: AI analysis of what patterns mean for content
        text = await self.call_ai(db, niche_id, {
            "niche": niche,
            "city": city or "не указан",
            "raw_trends": raw_trends,
        })

        try:
            start = text.find('{')
            end = text.rfind('}') + 1
            data = json.loads(text[start:end])
            await self._save_history(niche, city, data, raw_trends, niche_id)
            return data
        except Exception:
            return {
                "top_topics": [niche + " тренды"],
                "best_hooks": ["Ты знаешь об этом?"],
                "recommended_format": "список",
                "corrections": [],
                "summary": raw_trends[:300]
            }

    async def _save_history(self, niche: str, city: str, data: dict,
                            raw: str, niche_id: str = ""):
        """Тренды складываем в историю — по ней видно, как менялась ниша."""
        try:
            from core.research_store import save
            await save(kind="trends", query=f"{niche} {city}".strip(),
                       summary=str(data.get("summary", ""))[:2000],
                       findings=data, sources=[raw[:500]] if raw else [],
                       niche_id=niche_id)
        except Exception:
            pass
