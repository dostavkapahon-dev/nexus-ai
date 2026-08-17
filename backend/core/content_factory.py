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

# Шаги, без которых результат конвейера бессмысленен. Провал остальных
# (видео, монтаж) оставляет годный текст + обложку — это ещё успех.
CRITICAL_STEPS = ("analysis", "brief")

# Мозг-аналитик и креативный контроль — Claude. Помощники: Perplexity (поиск
# трендов в реальном времени) и Gemini (резерв). Claude всё видит и решает.
BRAIN_MODEL = "claude-sonnet-4-6"
TREND_HELPER_MODEL = "sonar-pro"  # Perplexity; при отсутствии ключа ai_router сам уйдёт в фолбэк


async def _research_trends(topic: str | None) -> str:
    """Свежие тренды из интернета перед созданием контента.

    Раньше это работало только с ключом Perplexity, иначе фабрика придумывала
    тему вслепую. Теперь идём через общий поиск: с ключом — живой поиск, без
    ключа — бесплатный источник, и тема опирается хоть на какие-то факты.
    """
    from core.agent_profile import get as get_profile
    from core.websearch import search

    niche = ""
    try:
        niche = (await get_profile()).get("niche") or ""
    except Exception:
        pass
    q = (f"вирусные тренды {niche or 'AI digital бизнес'} "
         f"{topic or 'Reels Shorts на этой неделе'}").strip()
    try:
        found = await search(q, max_results=5)
    except Exception:
        return ""
    items = found.get("items") or []
    return "\n".join(f"- {i['title']}: {i.get('snippet', '')}" for i in items)[:1500]

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
    from core.hooks import guidance, record
    g = guidance()
    trends = await _research_trends(topic)
    hint = f"Тема задана пользователем: {topic}." if topic else "Тему выбери сам по трендам ниши."
    hint += (f"\n\nУКАЗАНИЯ МАРКЕТОЛОГА НА СЕГОДНЯ (соблюдай):\n"
             f"- Тема дня: {g['day_theme']}\n"
             f"- Тип хука (ротация, НЕ повторяй {g['avoid_hook_types']}): {g['hook_type']}\n"
             f"- Формулы хука на выбор: {g['hook_formulas']}\n"
             f"- Формат ролика: {g['format']}\n"
             f"- Столп 80/20: {'ПРОМО услуг' if g['pillar']=='promo' else 'ЦЕННОСТЬ/обучение'}")
    if trends:
        hint += f"\n\nСВЕЖИЕ ТРЕНДЫ (от ассистента, учти их):\n{trends}"
    prompt = _ANALYSIS_PROMPT.format(topic_hint=hint)
    try:
        result = await ai_router.call(BRAIN_MODEL, await system_prompt(), prompt)
        raw = result.get("text", "")
    except Exception as e:
        # Моделей нет — но пустая заглушка «AI для бизнеса» хуже, чем осмысленная
        # заготовка по заданной теме: её видно, её можно доработать руками.
        from core.offline_content import draft
        d = draft(topic or "ваша тема")
        caption = d["caption"]
        return {"theme": d["theme"], "hook_type": g["hook_type"],
                "hook_text": d["hook_text"], "avatar_script": caption,
                "image_prompt": d["cover_prompt"], "_format": g["format"],
                "instagram": {"caption": caption, "hashtags": ["#ai", "#бизнес"]},
                "youtube": {"title": d["theme"], "description": caption},
                "tiktok": {"caption": caption[:150]}, "telegram": {"post": caption},
                "_offline": True,
                "_error": f"Модели недоступны ({str(e)[:100]}). Собрал заготовку "
                          f"без ИИ — текст стоит доработать."}
    try:
        s, e = raw.find("{"), raw.rfind("}") + 1
        data = json.loads(raw[s:e])
        data.setdefault("hook_type", g["hook_type"])
        data["_format"] = g["format"]
        record(g["hook_type"], g["format"], g["day_theme"])  # контроль ротации
        return data
    except Exception:
        return {"theme": topic or "AI для бизнеса", "hook_text": "Смотри до конца",
                "hook_type": g["hook_type"], "_format": g["format"],
                "avatar_script": raw[:500], "image_prompt": "dark cinematic AI tech poster",
                "instagram": {"caption": raw[:300], "hashtags": ["#ai", "#бизнес"]},
                "youtube": {"title": topic or "AI", "description": raw[:200]},
                "tiktok": {"caption": raw[:150]}, "telegram": {"post": raw[:500]}}


async def _flush_steps(report: dict) -> None:
    """Переносит новые шаги конвейера в журнал текущей задачи.

    Раньше `report["steps"]` жил только в ответе и пропадал вместе с ним: по упавшей
    фабрике нельзя было понять, на каком шаге она сломалась. Переписывать 12 мест
    вызова рискованно, поэтому журналируем пачкой — шаги, добавленные с прошлого раза.
    Никогда не роняет конвейер: журнал не должен ломать основную работу.
    """
    try:
        from core.cost_tracker import current_task_id
        task_id = current_task_id.get()
        if not task_id:
            return
        from core.task_manager import add_step
        sent = int(report.get("_journaled") or 0)
        steps = report.get("steps") or []
        for s in steps[sent:]:
            await add_step(task_id, agent="factory", action=s.get("step", "step"),
                           ok=bool(s.get("ok")), error=str(s.get("error") or "")[:300])
        report["_journaled"] = len(steps)
    except Exception:
        pass


async def run_factory(topic: str | None = None, platforms: list | None = None,
                      dry_run: bool = True, want_video: bool = True,
                      content_type: str = "auto") -> dict:
    """Полный цикл «креативный директор». dry_run=True — генерируем, не публикуем."""
    from core.creative_director import build_brief, choose_strategy, wow_review
    platforms = platforms or DEFAULT_PLATFORMS
    report = {"steps": [], "assets": {}, "published": {}, "dry_run": dry_run}

    # 0. Рецепт вируса из разведки (/viral) — подмешиваем в тему, если есть.
    try:
        from core.viral_research import get_recipe
        recipe = await get_recipe()
        if recipe and recipe.get("recipe"):
            hint = f"{recipe.get('recipe','')} Хуки: {'; '.join(recipe.get('hook_patterns', [])[:3])}"
            topic = f"{topic or ''}\n\n[Рецепт залетевших роликов — используй: {hint}]".strip()
    except Exception:
        pass

    # 0а2. Действующая стратегия задаёт угол подачи — иначе каждый ролик сам по себе.
    try:
        from core.strategy_store import context as strategy_context
        sctx = await strategy_context()
        if sctx:
            topic = f"{topic or ''}\n\n[СТРАТЕГИЯ]\n{sctx}".strip()
    except Exception:
        pass

    # 0б. Самопроверка перед дорогой генерацией: агент уточняет задачу сам,
    #     чтобы не гонять тяжёлые модели вслепую (экономия токенов).
    try:
        from core.self_critique import pre_check
        chk = await pre_check("content_factory", topic or "выбрать тему по трендам",
                              context=str(platforms))
        if chk.get("improved_task") and topic:
            topic = chk["improved_task"][:2000]
        report["steps"].append({"step": "self_check", "ok": chk.get("checked", True),
                                "ready": chk.get("ready"), "missing": chk.get("missing", [])[:3],
                                "error": chk.get("error")})
    except Exception as e:
        report["steps"].append({"step": "self_check", "ok": False, "error": str(e)[:160]})

    # 0в. Память агента: что уже работало и что проваливалось. Дописываем
    #     в тему — модель не изобретает заново и не повторяет ошибок.
    try:
        from core.skills_store import context_for
        memory = context_for()
        if memory:
            topic = f"{topic or ''}\n\n[ПАМЯТЬ АГЕНТА]\n{memory}".strip()
    except Exception:
        pass

    # 1-2. Анализ + план (AI-маркетолог)
    plan = await _analyze(topic)
    report["plan"] = plan
    # Офлайн-заготовка — это не провал шага: контент есть, просто собран по
    # шаблону. Провал — когда на выходе пусто.
    report["offline"] = bool(plan.get("_offline"))
    report["steps"].append({"step": "analysis",
                            "ok": "_error" not in plan or plan.get("_offline", False),
                            "theme": plan.get("theme"),
                            "note": plan.get("_error") if plan.get("_offline") else None})

    # 2b. Продакшен-ТЗ с раскадровкой и промтами (креативный директор)
    brief = await build_brief(plan)
    report["brief"] = brief
    report["offline"] = report["offline"] or bool(brief.get("_offline"))
    report["steps"].append({"step": "brief",
                            "ok": bool(brief.get("storyboard")),   # пусто — вот это провал
                            "shots": len(brief.get("storyboard", [])),
                            "note": brief.get("_error") if brief.get("_offline") else None})

    # 2c. Выбор стратегии видео (формат из ротации: talking_head → HeyGen-аватар)
    ct = content_type if content_type != "auto" else plan.get("_format", "auto")
    strategy = choose_strategy(ct)
    report["strategy"] = strategy
    report["steps"].append({"step": "strategy", "ok": True,
                            "choice": strategy["strategy"], "est_cost": strategy["est_cost"]})

    await _flush_steps(report)   # анализ/бриф/стратегия — до дорогой генерации

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

    # 3b. Раскадровка по кадрам — БЕСПЛАТНО (Pollinations, безлимит, 0 токенов)
    from core.skills import free_image, higgsfield_reel
    frames = []
    for shot in brief.get("storyboard", [])[:4]:
        prompt_img = shot.get("image_prompt", "")
        if prompt_img:
            frames.append({"t": shot.get("t"), "overlay": shot.get("overlay"),
                           "image": free_image(prompt_img)})
    report["assets"]["frames"] = frames
    # Нет раскадровки → нет кадров: это не «успешный» шаг, а следствие сбоя брифа.
    report["steps"].append({"step": "storyboard_frames", "ok": bool(frames),
                            "count": len(frames)})

    await _flush_steps(report)   # обложка и кадры

    # 3c. Видео по выбранной стратегии
    if want_video:
        vid = {"ok": False}
        st = strategy["strategy"]
        first_img = frames[0]["image"] if frames else cover

        # Видео может делать не сервер: если производство отдано внешнему
        # исполнителю (Claude Code с доступом к Higgsfield), кладём ТЗ в очередь
        # и на этом останавливаемся. Дальше конвейер продолжится сам, когда
        # исполнитель вернёт готовый файл, — см. finalize_from_assets.
        from core.production_queue import producer, CLAUDE, enqueue
        if await producer() == CLAUDE:
            job_brief = {
                "theme": plan.get("theme"), "hook_text": plan.get("hook_text"),
                "tone": brief.get("tone") or plan.get("tone"),
                "cover_prompt": brief.get("cover_prompt") or plan.get("image_prompt"),
                "video_motion_prompt": brief.get("video_motion_prompt"),
                "avatar_script": brief.get("avatar_script"),
                "storyboard": brief.get("storyboard", []),
                "seed_image": first_img, "cover": cover,
                "platforms": platforms,
                "caption": _caption_for(platforms[0] if platforms else "instagram", plan),
                "strategy": st,
            }
            from core.cost_tracker import current_task_id
            job = await enqueue(job_brief, kind="reel", task_id=current_task_id.get() or "")
            report["production_job"] = job["id"]
            report["assets"]["video"] = {"ok": False, "awaiting_producer": True,
                                         "job_id": job["id"]}
            report["steps"].append({"step": "video", "ok": True,
                                    "provider": "внешний исполнитель",
                                    "note": f"ТЗ передано, задание {job['id']}"})
            report["awaiting_producer"] = True
            report["published"] = {"status": "awaiting_producer",
                                   "note": "ждём готовый ролик от исполнителя"}
            await _flush_steps(report)
            await _send_report(report, platforms)
            report.pop("_journaled", None)
            report["ok"] = True
            return report

        try:
            if st == "heygen_avatar":
                vid = await generate_clip(script=brief.get("avatar_script", ""), provider="heygen")
            elif st == "storyboard_to_higgsfield":
                # СКИЛЛ: бесплатный сид-кадр → анимация HiggsField (платим только за видео)
                vid = await higgsfield_reel(motion_prompt=brief.get("video_motion_prompt", ""),
                                            seed_image=first_img,
                                            fallback_image_prompt=brief.get("cover_prompt", ""))
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

        # 3d. Монтаж (Роль 3): караоке-субтитры из сценария + роялти-фри музыка.
        if vid.get("ok"):
            try:
                from core.video_editor import edit_reel, ensure_local_video
                local_v = await ensure_local_video(vid)
                if local_v:
                    script_for_subs = (brief.get("avatar_script")
                                       or plan.get("hook_text")
                                       or plan.get("instagram", {}).get("caption", ""))
                    edited = await edit_reel(local_v, script_text=script_for_subs,
                                             mood=brief.get("tone") or plan.get("tone"))
                    if edited.get("ok"):
                        vid = {**vid, **edited, "edited": True}
                        report["assets"]["video"] = vid
                    report["steps"].append({"step": "montage", "ok": edited.get("ok", False),
                                            "subtitles": edited.get("subtitles"),
                                            "music": edited.get("music"),
                                            "error": edited.get("error")})
            except Exception as e:
                report["steps"].append({"step": "montage", "ok": False, "error": str(e)[:160]})

    # 4. «Вау»-ревью: усиливаем хук при низкой оценке
    wow = await wow_review(brief)
    report["wow"] = wow
    if wow.get("score", 7) < 8 and wow.get("new_hook"):
        plan["hook_text"] = wow["new_hook"]
    report["steps"].append({"step": "wow_review", "ok": True, "score": wow.get("score")})

    await _flush_steps(report)   # видео, монтаж, вау-ревью

    # 5. Публикация — через согласование в Telegram (сначала превью, потом аппрув).
    if not dry_run:
        vid_url = vid.get("url") if isinstance(vid, dict) else None
        media = vid_url if (vid_url and str(vid_url).startswith("http")) else cover
        caption = _caption_for(platforms[0] if platforms else "instagram", plan)
        try:
            from core.moderation import send_for_approval
            pid = await send_for_approval(caption, media_url=media, platforms=platforms, kind="factory")
            report["published"] = {"status": "awaiting_approval", "pid": pid,
                                   "note": "ролик отправлен в Telegram на согласование"}
            # Точка согласования — это не «шаг провалился», а ожидание человека.
            report["steps"].append({"step": "approval_requested", "ok": True, "pid": pid})
            report["awaiting_approval"] = True
        except Exception as e:
            report["published"] = {"status": "error", "error": str(e)[:160]}
            report["steps"].append({"step": "approval_requested", "ok": False,
                                    "error": str(e)[:160]})
    else:
        report["published"] = {pf: {"ok": None, "note": "dry-run"} for pf in platforms}

    # 6б. Итог: конвейер «удался» только если прошли ключевые шаги. Иначе
    #      наверх уходил ok=true при полностью провалившейся генерации.
    failed = [s["step"] for s in report["steps"] if not s.get("ok")]
    report["failed_steps"] = failed
    report["ok"] = not [s for s in failed if s in CRITICAL_STEPS]
    if not report["ok"]:
        report["hint"] = ("Не прошли шаги: " + ", ".join(failed) +
                          ". Обычно причина — нет ключа ИИ: добавьте GEMINI_API_KEY "
                          "(бесплатно) или ANTHROPIC_API_KEY в Подключениях.")
    elif report.get("offline"):
        report["hint"] = ("Собрано без моделей ИИ: тексты и раскадровка — по "
                          "шаблону, картинки бесплатным генератором. Добавьте "
                          "бесплатный ключ (Groq или Gemini), и то же самое будет "
                          "писаться под вашу нишу.")

    await _flush_steps(report)   # публикация/согласование — последний кусок журнала
    report.pop("_journaled", None)   # служебный счётчик наружу не отдаём

    # 6. Отчёт в Telegram
    await _send_report(report, platforms)
    return report


async def finalize_from_assets(job: dict) -> dict:
    """Продолжает конвейер после того, как исполнитель вернул готовое медиа.

    Ровно те же шаги, что и во внутреннем пути: монтаж (караоке-субтитры +
    музыка) и согласование в Telegram. Публикацию сам не делает — её запускает
    владелец кнопкой, как и для роликов, собранных сервером.
    """
    brief = job.get("brief") or {}
    assets = job.get("assets") or {}
    video_url = assets.get("video_url") or ""
    media = video_url or assets.get("cover_url") or assets.get("image_url") or brief.get("cover")
    platforms = brief.get("platforms") or DEFAULT_PLATFORMS
    out = {"job_id": job.get("id"), "steps": []}

    # Монтаж: субтитры из сценария и музыка под настроение.
    if video_url:
        try:
            from core.video_editor import edit_reel, ensure_local_video
            local = await ensure_local_video({"ok": True, "url": video_url})
            if local:
                edited = await edit_reel(
                    local,
                    script_text=brief.get("avatar_script") or brief.get("hook_text") or "",
                    mood=brief.get("tone"))
                if edited.get("ok"):
                    media = edited.get("url") or media
                    out["edited"] = True
                out["steps"].append({"step": "montage", "ok": edited.get("ok", False),
                                     "error": edited.get("error")})
        except Exception as e:
            out["steps"].append({"step": "montage", "ok": False, "error": str(e)[:160]})

    caption = brief.get("caption") or brief.get("hook_text") or ""
    try:
        from core.moderation import send_for_approval
        pid = await send_for_approval(caption, media_url=media, platforms=platforms,
                                      kind="factory")
        out["status"] = "awaiting_approval" if pid else "no_telegram"
        out["pid"] = pid
        out["steps"].append({"step": "approval_requested", "ok": bool(pid)})
        if not pid:
            # Без Telegram согласовывать негде — говорим прямо, а не молчим.
            out["note"] = ("Telegram не подключён: ролик готов, но показать его "
                           "на согласование некому. Ссылка: " + str(media))
    except Exception as e:
        out["status"] = "error"
        out["error"] = str(e)[:200]
        out["steps"].append({"step": "approval_requested", "ok": False,
                             "error": str(e)[:160]})
    out["media"] = media
    return out


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
