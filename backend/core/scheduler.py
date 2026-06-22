"""
NEXUS AI Scheduler — cron jobs for all automated tasks.

Schedule:
  09:00 UTC — Agent 6: Daily Trend Analysis
  12:00 UTC — Agent 3+4: Generate today's content
  18:00 UTC — Agent 5: Publish queue
  23:00 UTC — Agent 8: Daily summary report
"""
import os
import asyncio
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

_scheduler: AsyncIOScheduler = None

async def run_daily_trends():
    """Agent 6: fetch trends and update content plan."""
    from database.db import AsyncSessionLocal
    from database.models import Niche, ContentPlan, UserProfile
    from sqlalchemy import select
    from agents.trend_analyst import TrendAnalyst
    from agents.reporter import reporter
    from core.telegram_bot import send_message

    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    analyst = TrendAnalyst()

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Niche).where(Niche.status == "active"))
        niches = result.scalars().all()

        for niche in niches:
            try:
                trend_data = await analyst.analyze_trends(db, niche.id, niche.name, niche.city or "")
                report_text = await reporter.build_trend_report(db, trend_data, niche.name)
                if chat_id:
                    await send_message(chat_id, report_text)
            except Exception as e:
                if chat_id:
                    await send_message(chat_id, f"⚠️ Ошибка анализа трендов [{niche.name}]: {str(e)[:100]}")

async def run_daily_generate():
    """Agent 3+4: generate content for today's plans."""
    from database.db import AsyncSessionLocal
    from database.models import ContentPlan
    from sqlalchemy import select
    from core.orchestrator import nexus_core
    from core.telegram_bot import send_message

    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ContentPlan).where(ContentPlan.status == "pending").limit(10)
        )
        plans = result.scalars().all()

    count = 0
    for plan in plans:
        try:
            await nexus_core.generate_content_for_plan(plan.id)
            count += 1
        except Exception as e:
            if chat_id:
                await send_message(chat_id, f"⚠️ Ошибка генерации поста: {str(e)[:100]}")

    if chat_id and count:
        await send_message(chat_id, f"✍️ Создано постов: {count}")

async def run_daily_publish():
    """Agent 5: publish ready content from queue."""
    from database.db import AsyncSessionLocal
    from database.models import ContentPlan, Niche, GeneratedContent, Publication
    from sqlalchemy import select
    from publishers.telegram_pub import publish_telegram
    from core.telegram_bot import send_message

    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    published = 0

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ContentPlan).where(ContentPlan.status == "generated").limit(10)
        )
        plans = result.scalars().all()

        for plan in plans:
            try:
                niche_r = await db.execute(select(Niche).where(Niche.id == plan.niche_id))
                niche = niche_r.scalar_one_or_none()
                if not niche:
                    continue

                content_r = await db.execute(
                    select(GeneratedContent).where(GeneratedContent.plan_id == plan.id).limit(1)
                )
                content = content_r.scalar_one_or_none()
                if not content:
                    continue

                text = content.text_reviewed or content.text or ""
                image_url = content.image_url or ""

                platforms = niche.platforms or ["telegram"]

                for platform in platforms:
                    try:
                        if platform == "telegram":
                            tg_chat = os.getenv("TELEGRAM_CHAT_ID", "")
                            if tg_chat:
                                await publish_telegram(tg_chat, text, image_url or None)
                                db.add(Publication(plan_id=plan.id, platform="telegram", status="published"))

                        elif platform == "instagram":
                            from publishers.instagram_pub import publish_instagram
                            if os.getenv("INSTAGRAM_ACCESS_TOKEN"):
                                await publish_instagram(text, image_url or None)
                                db.add(Publication(plan_id=plan.id, platform="instagram", status="published"))

                        elif platform == "tiktok":
                            from publishers.tiktok_pub import publish_tiktok_photo
                            if os.getenv("TIKTOK_ACCESS_TOKEN") and image_url:
                                await publish_tiktok_photo(text, image_url)
                                db.add(Publication(plan_id=plan.id, platform="tiktok", status="published"))

                        elif platform == "vk":
                            from publishers.vk_pub import publish_vk
                            if os.getenv("VK_ACCESS_TOKEN"):
                                await publish_vk(text, image_url or None)
                                db.add(Publication(plan_id=plan.id, platform="vk", status="published"))

                        elif platform == "threads":
                            from publishers.threads_pub import publish_threads
                            if os.getenv("THREADS_ACCESS_TOKEN"):
                                await publish_threads(text, image_url or None)
                                db.add(Publication(plan_id=plan.id, platform="threads", status="published"))

                    except Exception as e:
                        if chat_id:
                            await send_message(chat_id, f"⚠️ {platform}: {str(e)[:80]}")

                plan.status = "published"
                published += 1
            except Exception as e:
                if chat_id:
                    await send_message(chat_id, f"⚠️ Ошибка публикации: {str(e)[:100]}")

        await db.commit()

    if chat_id:
        await send_message(chat_id,
            f"📤 <b>Публикация завершена</b>\n✅ Опубликовано постов: {published}")

async def run_daily_report():
    """Agent 8: send daily summary to Telegram."""
    from database.db import AsyncSessionLocal
    from agents.reporter import reporter
    from core.telegram_bot import send_message

    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not chat_id:
        return

    async with AsyncSessionLocal() as db:
        report = await reporter.build_status_report(db)
    await send_message(chat_id, report)

async def run_daily_factory():
    """09:30 Алматы — автоцикл «Фабрика»: анализ→ТЗ→видео→(публикация)→отчёт.
    Публикует, если AUTO_PUBLISH=1, иначе шлёт превью в Telegram.
    """
    from core.content_factory import run_factory
    auto = os.getenv("AUTO_PUBLISH", "0") == "1"
    try:
        await run_factory(topic=None, dry_run=not auto)
    except Exception as e:
        chat = os.getenv("TELEGRAM_CHAT_ID", "")
        if chat:
            from core.telegram_bot import send_message
            await send_message(chat, f"⚠️ Фабрика: {str(e)[:120]}")


async def run_weekly_analytics():
    """Воскресенье 20:00 — еженедельная аналитика и сводка владельцу."""
    from database.db import AsyncSessionLocal
    from agents.reporter import reporter
    from core.telegram_bot import send_message

    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not chat_id:
        return
    async with AsyncSessionLocal() as db:
        try:
            report = await reporter.build_status_report(db)
        except Exception as e:
            report = f"⚠️ Ошибка еженедельной аналитики: {str(e)[:120]}"
    await send_message(chat_id, "📊 <b>Еженедельный отчёт Pakhon Studio</b>\n\n" + report)


def start_scheduler():
    """Расписание по таймзоне Pakhon Studio (Asia/Almaty, UTC+5)."""
    global _scheduler
    try:
        from core.brand import TIMEZONE
    except Exception:
        TIMEZONE = os.getenv("NEXUS_TZ", "Asia/Almaty")
    _scheduler = AsyncIOScheduler(timezone=TIMEZONE)

    # 09:00 — Research/тренды (исследование рынка)
    _scheduler.add_job(run_daily_trends,   CronTrigger(hour=9,  minute=0), id="trends",  replace_existing=True)
    # 09:30 — Фабрика контента (автоцикл Reels)
    _scheduler.add_job(run_daily_factory,  CronTrigger(hour=9,  minute=30), id="factory", replace_existing=True)
    # 10:00 — Генерация материалов на день
    _scheduler.add_job(run_daily_generate, CronTrigger(hour=10, minute=0), id="generate", replace_existing=True)
    # 19:00 — Публикация (пик активности IG/TG по Алматы)
    _scheduler.add_job(run_daily_publish,  CronTrigger(hour=19, minute=0), id="publish",  replace_existing=True)
    # 22:00 — Итоговый статус дня владельцу
    _scheduler.add_job(run_daily_report,   CronTrigger(hour=22, minute=0), id="report",   replace_existing=True)
    # Воскресенье 20:00 — еженедельная аналитика
    _scheduler.add_job(run_weekly_analytics, CronTrigger(day_of_week="sun", hour=20, minute=0),
                       id="weekly", replace_existing=True)

    _scheduler.start()
    return _scheduler
