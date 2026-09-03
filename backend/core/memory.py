"""
ПАМЯТЬ ПРОЕКТА — единая сборка сохранённого контекста.
======================================================
Чтобы Cloud Opus и агенты НЕ анализировали всё заново на каждой задаче,
перед запуском дирижёра сюда собирается уже накопленное:
  • активные ниши и их цели,
  • профиль пользователя (продукт, стратегия, режим AI),
  • голос бренда,
  • свежий контент-план и очередь,
  • последние ошибки агентов.

Читает только существующие таблицы — новых сущностей не заводит.
"""
from sqlalchemy import select, desc
from database.db import AsyncSessionLocal
from database.models import (
    Niche, ContentPlan, GeneratedContent, UserProfile, AgentLog,
)


async def build_context(limit_plan: int = 5) -> str:
    """Короткая сводка памяти в виде текста — идёт в контекст Cloud Opus."""
    lines = []
    try:
        async with AsyncSessionLocal() as db:
            prof = (await db.execute(select(UserProfile).limit(1))).scalar_one_or_none()
            if prof:
                lines.append(
                    f"ПРОФИЛЬ: продукт — {(prof.product_description or '—')[:200]}; "
                    f"стратегия — {prof.strategy_focus} на {prof.strategy_duration} дн.; "
                    f"AI — {(prof.active_ai or 'claude')} / {(prof.ai_mode or 'economy')}"
                )

            niches = (await db.execute(
                select(Niche).where(Niche.status == "active")
            )).scalars().all()
            if niches:
                lines.append("АКТИВНЫЕ НИШИ: " + "; ".join(
                    f"{n.name}{(' · ' + n.city) if n.city else ''} → цель {n.goal}, "
                    f"{n.posts_per_day} пост/день, площадки {', '.join(n.platforms or ['telegram'])}"
                    for n in niches[:5]
                ))

            plans = (await db.execute(
                select(ContentPlan).where(ContentPlan.status == "pending")
                .order_by(ContentPlan.day_number).limit(limit_plan)
            )).scalars().all()
            if plans:
                lines.append("БЛИЖАЙШИЙ КОНТЕНТ-ПЛАН: " + "; ".join(
                    f"[{p.id[:8]}] день {p.day_number} · {p.platform} · {p.topic}" for p in plans
                ))

            ready = (await db.execute(
                select(ContentPlan).where(ContentPlan.status == "generated").limit(20)
            )).scalars().all()
            if ready:
                lines.append(f"В ОЧЕРЕДИ НА ПУБЛИКАЦИЮ: {len(ready)} шт.")

            last = (await db.execute(
                select(GeneratedContent).order_by(desc(GeneratedContent.created_at)).limit(1)
            )).scalar_one_or_none()
            if last:
                lines.append(f"ПОСЛЕДНИЙ КОНТЕНТ: {(last.text_reviewed or last.text or '')[:200]}")

            errors = (await db.execute(
                select(AgentLog).where(AgentLog.status == "error")
                .order_by(desc(AgentLog.created_at)).limit(3)
            )).scalars().all()
            if errors:
                lines.append("ПОСЛЕДНИЕ ОШИБКИ АГЕНТОВ: " + "; ".join(
                    f"{e.agent_name}: {(e.error or '')[:100]}" for e in errors
                ))
    except Exception as e:
        lines.append(f"(память частично недоступна: {str(e)[:120]})")

    try:
        from core.brand import get_brand_voice
        voice = get_brand_voice()
        if voice:
            lines.append(f"ГОЛОС БРЕНДА: {voice[:300]}")
    except Exception:
        pass

    return "\n".join(lines) if lines else "Память пуста — это первая задача."
