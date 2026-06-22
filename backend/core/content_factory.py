"""
CONTENT FACTORY — единый конвейер Pakhon Studio.
================================================
Один запуск = полный цикл «как AI-маркетолог»:
  1. АНАЛИЗ (вирусная механика, хук, тема дня) — бренд-мозг + AI
  2. ПЛАН под IG Reel / YT Short / TikTok / Telegram (единая тема, свои хуки)
  3. ГЕНЕРАЦИЯ: текст (Gemini/Claude), обложка (Imagen), видео (HeyGen→HiggsField→Runway),
     скрипт озвучки для аватара
  4. ПУБЛИКАЦИЯ на площадки (API где есть токен, иначе браузерный агент)
  5. ОТЧЁТ в Telegram владельцу

Работает на бесплатном Gemini (через ai_router fallback). Любая нехватка
ключа/площадки не валит весь цикл — логируется и продолжаем.
"""
import os
import json

from core.brand import system_prompt, cover_prompt, PLATFORM_SPECS

# Платформы по умолчанию
DEFAULT_PLATFORMS = ["instagram", "youtube", "tiktok", "telegram"]

# Мозг-аналитик и креативный контроль — Claude. Помощники: Perplexity (поиск
# трендов в реальном времени) и Gemini (резерв). Claude всё видит и решает.
BRAIN_MODEL = "claude-sonnet-4-6"
TREND_HELPER_MODEL = "sonar-pro"  # Perplexity; при отсутствии ключа ai_router сам уйдёт в фолбэк


async def _research_trends(topic: str | None) -> str:
    """Помощник ищет актуальные тренды (реальный поиск через Perplexity)."""
    from core.ai_router import ai_router
    q = (f"Найди 5 свежих вирусных трендов в нише AI/digital бизнес "
         f"{'по теме: ' + topic if topic else 'в Instagram Reels и YouTube Shorts на этой неделе'}. "
         f"Учитывай Казахстан/СНГ. Кратко: тема + почему залетает.")
    try:
        res = await ai_router.call(TREND_HELPER_MODEL,
                                   "Ты ассистент-аналитик трендов. Отвечай кратко, по делу.", q)
        return res.get("text", "")[:1500]
    except Exception:
        return ""

_ANALYSIS_PROMPT = """\
Ты — AI-маркетолог Pakhon Studio. Придумай ОДНУ тему дня для ниши AI/digital
бизнес (Казахстан/СНГ) и распиши её так, чтобы Reels ЗАЛЕТЕЛ.
{topic_hint}

Верни СТРОГО JSON (без markdown):
{{
  "theme": "тема дня одной фразой",
  "angle": "под каким углом подаём",
  "hook_type": "провокация|цифра|боль|тайна",
  "hook_text": "текстовый оверлей для первых 3 сек, крупно, до 7 слов",
  "avatar_script": "скрипт озвучки 15-25 сек, разговорно, короткие предложения, [пауза 0.5s] где нужно",
  "image_prompt": "англоязычный промпт для обложки (сцена, без текста)",
  "instagram": {{"caption": "подпись + 1 CTA", "hashtags": ["#..", "#.."]}},
  "youtube": {{"title": "до 60 симв с keyword", "description": "первые 2 строки keyword+CTA"}},
  "tiktok": {{"caption": "короткая подпись + хэштеги"}},
  "telegram": {{"post": "🔥 ХУК\\n\\nтело 3-5 абзацев\\n\\n👉 CTA\\n\\n#теги"}}
}}
Хэштеги Instagram: 5-8 шт, микс популярных и нишевых. Конкретика вместо абстракции.
"""


async def _analyze(topic: str | None) -> dict:
    """Шаг 1+2: помощник ищет тренды → Claude (мозг) делает анализ + план."""
    from core.ai_router import ai_router
    trends = await _research_trends(topic)
    hint = f"Тема задана пользователем: {topic}." if topic else "Тему выбери сам по трендам ниши."
    if trends:
        hint += f"\n\nСВЕЖИЕ ТРЕНДЫ (от ассистента, учти их):\n{trends}"
    prompt = _ANALYSIS_PROMPT.format(topic_hint=hint)
    try:
        result = await ai_router.call(BRAIN_MODEL, system_prompt(), prompt)
        raw = result.get("text", "")
    except Exception as e:
        return {"theme": topic or "AI для бизнеса", "hook_type": "тайна",
                "hook_text": "Смотри до конца", "avatar_script": "",
                "image_prompt": "dark cinematic AI tech poster, gold neon accents",
                "instagram": {"caption": "", "hashtags": ["#ai", "#бизнес"]},
                "youtube": {"title": topic or "AI", "description": ""},
                "tiktok": {"caption": ""}, "telegram": {"post": ""},
                "_error": f"Нет AI-ключа для анализа: {str(e)[:120]}. Добавь GEMINI_API_KEY."}
    try:
        s, e = raw.find("{"), raw.rfind("}") + 1
        return json.loads(raw[s:e])
    except Exception:
        return {"theme": topic or "AI для бизнеса", "hook_text": "Смотри до конца",
                "avatar_script": raw[:500], "image_prompt": "dark cinematic AI tech poster",
                "instagram": {"caption": raw[:300], "hashtags": ["#ai", "#бизнес"]},
                "youtube": {"title": topic or "AI", "description": raw[:200]},
                "tiktok": {"caption": raw[:150]}, "telegram": {"post": raw[:500]}}


async def run_factory(topic: str | None = None, platforms: list | None = None,
                      dry_run: bool = True, want_video: bool = True,
                      content_type: str = "auto") -> dict:
    """Полный цикл «креативный директор». dry_run=True — генерируем, не публикуем."""
    from core.creative_director import build_brief, choose_strategy, wow_review
    platforms = platforms or DEFAULT_PLATFORMS
    report = {"steps": [], "assets": {}, "published": {}, "dry_run": dry_run}

    # 1-2. Анализ + план (AI-маркетолог)
    plan = await _analyze(topic)
    report["plan"] = plan
    report["steps"].append({"step": "analysis", "ok": "_error" not in plan, "theme": plan.get("theme")})

    # 2b. Продакшен-ТЗ с раскадровкой и промтами (креативный директор)
    brief = await build_brief(plan)
    report["brief"] = brief
    report["steps"].append({"step": "brief", "ok": "_error" not in brief,
                            "shots": len(brief.get("storyboard", []))})

    # 2c. Выбор самой дешёвой рабочей стратегии видео
    strategy = choose_strategy(content_type)
    report["strategy"] = strategy
    report["steps"].append({"step": "strategy", "ok": True,
                            "choice": strategy["strategy"], "est_cost": strategy["est_cost"]})

    from core.media_generator import generate_image, generate_clip

    # 3a. Обложка
    try:
        cover = await generate_image(brief.get("cover_prompt") or plan.get("image_prompt")
                                     or cover_prompt(plan.get("hook_text", "")), platform="instagram")
        report["assets"]["cover"] = cover
        report["steps"].append({"step": "cover", "ok": bool(cover)})
    except Exception as e:
        cover = ""
        report["steps"].append({"step": "cover", "ok": False, "error": str(e)[:160]})

    # 3b. Раскадровка по кадрам (фото — дёшево/безлимит)
    frames = []
    for shot in brief.get("storyboard", [])[:4]:
        try:
            f = await generate_image(shot.get("image_prompt", ""), platform="instagram")
            if f:
                frames.append({"t": shot.get("t"), "overlay": shot.get("overlay"), "image": f})
        except Exception:
            pass
    report["assets"]["frames"] = frames
    report["steps"].append({"step": "storyboard_frames", "ok": True, "count": len(frames)})

    # 3c. Видео по выбранной стратегии
    if want_video:
        vid = {"ok": False}
        st = strategy["strategy"]
        first_img = frames[0]["image"] if frames else cover
        try:
            if st == "heygen_avatar":
                vid = await generate_clip(script=brief.get("avatar_script", ""), provider="heygen")
            elif st == "storyboard_to_higgsfield":
                vid = await generate_clip(prompt=brief.get("video_motion_prompt", ""),
                                          image_url=first_img, provider="higgsfield")
            elif st == "runway":
                vid = await generate_clip(prompt=brief.get("video_motion_prompt", ""),
                                          image_url=first_img, provider="runway")
            else:  # free_slideshow → ffmpeg-монтаж готового mp4
                from core.video_assembly import assemble_slideshow
                fr = frames or ([{"image": cover, "overlay": plan.get("hook_text", ""), "t": "0-4"}] if cover else [])
                vid = await assemble_slideshow(fr, cta_text=plan.get("instagram", {}).get("caption", "Pakhon Studio")[:40])
        except Exception as e:
            vid = {"ok": False, "error": str(e)[:160]}
        report["assets"]["video"] = vid
        report["steps"].append({"step": "video", "ok": vid.get("ok", False),
                                "provider": vid.get("provider"), "error": vid.get("error")})

    # 4. «Вау»-ревью: усиливаем хук при низкой оценке
    wow = await wow_review(brief)
    report["wow"] = wow
    if wow.get("score", 7) < 8 and wow.get("new_hook"):
        plan["hook_text"] = wow["new_hook"]
    report["steps"].append({"step": "wow_review", "ok": True, "score": wow.get("score")})

    # 5. Публикация
    if not dry_run:
        from core.orchestrator import nexus_core
        for pf in platforms:
            text = _caption_for(pf, plan)
            try:
                report["published"][pf] = await nexus_core._publish_one(pf, text, cover)
            except Exception as e:
                report["published"][pf] = {"ok": False, "error": str(e)[:160]}
    else:
        report["published"] = {pf: {"ok": None, "note": "dry-run"} for pf in platforms}

    # 6. Отчёт в Telegram
    await _send_report(report, platforms)
    return report


def _caption_for(platform: str, plan: dict) -> str:
    """Достаёт пер-платформенный текст из плана."""
    if platform == "instagram":
        ig = plan.get("instagram", {})
        tags = " ".join(ig.get("hashtags", [])) if isinstance(ig.get("hashtags"), list) else ""
        return (ig.get("caption", "") + "\n\n" + tags).strip()
    if platform == "youtube":
        yt = plan.get("youtube", {})
        return (yt.get("title", "") + "\n\n" + yt.get("description", "")).strip()
    if platform == "tiktok":
        return plan.get("tiktok", {}).get("caption", "")
    if platform == "telegram":
        return plan.get("telegram", {}).get("post", "")
    return plan.get("theme", "")


async def _send_report(report: dict, platforms: list) -> None:
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not chat_id:
        return
    try:
        from core.telegram_bot import send_message
        plan = report.get("plan", {})
        strat = report.get("strategy", {})
        wow = report.get("wow", {})
        lines = [f"🏭 <b>Фабрика контента{' (превью)' if report['dry_run'] else ''}</b>",
                 f"🎯 Тема: {plan.get('theme', '—')}",
                 f"🪝 Хук ({plan.get('hook_type', '?')}): {plan.get('hook_text', '—')}",
                 f"🎬 Стратегия: {strat.get('strategy', '—')} (~${strat.get('est_cost', 0)})",
                 f"⭐ Вау-оценка: {wow.get('score', '—')}/10", ""]
        for s in report["steps"]:
            mark = "✅" if s.get("ok") else "⚠️"
            extra = f" [{s.get('provider')}]" if s.get("provider") else ""
            extra += f" x{s.get('count')}" if s.get("count") else ""
            lines.append(f"{mark} {s['step']}{extra}")
        if not report["dry_run"]:
            lines.append("")
            for pf, r in report["published"].items():
                lines.append(f"{'✅' if r.get('ok') else '⚠️'} {pf}")
        await send_message(chat_id, "\n".join(lines))
    except Exception:
        pass
