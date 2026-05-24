"""
АГЕНТ 7: Sales Funnel Agent
Генерирует ответы на комментарии по воронке продаж.
Работает с 3 стадиями: осведомлённость → интерес → покупка.
"""
import json
from agents.base_agent import BaseAgent

FUNNEL_KEYWORDS = {
    "interest": ["хочу", "как получить", "где купить", "цена", "сколько стоит", "интересно", "расскажи", "что это"],
    "buy":      ["покупаю", "оплата", "как оплатить", "реквизиты", "куда платить", "беру", "заказываю"],
    "negative": ["обман", "развод", "фейк", "не верю", "ложь", "мусор", "плохо", "дорого"],
}

def detect_intent(comment: str) -> str:
    comment_low = comment.lower()
    for intent, keywords in FUNNEL_KEYWORDS.items():
        if any(k in comment_low for k in keywords):
            return intent
    return "general"

class FunnelAgent(BaseAgent):
    name = "funnel_agent"

    async def generate_reply(self, db, niche_id: str, comment: str, niche: str,
                              funnel_stage: int = 1, lead_magnet_url: str = "",
                              payment_url: str = "") -> dict:
        intent = detect_intent(comment)

        result = await self.call_ai(db, niche_id, {
            "niche": niche,
            "comment": comment,
            "intent": intent,
            "funnel_stage": funnel_stage,
            "lead_magnet_url": lead_magnet_url or "ссылка в шапке профиля",
            "payment_url": payment_url or "напишите в личные сообщения",
        })

        try:
            start = result.find('{')
            end = result.rfind('}') + 1
            data = json.loads(result[start:end])
        except Exception:
            data = {"reply": result.strip()[:500], "intent": intent}

        return {"reply": data.get("reply", ""), "intent": intent, "should_reply": intent != "general"}

    async def get_funnel_stats(self, db, niche_id: str) -> dict:
        """Returns basic funnel statistics from DB logs."""
        from sqlalchemy import select, func
        from database.models import AgentLog
        logs = await db.execute(
            select(AgentLog)
            .where(AgentLog.niche_id == niche_id, AgentLog.agent_name == "funnel_agent")
            .order_by(AgentLog.created_at.desc())
            .limit(100)
        )
        all_logs = logs.scalars().all()
        return {
            "total_replies": len(all_logs),
            "successful": sum(1 for l in all_logs if l.status == "success"),
        }
