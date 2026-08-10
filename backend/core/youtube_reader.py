"""
Чтение YouTube через официальный Data API v3 (нужен только YOUTUBE_API_KEY).

Даёт по любому публичному каналу (свой или конкурента): подписчиков, число видео,
суммарные просмотры и последние ролики со статистикой (просмотры/лайки/комментарии).
Надёжнее, чем yt-dlp-скрейпинг: не падает от смены вёрстки и не требует логина.

Ограничение: личная аналитика (удержание, watch time) недоступна по API-ключу —
для неё нужен OAuth (YouTube Analytics API), это отдельный шаг.
"""
import os
import httpx

API = "https://www.googleapis.com/youtube/v3"


def _key() -> str:
    return os.getenv("YOUTUBE_API_KEY", "").strip()


def is_configured() -> bool:
    return bool(_key())


async def _get(path: str, params: dict) -> dict:
    params = {**params, "key": _key()}
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{API}/{path}", params=params)
        data = r.json()
    if isinstance(data, dict) and data.get("error"):
        msg = data["error"].get("message") if isinstance(data["error"], dict) else str(data["error"])
        raise RuntimeError(msg)
    return data


async def resolve_channel(handle: str) -> dict | None:
    """Ищет канал по @handle / имени / channelId. Возвращает {id, title, ...} или None."""
    h = (handle or "").lstrip("@").strip()
    if not h:
        return None
    # Прямой channelId (UC...).
    if h.startswith("UC") and len(h) >= 20:
        return {"id": h}
    # По @handle (forHandle) — самый точный путь.
    try:
        d = await _get("channels", {"part": "id,snippet,statistics,contentDetails", "forHandle": h})
        items = d.get("items") or []
        if items:
            return items[0]
    except Exception:
        pass
    # Фолбэк: поиск по имени.
    d = await _get("search", {"part": "snippet", "q": h, "type": "channel", "maxResults": 1})
    items = d.get("items") or []
    if items:
        return {"id": items[0]["snippet"]["channelId"], "snippet": items[0]["snippet"]}
    return None


async def _uploads_playlist(channel_id: str) -> tuple[str, dict]:
    d = await _get("channels", {"part": "snippet,statistics,contentDetails", "id": channel_id})
    items = d.get("items") or []
    if not items:
        return "", {}
    ch = items[0]
    uploads = ch.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads", "")
    return uploads, ch


async def recent_videos(uploads_playlist: str, n: int = 12) -> list[dict]:
    """Последние ролики канала со статистикой (views/likes/comments)."""
    if not uploads_playlist:
        return []
    pl = await _get("playlistItems", {"part": "contentDetails", "playlistId": uploads_playlist,
                                      "maxResults": min(n, 50)})
    ids = [it["contentDetails"]["videoId"] for it in (pl.get("items") or [])
           if it.get("contentDetails", {}).get("videoId")]
    if not ids:
        return []
    vids = await _get("videos", {"part": "snippet,statistics", "id": ",".join(ids)})
    out = []
    for v in vids.get("items", []):
        st = v.get("statistics", {})
        sn = v.get("snippet", {})
        out.append({
            "title": sn.get("title"),
            "views": int(st.get("viewCount", 0) or 0),
            "likes": int(st.get("likeCount", 0) or 0),
            "comments": int(st.get("commentCount", 0) or 0),
            "url": f"https://www.youtube.com/watch?v={v.get('id')}",
        })
    return out


async def analyze(handle: str = "", n: int = 12) -> dict:
    """Разбор канала: шапка + топ роликов по просмотрам. Форма совместима с social_intel."""
    ch = await resolve_channel(handle)
    if not ch:
        return {"ok": False, "platform": "youtube", "handle": handle,
                "error": "канал не найден по этому нику"}
    channel_id = ch.get("id")
    uploads, full = await _uploads_playlist(channel_id)
    stats = (full or ch).get("statistics", {})
    snip = (full or ch).get("snippet", {})
    videos = await recent_videos(uploads, n)
    videos.sort(key=lambda m: m.get("views", 0), reverse=True)
    return {
        "ok": True,
        "platform": "youtube",
        "handle": snip.get("customUrl") or snip.get("title") or handle,
        "channel": snip.get("title"),
        "followers": int(stats.get("subscriberCount", 0) or 0),
        "posts_count": int(stats.get("videoCount", 0) or 0),
        "total_views": int(stats.get("viewCount", 0) or 0),
        "top_posts": videos[:10],
        "source": "youtube_api",
    }
