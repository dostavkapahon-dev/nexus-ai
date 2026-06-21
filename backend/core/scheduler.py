"""
NEXUS AI Scheduler — config-driven cron automation.

Jobs (hours are configurable via AutomationConfig, all UTC):
  autopilot  — ensure every active niche has a fresh content plan
  trends     — daily trend analysis + Telegram report
  generate   — turn pending plan items into content (+ optional video)
  publish    — push generated content to every configured platform
  report     — daily summary to Telegram

The whole pipeline is gated by AutomationConfig.enabled — when off, jobs are
registered but return immediately, so nothing runs until the user flips the
master switch in the UI.
"""
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

_scheduler: AsyncIOScheduler = None


async def _load_config() -> dict:
    from core.automation import get_config
    return await get_config()


async def _is_enabled() -> bool:
    cfg = await _load_config()
    return bool(cfg.get("enabled"))


# --------------------------------------------------------------------------- #
# Jobs
# --------------------------------------------------------------------------- #
async def run_autopilot(force: bool = False):
    """Create a content plan for any active niche that has run dry."""
    if not force and not await _is_enabled():
        return
    cfg = await _load_config()
    if not cfg.get("autopilot"):
        return

    from database.db import AsyncSessionLocal
    from database.models import Niche, ContentPlan
    from sqlalchemy import select, func
    from core.orchestrator import nexus_core
    from core.telegram_bot import send_message

    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    async with AsyncSessionLocal() as db:
        niches = (await db.execute(select(Niche).where(Niche.status == "active"))).scalars().all()

    for niche in niches:
        async with AsyncSessionLocal() as db:
            backlog = await db.scalar(
                select(func.count(ContentPlan.id)).where(
                    ContentPlan.niche_id == niche.id,
                    ContentPlan.status.in_(["pending", "generated"]),
                )
            )
        if backlog and backlog > 0:
            continue
        try:
            await nexus_core.run_full_pipeline(niche.id)
            if chat_id:
                await send_message(chat_id, f"🧭 Автопилот: создан новый план для «{niche.name}»")
        except Exception as e:
            if chat_id:
                await send_message(chat_id, f"⚠️ Автопилот [{niche.name}]: {str(e)[:100]}")


async def run_daily_trends(force: bool = False):
    if not force and not await _is_enabled():
        return
    from database.db import AsyncSessionLocal
    from database.models import Niche
    from sqlalchemy import select
    from agents.trend_analyst import TrendAnalyst
    from agents.reporter import reporter
    from core.telegram_bot import send_message

    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    analyst = TrendAnalyst()
    async with AsyncSessionLocal() as db:
        niches = (await db.execute(select(Niche).where(Niche.status == "active"))).scalars().all()
        for niche in niches:
            try:
                trend_data = await analyst.analyze_trends(db, niche.id, niche.name, niche.city or "")
                report_text = await reporter.build_trend_report(db, trend_data, niche.name)
                if chat_id:
                    await send_message(chat_id, report_text)
            except Exception as e:
                if chat_id:
                    await send_message(chat_id, f"⚠️ Ошибка анализа трендов [{niche.name}]: {str(e)[:100]}")


async def run_daily_generate(force: bool = False):
    if not force and not await _is_enabled():
        return
    cfg = await _load_config()
    from database.db import AsyncSessionLocal
    from database.models import ContentPlan, GeneratedContent
    from sqlalchemy import select
    from core.orchestrator import nexus_core
    from core.telegram_bot import send_message

    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    batch = cfg.get("batch_size") or 10
    async with AsyncSessionLocal() as db:
        plans = (await db.execute(
            select(ContentPlan).where(ContentPlan.status == "pending").limit(batch)
        )).scalars().all()
        plan_ids = [p.id for p in plans]

    count = 0
    for plan_id in plan_ids:
        try:
            await nexus_core.generate_content_for_plan(plan_id)
            if cfg.get("auto_video"):
                await _attach_video(plan_id, cfg.get("video_provider") or "auto")
            count += 1
        except Exception as e:
            if chat_id:
                await send_message(chat_id, f"⚠️ Ошибка генерации поста: {str(e)[:100]}")

    if chat_id and count:
        await send_message(chat_id, f"✍️ Создано постов: {count}")


async def _attach_video(plan_id: str, provider: str):
    """Generate a clip for a freshly generated post and store its URL."""
    from database.db import AsyncSessionLocal
    from database.models import GeneratedContent
    from sqlalchemy import select
    from core.media_generator import generate_video

    async with AsyncSessionLocal() as db:
        content = await db.scalar(
            select(GeneratedContent).where(GeneratedContent.plan_id == plan_id).limit(1)
        )
        if not content:
            return
        prompt = content.text_reviewed or content.text or ""
        if not prompt:
            return
        url = await generate_video(prompt, content.image_url, provider=provider)
        if url:
            content.video_url = url
            await db.commit()


async def run_daily_publish(force: bool = False):
    if not force and not await _is_enabled():
        return
    cfg = await _load_config()
    from database.db import AsyncSessionLocal
    from database.models import ContentPlan
    from sqlalchemy import select
    from core.orchestrator import nexus_core
    from core.telegram_bot import send_message

    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    batch = cfg.get("batch_size") or 10
    async with AsyncSessionLocal() as db:
        plans = (await db.execute(
            select(ContentPlan).where(ContentPlan.status == "generated").limit(batch)
        )).scalars().all()
        plan_ids = [p.id for p in plans]

    published = 0
    for plan_id in plan_ids:
        try:
            await nexus_core.publish_plan(plan_id)
            published += 1
        except Exception as e:
            if chat_id:
                await send_message(chat_id, f"⚠️ Ошибка публикации: {str(e)[:100]}")

    if chat_id:
        await send_message(chat_id, f"📤 <b>Публикация завершена</b>\n✅ Постов: {published}")


async def run_daily_report(force: bool = False):
    if not force and not await _is_enabled():
        return
    from database.db import AsyncSessionLocal
    from agents.reporter import reporter
    from core.telegram_bot import send_message

    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not chat_id:
        return
    async with AsyncSessionLocal() as db:
        report = await reporter.build_status_report(db)
    await send_message(chat_id, report)


# Map job id → (callable, config hour key). Autopilot runs hourly.
JOBS = {
    "trends": (run_daily_trends, "schedule_trends"),
    "generate": (run_daily_generate, "schedule_generate"),
    "publish": (run_daily_publish, "schedule_publish"),
    "report": (run_daily_report, "schedule_report"),
}


def _apply_jobs(cfg: dict):
    """(Re)register all cron jobs from the given config dict."""
    for job_id, (fn, hour_key) in JOBS.items():
        hour = int(cfg.get(hour_key, 12))
        _scheduler.add_job(fn, CronTrigger(hour=hour, minute=0), id=job_id, replace_existing=True)
    # Autopilot tops up plans every hour so niches never run dry.
    _scheduler.add_job(run_autopilot, CronTrigger(minute=5), id="autopilot", replace_existing=True)


DEFAULT_HOURS = {
    "schedule_trends": 9, "schedule_generate": 12,
    "schedule_publish": 18, "schedule_report": 23,
}


def start_scheduler():
    """Start with default cron times; lifespan calls reschedule() right after
    to realign with the stored config once the DB is ready."""
    global _scheduler
    _scheduler = AsyncIOScheduler(timezone="UTC")
    _apply_jobs(DEFAULT_HOURS)
    _scheduler.start()
    return _scheduler


async def reschedule():
    """Re-apply cron times from stored config (call after the user saves settings)."""
    if not _scheduler:
        return
    cfg = await _load_config()
    _apply_jobs(cfg)


async def trigger_now(job_id: str):
    """Run a job immediately, bypassing its schedule (still respects `enabled`)."""
    if job_id == "autopilot":
        return await run_autopilot(force=True)
    fn = JOBS.get(job_id, (None,))[0]
    if fn:
        return await fn(force=True)
