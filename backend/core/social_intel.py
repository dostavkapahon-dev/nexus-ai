"""
Бесплатная разведка аккаунта — замена платного посредника Ayrshare.

Зачем: Ayrshare — сторонний сервис, и «досье аккаунта» зависело от того, включён
он у нас или нет. Здесь то же самое делается БЕСПЛАТНО и без внешнего сервиса:

  • YouTube / TikTok — публичные метрики канала и последних роликов тянутся через
    yt-dlp (та же библиотека, что и в viral_research) — просмотры, лайки, длина;
  • Instagram — обычно требует логина, поэтому берётся через Bright Data
    (Web Unlocker), если задан BRIGHTDATA_API_KEY; иначе честно деградируем.

Ручки (никнеймы) аккаунта берутся из БД/окружения:
  IG_HANDLE, TIKTOK_HANDLE, YOUTUBE_HANDLE  (можно с @ или без).

Интерфейс намеренно совпадает со старым ayrshare_pub, чтобы оркестратор,
автопилот и стратег продолжали работать без изменений в логике:
  is_configured(), get_account_intelligence(platforms).
"""
import os
import asyncio
import json

import httpx
from sqlalchemy import select

from database.db import AsyncSessionLocal
from database.models import Connection

_HANDLE_KEYS = {
    "instagram": "ig_handle",
    "tiktok": "tiktok_handle",
    "youtube": "youtube_handle",
}


async def _conn(key: str) -> str:
    """Значение из БД (настройки сайта) с фолбэком на переменную окружения."""
    try:
        async with AsyncSessionLocal() as db:
            r = await db.execute(select(Connection).where(Connection.key_name == key))
            c = r.scalar_one_or_none()
            if c and c.key_value:
                return c.key_value.strip()
    except Exception:
        pass
    return os.getenv(key.upper(), "").strip()


async def _handle(platform: str) -> str:
    key = _HANDLE_KEYS.get(platform)
    if not key:
        return ""
    return (await _conn(key)).lstrip("@").strip()


def _brightdata_key() -> str:
    return os.getenv("BRIGHTDATA_API_KEY", "").strip()


async def is_configured() -> bool:
    """Есть ли чем анализировать бесплатно: хотя бы один ник или ключ Bright Data."""
    if _brightdata_key():
        return True
    for p in _HANDLE_KEYS:
        if await _handle(p):
            return True
    return False


# ─────────────────────────── yt-dlp (YouTube / TikTok) ───────────────────────────

def _channel_url(platform: str, handle: str) -> str | None:
    if platform == "youtube":
        return f"https://www.youtube.com/@{handle}/videos"
    if platform == "tiktok":
        return f"https://www.tiktok.com/@{handle}"
    if platform == "instagram":
        return f"https://www.instagram.com/{handle}/"
    return None


def _extract_channel(url: str, n: int) -> dict:
    import yt_dlp
    opts = {
        "quiet": True, "no_warnings": True, "skip_download": True,
        "extract_flat": True, "playlistend": n, "noplaylist": False,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def _post_meta(e: dict) -> dict:
    return {
        "title": e.get("title"),
        "views": e.get("view_count"),
        "likes": e.get("like_count"),
        "duration": e.get("duration"),
        "url": e.get("url") or e.get("webpage_url"),
    }


def _engagement(m: dict) -> int:
    return int((m.get("views") or 0) + (m.get("likes") or 0) * 10)


async def _fetch_channel(platform: str, handle: str, n: int = 12) -> dict:
    """Публичные метрики канала + топ последних роликов (бесплатно, yt-dlp)."""
    url = _channel_url(platform, handle)
    if not url:
        return {"ok": False, "error": "no channel url"}
    try:
        info = await asyncio.to_thread(_extract_channel, url, n)
    except Exception as e:
        return {"ok": False, "error": str(e)[:150], "handle": handle, "platform": platform}

    entries = info.get("entries") or []
    posts = [_post_meta(e) for e in entries if e]
    ranked = sorted(posts, key=_engagement, reverse=True)
    return {
        "ok": True,
        "platform": platform,
        "handle": handle,
        "channel": info.get("title") or info.get("uploader"),
        "followers": info.get("channel_follower_count") or info.get("subscriber_count"),
        "posts_count": len(posts),
        "top_posts": ranked[:10],
        "source": "yt-dlp",
    }


# ─────────────────────────── Bright Data (Instagram и т.п.) ───────────────────────────

async def brightdata_fetch(url: str) -> str | None:
    """Достаёт HTML публичной страницы через Bright Data Web Unlocker.

    Нужен BRIGHTDATA_API_KEY. Используется там, где yt-dlp не справляется
    (Instagram обычно требует логина). Best-effort: при любой ошибке — None.
    """
    key = _brightdata_key()
    if not key:
        return None
    try:
        async with httpx.AsyncClient(timeout=45) as c:
            r = await c.post(
                "https://api.brightdata.com/request",
                headers={"Authorization": f"Bearer {key}",
                         "Content-Type": "application/json"},
                json={
                    "zone": os.getenv("BRIGHTDATA_ZONE", "web_unlocker1"),
                    "url": url,
                    "format": "raw",
                },
            )
        if r.status_code == 200:
            return r.text
    except Exception:
        return None
    return None


async def _fetch_instagram(handle: str) -> dict:
    """Instagram: пробуем Bright Data, при неудаче — честная деградация."""
    url = _channel_url("instagram", handle)
    html = await brightdata_fetch(url)
    if not html:
        return {"ok": False, "platform": "instagram", "handle": handle,
                "error": "Instagram требует Bright Data (BRIGHTDATA_API_KEY) — "
                         "yt-dlp его не тянет без логина."}
    # Из HTML вытаскиваем описание профиля (og:description содержит
    # «N Followers, M Following, K Posts»).
    followers = None
    marker = 'property="og:description" content="'
    i = html.find(marker)
    if i != -1:
        desc = html[i + len(marker): html.find('"', i + len(marker))]
        followers = desc.split(" Followers")[0].strip() if " Followers" in desc else None
    return {"ok": True, "platform": "instagram", "handle": handle,
            "followers": followers, "source": "brightdata"}


# ─────────────────────────── публичный интерфейс ───────────────────────────

async def get_account_intelligence(platforms: list[str] | None = None) -> dict:
    """«Досье аккаунта» — бесплатно. По каждой площадке: подписчики + топ роликов.

    Совместимо по форме со старым Ayrshare-вариантом (dict, который агенты
    сериализуют в контекст LLM).
    """
    platforms = [p for p in (platforms or ["instagram"]) if p in _HANDLE_KEYS]
    out: dict = {"platforms": platforms, "source": "free", "accounts": {}}

    for p in platforms:
        handle = await _handle(p)
        if not handle:
            out["accounts"][p] = {"ok": False, "error": f"ник для {p} не задан"}
            continue
        if p == "instagram":
            out["accounts"][p] = await _fetch_instagram(handle)
        else:
            out["accounts"][p] = await _fetch_channel(p, handle)

    return out


# ─────────── совместимость со старыми роутами /api/social/* ───────────

async def get_user() -> dict:
    accts = []
    for p in _HANDLE_KEYS:
        if await _handle(p):
            accts.append(p)
    return {"activeSocialAccounts": accts}


async def get_profile_analytics(platforms: list[str]) -> dict:
    return await get_account_intelligence(platforms)


async def get_recent_posts(platforms: list[str] | None = None, last_records: int = 20) -> dict:
    intel = await get_account_intelligence(platforms)
    history = []
    for p, data in intel.get("accounts", {}).items():
        for post in (data.get("top_posts") or [])[:last_records]:
            history.append({"platform": p, **post})
    return {"history": history}


async def get_post_analytics(post_id: str = None, platforms: list[str] = None) -> dict:
    """Метрики одного ролика по ссылке (бесплатно, yt-dlp)."""
    if not post_id:
        return {"error": "укажите ссылку на ролик (post_id = URL)"}
    from core.viral_research import fetch_meta
    return await fetch_meta(post_id)
