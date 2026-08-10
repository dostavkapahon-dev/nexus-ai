"""
Автоматическое чтение Instagram через официальный Graph API (бесплатно).

Что даёт:
  • свой аккаунт — все посты и Reels + инсайты (охват, просмотры, сохранения,
    репосты, вовлечённость), подписчики, показы профиля;
  • чужой аккаунт — публичные данные через Business Discovery (подписчики,
    число постов, последние посты с лайками/комментариями).

Нужен один токен (тот же, что для публикации):
  INSTAGRAM_ACCESS_TOKEN  — Page/User access token с правами
                            instagram_basic, instagram_manage_insights,
                            pages_read_engagement;
  INSTAGRAM_ACCOUNT_ID    — id Instagram Business/Creator аккаунта.

Требование Meta: и свой аккаунт, и разбираемые чужие должны быть
Business/Creator (обычные приватные профили API не отдаёт).
"""
import os
import httpx

GRAPH = "https://graph.facebook.com/v19.0"


def _token() -> str:
    return os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip()


def _account_id() -> str:
    return os.getenv("INSTAGRAM_ACCOUNT_ID", "").strip()


def is_configured() -> bool:
    return bool(_token() and _account_id())


async def _get(path: str, params: dict) -> dict:
    params = {**params, "access_token": _token()}
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{GRAPH}/{path}", params=params)
        data = r.json()
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(data["error"].get("message", "Instagram API error"))
    return data


def _engagement(m: dict) -> int:
    return int((m.get("like_count") or 0) + (m.get("comments_count") or 0)
               + (m.get("views") or m.get("plays") or 0))


# ─────────────────────────── свой аккаунт ───────────────────────────

async def my_profile() -> dict:
    """Шапка своего аккаунта: username, подписчики, число постов."""
    return await _get(_account_id(), {"fields": "username,followers_count,media_count,biography"})


async def my_media(limit: int = 25) -> list[dict]:
    """Свои посты/Reels с базовыми метриками."""
    fields = ("id,caption,media_type,media_product_type,like_count,comments_count,"
              "timestamp,permalink,thumbnail_url,media_url")
    data = await _get(f"{_account_id()}/media", {"fields": fields, "limit": limit})
    return data.get("data", []) or []


async def media_insights(media_id: str, is_reel: bool) -> dict:
    """Инсайты одного поста/Reels (охват, просмотры, сохранения, репосты)."""
    metrics = ("reach,likes,comments,saved,shares,plays" if is_reel
               else "reach,likes,comments,saved,shares")
    try:
        data = await _get(f"{media_id}/insights", {"metric": metrics})
        out = {}
        for item in data.get("data", []):
            vals = item.get("values") or [{}]
            out[item.get("name")] = vals[0].get("value")
        return out
    except Exception as e:
        return {"error": str(e)[:120]}


async def analyze_own(with_insights: bool = True, top: int = 10) -> dict:
    """Полный разбор своего аккаунта: шапка + топ постов/Reels по вовлечённости."""
    profile = await my_profile()
    media = await my_media(limit=25)

    for m in media:
        if with_insights:
            ins = await media_insights(m["id"], m.get("media_product_type") == "REELS")
            m["views"] = ins.get("plays") or ins.get("reach")
            m["reach"] = ins.get("reach")
            m["saved"] = ins.get("saved")
            m["shares"] = ins.get("shares")

    ranked = sorted(media, key=_engagement, reverse=True)
    return {
        "ok": True,
        "platform": "instagram",
        "handle": profile.get("username"),
        "followers": profile.get("followers_count"),
        "posts_count": profile.get("media_count"),
        "bio": profile.get("biography"),
        "top_posts": [
            {"title": (m.get("caption") or "")[:120],
             "type": m.get("media_product_type") or m.get("media_type"),
             "likes": m.get("like_count"), "comments": m.get("comments_count"),
             "views": m.get("views"), "reach": m.get("reach"),
             "saved": m.get("saved"), "shares": m.get("shares"),
             "url": m.get("permalink")}
            for m in ranked[:top]
        ],
        "source": "graph_api",
    }


# ─────────────────────────── чужой аккаунт ───────────────────────────

async def analyze_competitor(username: str, top: int = 10) -> dict:
    """Публичные данные чужого Business/Creator аккаунта (Business Discovery)."""
    username = username.lstrip("@")
    bd = (f"business_discovery.username({username})"
          "{username,followers_count,media_count,"
          "media.limit(25){caption,like_count,comments_count,media_type,timestamp,permalink}}")
    data = await _get(_account_id(), {"fields": bd})
    disc = data.get("business_discovery") or {}
    media = (disc.get("media") or {}).get("data", []) or []
    ranked = sorted(media, key=_engagement, reverse=True)
    return {
        "ok": True,
        "platform": "instagram",
        "handle": disc.get("username") or username,
        "followers": disc.get("followers_count"),
        "posts_count": disc.get("media_count"),
        "top_posts": [
            {"title": (m.get("caption") or "")[:120], "type": m.get("media_type"),
             "likes": m.get("like_count"), "comments": m.get("comments_count"),
             "url": m.get("permalink")}
            for m in ranked[:top]
        ],
        "source": "graph_api_business_discovery",
    }


async def analyze(handle: str = "") -> dict:
    """Умный разбор: свой аккаунт (с инсайтами) или чужой (Business Discovery)."""
    handle = (handle or "").lstrip("@").strip()
    own_username = ""
    try:
        own_username = (await my_profile()).get("username", "")
    except Exception:
        pass
    if not handle or handle.lower() == (own_username or "").lower():
        return await analyze_own()
    return await analyze_competitor(handle)
