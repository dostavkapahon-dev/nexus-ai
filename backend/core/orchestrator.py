import os
import json
from datetime import datetime
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

                # Досье аккаунта (бесплатно, без сторонних сервисов: yt-dlp +
                # опц. Bright Data) — чтобы бот планировал контент на реальных
                # данных, а не вслепую.
                account_intel = None
                try:
                    from core.social_intel import is_configured as intel_ready, get_account_intelligence
                    if await intel_ready():
                        ig_platforms = [p for p in (niche.platforms or []) if p in
                                        ("instagram", "tiktok", "youtube")]
                        account_intel = await get_account_intelligence(ig_platforms or ["instagram"])
                        await broadcast(niche_id, {"event": "account_intel", "data": bool(account_intel)})
                except Exception:
                    account_intel = None

                await broadcast(niche_id, {"event": "agent_start", "agent": "viral_hunter"})
                hunter = ViralHunter()
                viral_data = await hunter.hunt(db, niche_id, niche.name, niche.platforms or ["telegram"], niche_profile.get("audience", {}), account_intel)
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
                    analysis_data={"niche_profile": niche_profile, "viral_data": viral_data, "account_intel": account_intel}
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

            # Если пользователь выбрал стратегию в Telegram (/strategy) — учитываем её.
            try:
                from core.strategy_advisor import get_chosen
                chosen = await get_chosen(db)
                if chosen:
                    viral_data = {**(viral_data or {}), "chosen_strategy": chosen}
            except Exception:
                pass

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

    async def generate_content_for_plan(self, plan_id: str, corrections: str = None):
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(ContentPlan).where(ContentPlan.id == plan_id))
            plan = result.scalar_one_or_none()
            if not plan:
                return

            niche_result = await db.execute(select(Niche).where(Niche.id == plan.niche_id))
            niche = niche_result.scalar_one_or_none()
            if not niche:
                return

            # Если пришли правки от админа — учитываем их в задании копирайтеру.
            hook = plan.hook or ""
            if corrections:
                hook = f"{hook}\n\nУчти правки: {corrections}"

            await broadcast(plan.niche_id, {"event": "agent_start", "agent": "copywriter"})
            copywriter = Copywriter()
            text = await copywriter.write(db, plan.niche_id, niche.name, plan.topic, hook, niche.tone_of_voice, plan.platform, niche.goal)
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
            plan.status = "awaiting_approval"
            await db.commit()
            await broadcast(plan.niche_id, {"event": "pipeline_complete"})

            # На согласование в Telegram перед публикацией.
            try:
                from core.moderation import send_for_approval
                await send_for_approval(
                    text_voiced, media_url=visual_result.get("image_url"),
                    platforms=(niche.platforms or ["instagram"]),
                    kind="plan", ref=plan_id,
                )
            except Exception:
                pass

    async def publish_plan(self, plan_id: str):
        """Publish a generated plan item to all configured platforms.

        Использует пер-платформенный текст (platform_versions), официальные API
        где есть токен, и браузерного агента как fallback. Возвращает отчёт.
        """
        async with AsyncSessionLocal() as db:
            from database.models import Publication
            result = await db.execute(select(ContentPlan).where(ContentPlan.id == plan_id))
            plan = result.scalar_one_or_none()
            if not plan:
                return {"ok": False, "error": "plan not found"}

            niche_r = await db.execute(select(Niche).where(Niche.id == plan.niche_id))
            niche = niche_r.scalar_one_or_none()
            if not niche:
                return {"ok": False, "error": "niche not found"}

            content_r = await db.execute(
                select(GeneratedContent).where(GeneratedContent.plan_id == plan_id).limit(1)
            )
            content = content_r.scalar_one_or_none()
            if not content:
                raise ValueError("Content not generated yet")

            base_text = content.text_reviewed or content.text or ""
            image_url = content.image_url or ""
            versions = content.platform_versions or {}
            platforms = niche.platforms or ["telegram"]

            # Под какой стратегией выходят посты — чтобы потом сравнить результат.
            strategy_id = ""
            try:
                from core.strategy_store import current as current_strategy
                cur = await current_strategy(plan.niche_id)
                strategy_id = cur["id"] if cur else ""
            except Exception:
                pass

            report = {}
            for platform in platforms:
                text = versions.get(platform) or base_text
                try:
                    res = await self._publish_one(platform, text, image_url)
                except Exception as e:
                    res = {"ok": False, "error": str(e)}
                report[platform] = res
                # Разовый сетевой сбой не должен означать потерянный пост: неудачная
                # публикация остаётся в очереди с текстом и картинкой, и джоб повторит её.
                # Отказ по существу (нет прав/токена) повторять бессмысленно — BLOCKED.
                from core.publish_queue import (PUBLISHED, RETRYING, BLOCKED,
                                                _is_permanent, _backoff)
                from core.cost_tracker import current_task_id
                if res.get("ok"):
                    status, next_retry = PUBLISHED, None
                elif _is_permanent(res):
                    status, next_retry = BLOCKED, None
                else:
                    status, next_retry = RETRYING, datetime.utcnow() + _backoff(1)
                    report[platform] = {**res, "queued_retry": True}

                # Сохраняем не только факт, но и ЧТО опубликовали: тему, хук и формат.
                # Без этого позже невозможно связать результат с приёмом.
                db.add(Publication(
                    plan_id=plan_id, niche_id=plan.niche_id, platform=platform, status=status,
                    external_id=str(res.get("post_id") or ""),
                    post_url=str(res.get("post_url") or ""),
                    topic=(plan.topic or "")[:300], hook=plan.hook or "",
                    content_format=plan.format or "", strategy_id=strategy_id,
                    attempts=1, next_retry_at=next_retry,
                    last_error=None if res.get("ok") else
                        str(res.get("error") or res.get("reason") or "")[:500],
                    text=text, image_url=image_url,
                    task_id=current_task_id.get()))
                await broadcast(plan.niche_id, {"event": "publish_result", "platform": platform, "result": res})

            plan.status = "published" if any(r.get("ok") for r in report.values()) else "generated"
            await db.commit()
            return {"ok": True, "report": report}

    async def _publish_one(self, platform: str, text: str, image_url: str) -> dict:
        """Публикация одной площадки через её коннектор.

        Раньше здесь была лестница if-ов по каждой площадке. Теперь все площадки
        реализуют один контракт (`connectors/base.py::SocialConnector`), поэтому
        маршрутизация одинаковая: коннектор → при отказе браузерный путь.

        Режим NEXUS_PUBLISH_MODE: browser — всё через браузер без API;
        api — только официальные API; auto — API если настроен, иначе браузер.
        """
        from publishers.browser_publish import publish_via_browser
        from connectors import get_connector

        mode = os.getenv("NEXUS_PUBLISH_MODE", "auto").strip().lower()

        # Telegram — свой бот, а не «API площадки»: его не подменяем браузером.
        if mode == "browser" and platform != "telegram":
            return await publish_via_browser(platform, text, image_url)

        connector = get_connector(platform)
        if connector and connector.configured():
            try:
                res = await connector.publish(text, image_url=image_url or "")
            except Exception as e:
                res = {"ok": False, "error": str(e)[:300]}

            if res.get("ok"):
                return res
            # Ограничение платформы или сбой API — уходим в браузер, но
            # сохраняем исходную причину, чтобы она не потерялась в отчёте.
            if mode == "api":
                return res
            browser = await publish_via_browser(platform, text, image_url)
            if browser.get("ok"):
                return {**browser, "api_note": res.get("reason") or res.get("error")}
            return {"ok": False, "platform": platform,
                    "error": res.get("reason") or res.get("error") or "публикация не удалась",
                    "blocked_by_api": res.get("blocked_by_api", False),
                    "fallback_error": browser.get("error")}

        # Telegram — свой бот, а не «API площадки». Браузерного сценария для него нет
        # и быть не должно: без токена это «не настроено», а не повод лезть в браузер.
        # Иначе наверх уходило «нет браузерного сценария» — причина не та, и очередь
        # пять раз повторяла заведомо безнадёжную публикацию.
        if mode == "api" or platform == "telegram":
            missing = connector.missing_env() if connector else []
            return {"ok": False, "platform": platform,
                    "error": "площадка не настроена" + (f": не заданы {', '.join(missing)}" if missing else "")}

        # Токенов нет — публикуем через браузер (без API).
        return await publish_via_browser(platform, text, image_url)


nexus_core = NexusCore()