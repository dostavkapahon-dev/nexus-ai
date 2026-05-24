"""
АГЕНТ 8: Dashboard Reporter
Собирает данные со всех агентов, формирует отчёт,
отправляет в Telegram по команде /status или автоматически.
"""
import os
from datetime import datetime, timedelta
from sqlalchemy import select, func
from database.models import Niche, ContentPlan, GeneratedContent, Publication, AgentLog, UserProfile

class Reporter:
    name = "reporter"

    async def build_status_report(self, db) -> str:
        """Full system status report for Telegram."""
        now = datetime.utcnow()

        # Profile/goals
        prof_r = await db.execute(select(UserProfile).limit(1))
        profile = prof_r.scalar_one_or_none()
        ai_mode = (profile.ai_mode if profile else "economy").upper()
        active_ai = (profile.active_ai if profile else "claude").upper()

        # Niches
        niches_r = await db.execute(select(Niche))
        niches = niches_r.scalars().all()
        active_niches = [n for n in niches if n.status == "active"]

        # Content stats
        total_planned = await db.scalar(select(func.count(ContentPlan.id))) or 0
        total_generated = await db.scalar(
            select(func.count(ContentPlan.id)).where(ContentPlan.status == "generated")
        ) or 0
        total_published = await db.scalar(
            select(func.count(Publication.id))
        ) or 0
        in_queue = await db.scalar(
            select(func.count(ContentPlan.id)).where(ContentPlan.status.in_(["generated", "pending"]))
        ) or 0

        # Cost stats
        total_cost = await db.scalar(select(func.sum(AgentLog.cost_usd))) or 0.0
        total_tokens = await db.scalar(select(func.sum(AgentLog.tokens_used))) or 0

        # Agent health
        recent_errors = await db.scalar(
            select(func.count(AgentLog.id)).where(
                AgentLog.status == "error",
                AgentLog.created_at >= now - timedelta(hours=24)
            )
        ) or 0

        lines = [
            "═══════════════════════════════",
            "🤖 <b>NEXUS AI — Статус системы</b>",
            f"📅 {now.strftime('%d.%m.%Y %H:%M')} UTC",
            "═══════════════════════════════",
            "",
            f"🎯 <b>Ниши:</b> {len(active_niches)} активных / {len(niches)} всего",
        ]
        for n in active_niches[:3]:
            lines.append(f"  • <b>{n.name}</b> ({n.city or '—'}) · {n.posts_per_day} пост/день")

        lines += [
            "",
            "📤 <b>Контент:</b>",
            f"  • Запланировано: {total_planned}",
            f"  • Создано: {total_generated}",
            f"  • Опубликовано: {total_published}",
            f"  • В очереди: {in_queue}",
            "",
            "💰 <b>Расходы:</b>",
            f"  • Потрачено: ${total_cost:.4f}",
            f"  • Токенов: {total_tokens:,}",
            "",
            f"🧠 <b>AI режим:</b> {active_ai} ({ai_mode})",
            f"🔧 <b>Агентов:</b> 8 модулей",
            f"⚠️ <b>Ошибок за 24ч:</b> {recent_errors}",
            "",
            "═══════════════════════════════",
        ]
        return "\n".join(lines)

    async def build_trend_report(self, db, trend_data: dict, niche: str) -> str:
        top = trend_data.get("top_topics", [])[:3]
        hooks = trend_data.get("best_hooks", [])[:2]
        summary = trend_data.get("summary", "")
        now = datetime.utcnow()
        lines = [
            f"📈 <b>ТРЕНДЫ ДНЯ — {niche}</b>",
            f"📅 {now.strftime('%d.%m.%Y')}",
            "",
        ]
        if top:
            lines.append("🔥 <b>Топ темы:</b>")
            for t in top:
                lines.append(f"  • {t}")
        if hooks:
            lines.append("")
            lines.append("💡 <b>Лучшие хуки:</b>")
            for h in hooks:
                lines.append(f"  • {h}")
        if summary:
            lines += ["", f"📝 {summary[:200]}"]
        lines.append("\n📅 Контент-план скорректирован автоматически")
        return "\n".join(lines)

reporter = Reporter()
