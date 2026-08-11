"""
Виральная разведка — анализ чужих залетевших роликов в YouTube / TikTok / Instagram.

Что делает:
  • тянет метрики ролика по ссылке (просмотры, лайки, длительность, автор) — yt-dlp;
  • ищет топ по нише в YouTube (по просмотрам);
  • «смотрит» сам ролик (кадры → vision) и разбирает хук/динамику;
  • по нескольким референсам LLM выжимает «рецепт вируса» (хук, структура, темп,
    форматы, темы), который сохраняется и подмешивается в генерацию.

yt-dlp работает для YouTube надёжно; TikTok обычно тоже; Instagram часто требует
логина — тогда возвращаем что смогли (хотя бы метрики/деградация без падения).
"""
import json
import asyncio

from sqlalchemy import select
from database.db import AsyncSessionLocal
from database.models import Connection
from core.ai_router import ai_router, ECONOMY_MODELS

RECIPE_KEY = "viral_recipe"


def _ydl_opts(download: bool = False, outtmpl: str = None) -> dict:
    opts = {"quiet": True, "no_warnings": True, "skip_download": not download,
            "noplaylist": True, "extract_flat": False}
    if outtmpl:
        opts["outtmpl"] = outtmpl
        opts["format"] = "mp4/best[height<=720]"
    return opts


def _extract(url: str, download: bool = False, outtmpl: str = None) -> dict:
    import yt_dlp
    with yt_dlp.YoutubeDL(_ydl_opts(download, outtmpl)) as ydl:
        return ydl.extract_info(url, download=download)


def _meta_from(info: dict) -> dict:
    return {
        "title": info.get("title"),
        "views": info.get("view_count"),
        "likes": info.get("like_count"),
        "comments": info.get("comment_count"),
        "duration": info.get("duration"),
        "uploader": info.get("uploader") or info.get("channel"),
        "platform": info.get("extractor_key") or info.get("extractor"),
        "url": info.get("webpage_url") or info.get("original_url"),
        "thumbnail": info.get("thumbnail"),
        "description": (info.get("description") or "")[:500],
    }


async def fetch_meta(url: str) -> dict:
    """Метрики ролика по ссылке (без скачивания)."""
    try:
        info = await asyncio.to_thread(_extract, url, False, None)
        return {"ok": True, **_meta_from(info)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:150], "url": url}


async def youtube_search(query: str, n: int = 8) -> list[dict]:
    """Топ роликов YouTube по нише, отсортированные по просмотрам."""
    try:
        info = await asyncio.to_thread(_extract, f"ytsearch{n}:{query}", False, None)
        entries = info.get("entries", []) or []
        metas = [_meta_from(e) for e in entries if e]
        metas.sort(key=lambda m: (m.get("views") or 0), reverse=True)
        return metas
    except Exception:
        return []


async def analyze_reference(url: str, with_vision: bool = True) -> dict:
    """Метрики + визуальный разбор одного референса (скачиваем и смотрим кадры)."""
    meta = await fetch_meta(url)
    # Без API: если yt-dlp не смог (Instagram/логин), добираем метрики браузером.
    if not meta.get("ok"):
        try:
            from core import browser_reader
            if browser_reader.enabled():
                b = await browser_reader.analyze_post(url)
                if b.get("ok"):
                    meta = {"ok": True, "title": b.get("title"), "views": b.get("views"),
                            "likes": b.get("likes"), "comments": b.get("comments"),
                            "uploader": b.get("author"), "url": url, "source": "browser"}
        except Exception:
            pass
    out = {"meta": meta}
    if with_vision and meta.get("ok"):
        try:
            from core.vision import analyze_video, analyze_image
            # Пытаемся разобрать сам ролик; если не качается — хотя бы обложку.
            v = await analyze_video(meta["url"], frames=3)
            if not v.get("ok") and meta.get("thumbnail"):
                v = await analyze_image(meta["thumbnail"])
            out["vision"] = v.get("analysis") if v.get("ok") else v.get("error")
        except Exception as e:
            out["vision"] = f"vision error: {str(e)[:120]}"
    return out


async def _save_recipe(recipe: dict):
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Connection).where(Connection.key_name == RECIPE_KEY))
        c = r.scalar_one_or_none()
        payload = json.dumps(recipe, ensure_ascii=False)
        if c:
            c.key_value = payload
        else:
            db.add(Connection(key_name=RECIPE_KEY, key_value=payload))
        await db.commit()


async def get_recipe() -> dict | None:
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Connection).where(Connection.key_name == RECIPE_KEY))
        c = r.scalar_one_or_none()
    if c and c.key_value:
        try:
            return json.loads(c.key_value)
        except Exception:
            return None
    return None


async def research(urls: list[str], niche: str = "") -> dict:
    """Разбирает несколько референсов и выжимает «рецепт вируса». Сохраняет его."""
    refs = []
    for u in urls[:5]:
        refs.append(await analyze_reference(u, with_vision=True))

    context = json.dumps(refs, ensure_ascii=False)[:8000]
    system = ("Ты аналитик вирусного контента. По разбору чужих залетевших роликов "
              "(метрики + что в кадре) выведи, ПОЧЕМУ они зашли, и дай рецепт. JSON, кратко.")
    prompt = (
        f"Ниша: {niche or '—'}\n"
        f"Разбор референсов (метрики + визуальный анализ):\n{context}\n\n"
        "Верни JSON:\n"
        '{"why_viral": ["причина", ...], "hook_patterns": ["..."], '
        '"structure": "структура ролика по секундам", "pacing": "темп/склейки", '
        '"topics": ["тема", ...], "recipe": "как собрать наш ролик чтобы залетел"}'
    )
    model = ECONOMY_MODELS.get("viral_hunter", "gemini-1.5-flash")
    try:
        res = await ai_router.call(model, system, prompt)
        text = res.get("text", "")
        s, e = text.find("{"), text.rfind("}") + 1
        recipe = json.loads(text[s:e])
    except Exception as ex:
        recipe = {"why_viral": [], "recipe": f"(не удалось разобрать: {str(ex)[:100]})"}

    # Разбор чужих роликов — лучший источник уроков: сохраняем в память агента,
    # чтобы находки применялись и в следующих задачах, а не жили один раз.
    try:
        from core.skills_store import learn_from
        await learn_from(json.dumps(recipe, ensure_ascii=False)[:4000],
                         source="viral_research")
    except Exception:
        pass

    recipe["_refs"] = [r["meta"] for r in refs]
    await _save_recipe(recipe)

    # История исследований: KV-ключ хранит только последний рецепт и перезатирается,
    # а здесь остаётся вся хронология с привязкой к нише и задаче.
    try:
        from core.research_store import save as save_research
        await save_research(
            kind="viral", query=" ".join(urls[:5])[:500],
            summary=str(recipe.get("recipe", ""))[:2000],
            findings={k: v for k, v in recipe.items() if k != "_refs"},
            sources=[r["meta"].get("url") for r in refs if r.get("meta")])
    except Exception:
        pass
    return recipe
