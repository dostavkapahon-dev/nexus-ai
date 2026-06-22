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
    """Шаг 1+2: анализ + план через AI (работает и на Gemini)."""
    from core.ai_router import ai_router
    hint = f"Тема задана пользователем: {topic}." if topic else "Тему выбери сам по трендам ниши."
    prompt = _ANALYSIS_PROMPT.format(topic_hint=hint)
    try:
        result = await ai_router.call("claude-sonnet-4-6", system_prompt(), prompt)
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
                      dry_run: bool = True, want_video: bool = True) -> dict:
    """Полный цикл. dry_run=True — всё генерируем, но НЕ публикуем."""
    platforms = platforms or DEFAULT_PLATFORMS
    report = {"steps": [], "assets": {}, "published": {}, "dry_run": dry_run}

    # 1-2. Анализ + план
    plan = await _analyze(topic)
    report["plan"] = plan
    report["steps"].append({"step": "analysis", "ok": True, "theme": plan.get("theme")})

    # 3a. Обложка (Imagen → fallback)
    try:
        from core.media_generator import generate_image
        img_prompt = cover_prompt(plan.get("hook_text", plan.get("theme", "")))
        cover = await generate_image(plan.get("image_prompt", img_prompt), platform="instagram")
        report["assets"]["cover"] = cover
        report["steps"].append({"step": "cover", "ok": bool(cover)})
    except Exception as e:
        cover = ""
        report["steps"].append({"step": "cover", "ok": False, "error": str(e)[:160]})

    # 3b. Видео (HeyGen аватар → HiggsField → Runway)
    if want_video:
        try:
            from core.media_generator import generate_clip
            vid = await generate_clip(prompt=plan.get("image_prompt", ""),
                                      script=plan.get("avatar_script", ""), provider="auto")
            report["assets"]["video"] = vid
            report["steps"].append({"step": "video", "ok": vid.get("ok", False),
                                    "provider": vid.get("provider"), "error": vid.get("error")})
        except Exception as e:
            report["steps"].append({"step": "video", "ok": False, "error": str(e)[:160]})

    # 4. Публикация по площадкам
    if not dry_run:
        from core.orchestrator import nexus_core
        for pf in platforms:
            text = _caption_for(pf, plan)
            try:
                res = await nexus_core._publish_one(pf, text, cover)
                report["published"][pf] = res
            except Exception as e:
                report["published"][pf] = {"ok": False, "error": str(e)[:160]}
    else:
        report["published"] = {pf: {"ok": None, "note": "dry-run, не публиковалось"} for pf in platforms}

    # 5. Отчёт в Telegram
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
        lines = [f"🏭 <b>Фабрика контента{' (dry-run)' if report['dry_run'] else ''}</b>",
                 f"🎯 Тема: {plan.get('theme', '—')}",
                 f"🪝 Хук ({plan.get('hook_type', '?')}): {plan.get('hook_text', '—')}", ""]
        for s in report["steps"]:
            mark = "✅" if s.get("ok") else "⚠️"
            extra = f" [{s.get('provider')}]" if s.get("provider") else ""
            lines.append(f"{mark} {s['step']}{extra}")
        if not report["dry_run"]:
            lines.append("")
            for pf, r in report["published"].items():
                lines.append(f"{'✅' if r.get('ok') else '⚠️'} {pf}")
        await send_message(chat_id, "\n".join(lines))
    except Exception:
        pass
