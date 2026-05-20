import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database.db import AsyncSessionLocal
from database.models import Niche, ContentPlan, GeneratedContent
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

class NexusCore:
    async def run_full_pipeline(self, niche_id: str):
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Niche).where(Niche.id == niche_id))
            niche = result.scalar_one_or_none()
            if not niche:
                return

            await broadcast(niche_id, {"event": "agent_start", "agent": "niche_analyst"})
            analyst = NicheAnalyst()
            niche_profile = await analyst.analyze(db, niche_id, niche.name, niche.city or '', niche.goal, niche.tone_of_voice)
            await broadcast(niche_id, {"event": "agent_done", "agent": "niche_analyst"})

            await broadcast(niche_id, {"event": "agent_start", "agent": "viral_hunter"})
            hunter = ViralHunter()
            viral_data = await hunter.hunt(db, niche_id, niche.name, niche.platforms or ['telegram'], niche_profile.get("audience", {}))
            await broadcast(niche_id, {"event": "agent_done", "agent": "viral_hunter"})

            await broadcast(niche_id, {"event": "agent_start", "agent": "strategist"})
            strategist = Strategist()
            plan_items = await strategist.create_plan(db, niche_id, niche.name, niche.platforms or ['telegram'], niche.goal, niche.posts_per_day, viral_data)
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
            text = await copywriter.write(db, plan.niche_id, niche.name, plan.topic, plan.hook or '', niche.tone_of_voice, plan.platform, niche.goal)
            await broadcast(plan.niche_id, {"event": "agent_done", "agent": "copywriter"})

            await broadcast(plan.niche_id, {"event": "agent_start", "agent": "reviewer"})
            reviewer = Reviewer()
            review_result = await reviewer.review(db, plan.niche_id, text, niche.name, niche.goal, plan.platform)
            text_reviewed = review_result.get("text_reviewed", text)
            score = review_result.get("score", 7.0)
            await broadcast(plan.niche_id, {"event": "agent_done", "agent": "reviewer"})

            await broadcast(plan.niche_id, {"event": "agent_start", "agent": "voice_adapter"})
            voice = VoiceAdapter()
            text_voiced = await voice.adapt(db, plan.niche_id, text_reviewed, niche.about_user or '', niche.tone_of_voice)
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
                plan_id=plan_id,
                text=text,
                text_reviewed=text_voiced,
                image_url=visual_result.get("image_url"),
                image_prompt=visual_result.get("image_prompt"),
                score=score,
                platform_versions=platform_versions
            )
            db.add(content)
            plan.status = "generated"
            await db.commit()
            await broadcast(plan.niche_id, {"event": "pipeline_complete"})

nexus_core = NexusCore()
