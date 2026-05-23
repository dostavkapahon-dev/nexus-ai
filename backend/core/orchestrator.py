import os
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database.db import AsyncSessionLocal
from database.models import Niche, ContentPlan, GeneratedContent, NicheAnalysisCache, UserProfile
from agents.niche_analyst import NicheAnalyst
from agents.viral_hunter import ViralHunter
from agents.strategist import Strategist
from agents.copywriter import Copywriter
from agents.reviewer import Reviewer
from agents.visual_creator import VisualCreator
from agents.voice_adapter import VoiceAdapter
from agents.adapter import PlatformAdapter

_broadcast_fn = None

def set_broadcast(fn):
    global _broadcast_fn
    _broadcast_fn = fn

async def broadcast(niche_id: str, data: dict):
    if _broadcast_fn:
        await _broadcast_fn(niche_id, data)

async def _send_telegram_report(text: str):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as c:
            await c.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": False}
            )
    except Exception:
        pass

async def _get_profile(db):
    result = await db.execute(select(UserProfile).limit(1))
    return result.scalar_one_or_none()

class NexusCore:
    async def run_full_pipeline(self, niche_id: str):
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Niche).where(Niche.id == niche_id))
            niche = result.scalar_one_or_none()
            if not niche:
                return

            profile = await _get_profile(db)
            ai_mode = profile.ai_mode if profile else "economy"
            niche_key = f"{niche.name.lower().strip()}:{(niche.city or '').lower().strip()}"

            # Check Google Drive cache
            cache_result = await db.execute(
                select(NicheAnalysisCache).where(NicheAnalysisCache.niche_key == niche_key)
            )
            cache = cache_result.scalar_one_or_none()

            if cache and cache.analysis_data:
                niche_profile = cache.analysis_data.get("niche_profile", {})
                viral_data = cache.analysis_data.get("viral_data", {})
                await broadcast(niche_id, {"event": "cache_hit", "agent": "niche_analyst", "drive_url": cache.drive_url})
            else:
                await broadcast(niche_id, {"event": "agent_start", "agent": "niche_analyst"})
                analyst = NicheAnalyst()
                niche_profile = await analyst.analyze(db, niche_id, niche.name, niche.city or "", niche.goal, niche.tone_of_voice)
                await broadcast(niche_id, {"event": "agent_done", "agent": "niche_analyst"})

                await broadcast(niche_id, {"event": "agent_start", "agent": "viral_hunter"})
                hunter = ViralHunter()
                viral_data = await hunter.hunt(db, niche_id, niche.name, niche.platforms or ["telegram"], niche_profile.get("audience", {}))
                await broadcast(niche_id, {"event": "agent_done", "agent": "viral_hunter"})

                # Upload to Google Drive
                drive_url = ""
                drive_file_id = ""
                folder_id = (profile.google_drive_folder_id if profile else "") or os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
                if folder_id:
                    try:
                        from core.google_drive import upload_json
                        fname = f"nexus_{niche_key.replace(':', '_').replace(' ', '_')}.json"
                        uploaded = await upload_json(folder_id, fname, {
                            "niche": niche.name, "city": niche.city,
                            "niche_profile": niche_profile, "viral_data": viral_data
                        })
                        drive_url = uploaded.get("webViewLink", "")
                        drive_file_id = uploaded.get("id", "")
                    except Exception:
                        pass

                db.add(NicheAnalysisCache(
                    niche_key=niche_key, drive_file_id=drive_file_id,
                    drive_url=drive_url,
                    analysis_data={"niche_profile": niche_profile, "viral_data": viral_data}
                ))
                await db.commit()

                msg = (
                    f"✅ <b>NEXUS AI — Анализ готов</b>\n\n"
                    f"📌 Ниша: <b>{niche.name}</b>\n"
                    f"🏙 Город: {niche.city or '—'}\n"
                    f"🎯 Цель: {niche.goal}\n"
                    f"🤖 Режим AI: {ai_mode.upper()}\n"
                )
                if drive_url:
                    msg += f"\n📂 <a href=\"{drive_url}\">Открыть анализ на Google Диске</a>"
                await _send_telegram_report(msg)

            await broadcast(niche_id, {"event": "agent_start", "agent": "strategist"})
            strategist = Strategist()
            plan_items = await strategist.create_plan(
                db, niche_id, niche.name,
                niche.platforms or ["telegram"], niche.goal,
                niche.posts_per_day, viral_data
            )
            await broadcast(niche_id, {"event": "agent_done", "agent": "strategist"})

            for item in plan_items[:30]:
                plan = ContentPlan(
                    niche_id=niche_id,
                    day_number=item.get("day", 1),
                    platform=item.get("platform", "telegram"),
                    topic=item.get("topic", ""),
                    hook=item.get("hook", ""),
                    format=item.get("format", "post"),
                    status="pending"
                )
                db.add(plan)
            await db.commit()
            await broadcast(niche_id, {"event": "pipeline_complete"})

    async def generate_content_for_plan(self, plan_id: str):
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(ContentPlan).where(ContentPlan.id == plan_id))
            plan = result.scalar_one_or_none()
            if not plan:
                return

            niche_result = await db.execute(select(Niche).where(Niche.id == plan.niche_id))
            niche = niche_result.scalar_one_or_none()
            if not niche:
                return

            await broadcast(plan.niche_id, {"event": "agent_start", "agent": "copywriter"})
            copywriter = Copywriter()
            text = await copywriter.write(db, plan.niche_id, niche.name, plan.topic, plan.hook or "", niche.tone_of_voice, plan.platform, niche.goal)
            await broadcast(plan.niche_id, {"event": "agent_done", "agent": "copywriter"})

            await broadcast(plan.niche_id, {"event": "agent_start", "agent": "reviewer"})
            reviewer = Reviewer()
            review_result = await reviewer.review(db, plan.niche_id, text, niche.name, niche.goal, plan.platform)
            text_reviewed = review_result.get("text_reviewed", text)
            score = review_result.get("score", 7.0)
            await broadcast(plan.niche_id, {"event": "agent_done", "agent": "reviewer"})

            await broadcast(plan.niche_id, {"event": "agent_start", "agent": "voice_adapter"})
            voice = VoiceAdapter()
            text_voiced = await voice.adapt(db, plan.niche_id, text_reviewed, niche.about_user or "", niche.tone_of_voice)
            await broadcast(plan.niche_id, {"event": "agent_done", "agent": "voice_adapter"})

            await broadcast(plan.niche_id, {"event": "agent_start", "agent": "visual_creator"})
            visual = VisualCreator()
            visual_result = await visual.create(db, plan.niche_id, niche.name, plan.topic, plan.platform, text_voiced)
            await broadcast(plan.niche_id, {"event": "agent_done", "agent": "visual_creator"})

            await broadcast(plan.niche_id, {"event": "agent_start", "agent": "adapter"})
            adapter = PlatformAdapter()
            platform_versions = await adapter.adapt(db, plan.niche_id, text_voiced, niche.name)
            await broadcast(plan.niche_id, {"event": "agent_done", "agent": "adapter"})

            content = GeneratedContent(
                plan_id=plan_id, text=text, text_reviewed=text_voiced,
                image_url=visual_result.get("image_url"),
                image_prompt=visual_result.get("image_prompt"),
                score=score, platform_versions=platform_versions
            )
            db.add(content)
            plan.status = "generated"
            await db.commit()
            await broadcast(plan.niche_id, {"event": "pipeline_complete"})

nexus_core = NexusCore()