"""Публикация через Ayrshare — сторонний сервис-посредник.

Ayrshare сам держит OAuth-связь с Instagram (и другими соцсетями): аккаунт
подключается один раз в их дашборде, а мы постим одним REST-запросом с API-ключом.
Это убирает необходимость в собственном Meta-приложении и ревью Meta.

Бесплатный тариф Ayrshare позволяет подключить один набор соцсетей и публиковать.
Ключ берётся из переменной окружения / БД: AYRSHARE_API_KEY.

Инструкция по подключению (один раз):
  1. Зарегистрироваться на https://www.ayrshare.com (Free plan).
  2. В дашборде Ayrshare нажать «Link» у Instagram и войти в аккаунт (OAuth).
  3. Скопировать API Key (Ayrshare dashboard → API Key) и вставить в настройках
     Nexus (поле «Ayrshare API Key») или задать env AYRSHARE_API_KEY.
"""
import os
import httpx

AYRSHARE_URL = "https://api.ayrshare.com/api/post"


def _api_key() -> str:
    return os.getenv("AYRSHARE_API_KEY", "").strip()


def is_configured() -> bool:
    return bool(_api_key())


# Площадки, которые Ayrshare умеет публиковать одним API-вызовом.
SUPPORTED_PLATFORMS = {
    "instagram", "facebook", "twitter", "x", "tiktok", "youtube",
    "linkedin", "pinterest", "threads", "telegram", "reddit",
    "bluesky", "gmb", "snapchat",
}

# Нормализация имён под идентификаторы Ayrshare.
_ALIASES = {"x": "twitter"}


def ayr_name(platform: str) -> str:
    p = (platform or "").lower().strip()
    return _ALIASES.get(p, p)


def supports(platform: str) -> bool:
    """Умеет ли Ayrshare постить в эту площадку."""
    return (platform or "").lower().strip() in SUPPORTED_PLATFORMS


async def publish_ayrshare(
    text: str,
    platforms: list[str],
    image_url: str | None = None,
    video_url: str | None = None,
) -> dict:
    """Публикует пост через Ayrshare на указанные платформы.

    platforms: список идентификаторов Ayrshare, напр. ["instagram"], ["facebook"],
    ["twitter"], ["tiktok"], ["youtube"], ["telegram"].
    """
    key = _api_key()
    if not key:
        raise ValueError("AYRSHARE_API_KEY не задан")

    body: dict = {"post": text, "platforms": platforms}

    media = []
    if video_url:
        media.append(video_url)
    elif image_url:
        media.append(image_url)
    # Instagram требует медиа — если его нет, подставляем плейсхолдер.
    if "instagram" in platforms and not media:
        media.append(
            "https://image.pollinations.ai/prompt/abstract%20minimal%20background"
            "?width=1080&height=1080&nologo=true"
        )
    if media:
        body["mediaUrls"] = media

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            AYRSHARE_URL,
            headers={"Authorization": f"Bearer {key}"},
            json=body,
        )
        data = r.json()

    status = data.get("status")
    if status != "success":
        # Ayrshare кладёт детали в errors/message
        errs = data.get("errors") or data.get("posts") or data
        raise RuntimeError(f"Ayrshare error: {errs}")

    post_ids = data.get("postIds") or data.get("id") or []
    first = post_ids[0] if isinstance(post_ids, list) and post_ids else {}
    return {
        "post_id": first.get("id") if isinstance(first, dict) else data.get("id"),
        "post_url": first.get("postUrl") if isinstance(first, dict) else None,
        "raw": post_ids,
    }


async def publish_instagram_ayrshare(text: str, image_url: str | None = None) -> dict:
    """Удобная обёртка: публикация в Instagram через Ayrshare."""
    return await publish_ayrshare(text, ["instagram"], image_url=image_url)


# ------------------------- Аналитика (чтение/анализ) -------------------------

API_BASE = "https://api.ayrshare.com/api"


async def _get(path: str, params: dict | None = None) -> dict:
    key = _api_key()
    if not key:
        raise ValueError("AYRSHARE_API_KEY не задан")
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{API_BASE}/{path}",
            headers={"Authorization": f"Bearer {key}"},
            params=params or {},
        )
        return r.json()


async def _post(path: str, body: dict) -> dict:
    key = _api_key()
    if not key:
        raise ValueError("AYRSHARE_API_KEY не задан")
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{API_BASE}/{path}",
            headers={"Authorization": f"Bearer {key}"},
            json=body,
        )
        return r.json()


async def get_user() -> dict:
    """Профиль в Ayrshare: какие соцсети подключены, отображаемые имена и т.д."""
    return await _get("user")


async def get_profile_analytics(platforms: list[str]) -> dict:
    """Аналитика профиля (шапка/аккаунт): подписчики, охваты, показы, вовлечённость.

    platforms: напр. ["instagram", "tiktok", "youtube", "facebook"].
    """
    return await _post("analytics/social", {"platforms": platforms})


async def get_post_analytics(post_id: str = None, platforms: list[str] = None) -> dict:
    """Аналитика конкретного поста/ролика: лайки, комментарии, просмотры, охват.

    Передайте id поста, полученный при публикации (postIds), или Ayrshare `id`.
    """
    body: dict = {}
    if post_id:
        body["id"] = post_id
    if platforms:
        body["platforms"] = platforms
    return await _post("analytics/post", body)


async def get_recent_posts(platforms: list[str] = None, last_records: int = 20) -> dict:
    """Список последних опубликованных постов/роликов (история)."""
    body: dict = {"lastRecords": last_records}
    if platforms:
        body["platforms"] = platforms
    return await _post("history", body)


def _engagement(item: dict) -> int:
    """Грубая оценка вовлечённости поста для сортировки топа."""
    a = item.get("analytics") or item
    return int(
        (a.get("likeCount") or a.get("likes") or 0)
        + (a.get("commentsCount") or a.get("comments") or 0)
        + (a.get("viewsCount") or a.get("views") or a.get("videoViews") or 0)
        + (a.get("reachCount") or a.get("reach") or 0)
    )


async def get_account_intelligence(platforms: list[str] = None) -> dict:
    """«Досье аккаунта» для стратега/ViralHunter — чтобы делать ролики не вслепую.

    Собирает: профиль (шапка, подписчики, охваты) + топ последних постов/роликов
    по вовлечённости. На основе этого агенты понимают, ЧТО за аккаунт и ЧТО зашло.
    """
    platforms = platforms or ["instagram"]
    out: dict = {"platforms": platforms}

    try:
        out["profile"] = await get_profile_analytics(platforms)
    except Exception as e:
        out["profile"] = {"error": str(e)[:200]}

    try:
        history = await get_recent_posts(platforms, last_records=30)
        posts = history.get("history") or history.get("posts") or []
        if isinstance(posts, list):
            ranked = sorted(posts, key=_engagement, reverse=True)
            out["top_posts"] = ranked[:10]
            out["posts_count"] = len(posts)
    except Exception as e:
        out["top_posts"] = {"error": str(e)[:200]}

    return out
