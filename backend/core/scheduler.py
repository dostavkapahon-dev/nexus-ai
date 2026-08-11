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

                # Единый диспетчер публикации (тот же, что в оркестраторе):
                # официальный API площадки → браузерный агент.
                from core.orchestrator import nexus_core
                for platform in platforms:
                    try:
                        res = await nexus_core._publish_one(platform, text, image_url or "")
                        status = "published" if res.get("ok") else "failed"
                        db.add(Publication(plan_id=plan.id, platform=platform, status=status))
                        if not res.get("ok") and chat_id:
                            await send_message(chat_id, f"⚠️ {platform}: {str(res.get('error'))[:80]}")
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


async def run_token_maintenance():
    """Следит за токенами площадок: продлевает Instagram и предупреждает о протухании.

    Раньше токен Instagram умирал через 60 дней МОЛЧА, и об этом узнавали только
    когда падала публикация.
    """
    from connectors import health_all, get_connector
    from core.telegram_bot import send_message

    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    problems = []
    for st in await health_all():
        platform = st.get("platform", "")
        if not st.get("configured"):
            continue
        days = st.get("days_left")
        # Меньше двух недель — пробуем продлить заранее, не дожидаясь падения.
        if days is not None and days < 14:
            res = await get_connector(platform).refresh_token()
            if res.get("refreshed"):
                problems.append(f"🔄 {platform}: токен продлён "
                                f"(осталось было {days} дн.)")
            else:
                problems.append(f"⚠️ {platform}: токен истекает через {days} дн., "
                                f"продлить не удалось — {res.get('error', '')[:80]}")
        elif not st.get("ok"):
            problems.append(f"❌ {platform}: {str(st.get('error'))[:100]}")

    if problems and chat_id and os.getenv("TELEGRAM_BOT_TOKEN"):
        await send_message(chat_id, "🔑 <b>Токены площадок</b>\n\n" + "\n".join(problems))
    return {"checked": True, "problems": problems}


def _tracked(kind: str, goal: str, fn):
    """Оборачивает джоб в задачу: у ночного запуска тоже есть id, статус и текст ошибки."""
    async def job():
        from core.task_manager import create, run
        task_id = await create(kind, goal, source="scheduler")
        await run(task_id, fn)
    return job


def start_scheduler():
    """Расписание по таймзоне Pakhon Studio (Asia/Almaty, UTC+5)."""
    global _scheduler
    try:
        from core.brand import TIMEZONE
    except Exception:
        TIMEZONE = os.getenv("NEXUS_TZ", "Asia/Almaty")
    _scheduler = AsyncIOScheduler(timezone=TIMEZONE)

    # 09:00 — Research/тренды (исследование рынка)
    _scheduler.add_job(_tracked("trends", "Ежедневный анализ трендов", run_daily_trends),
                       CronTrigger(hour=9,  minute=0), id="trends",  replace_existing=True)
    # 09:30 — Фабрика контента (автоцикл Reels)
    _scheduler.add_job(_tracked("factory", "Ежедневная фабрика контента", run_daily_factory),
                       CronTrigger(hour=9,  minute=30), id="factory", replace_existing=True)
    # 10:00 — Генерация материалов на день
    _scheduler.add_job(_tracked("generate", "Ежедневная генерация материалов", run_daily_generate),
                       CronTrigger(hour=10, minute=0), id="generate", replace_existing=True)
    # 19:00 — Публикация (пик активности IG/TG по Алматы)
    _scheduler.add_job(_tracked("publish", "Ежедневная публикация", run_daily_publish),
                       CronTrigger(hour=19, minute=0), id="publish",  replace_existing=True)
    # 22:00 — Итоговый статус дня владельцу
    _scheduler.add_job(_tracked("report", "Ежедневный отчёт", run_daily_report),
                       CronTrigger(hour=22, minute=0), id="report",   replace_existing=True)
    # Воскресенье 20:00 — еженедельная аналитика
    # 08:00 — проверка и продление токенов площадок (до утренних публикаций)
    _scheduler.add_job(_tracked("tokens", "Проверка токенов площадок", run_token_maintenance),
                       CronTrigger(hour=8, minute=0), id="tokens", replace_existing=True)
    _scheduler.add_job(_tracked("analytics", "Еженедельная аналитика", run_weekly_analytics),
                       CronTrigger(day_of_week="sun", hour=20, minute=0),
                       id="weekly", replace_existing=True)

    _scheduler.start()
    return _scheduler
