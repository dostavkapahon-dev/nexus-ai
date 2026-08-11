"""
YouTube — Data API v3.

Чтение канала работает по обычному API-ключу. Загрузка видео требует OAuth2
(`YOUTUBE_OAUTH_JSON`) — API-ключа принципиально недостаточно, это ограничение
платформы, а не сбой кода.
"""
import os
import httpx

from connectors.base import SocialConnector

API = "https://www.googleapis.com/youtube/v3"


class YouTubeConnector(SocialConnector):
    platform = "youtube"
    required_env = ("YOUTUBE_API_KEY",)      # для чтения; для публикации — OAuth
    rate_per_minute = 30

    async def health(self) -> dict:
        out = {"platform": self.platform, "configured": self.configured(),
               "missing_env": self.missing_env()}
        has_oauth = bool(os.getenv("YOUTUBE_OAUTH_JSON", "").strip())
        if not self.configured():
            return {**out, "ok": False, "error": "не задан YOUTUBE_API_KEY",
                    "can_publish": has_oauth}
        try:
            await self.limiter.acquire()
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.get(f"{API}/videos", params={
                    "part": "id", "chart": "mostPopular", "maxResults": 1,
                    "key": os.getenv("YOUTUBE_API_KEY", "")})
                d = r.json()
            if d.get("error"):
                return {**out, "ok": False,
                        "error": str(d["error"].get("message"))[:200], "can_publish": has_oauth}
            from core.social_intel import _handle
            handle = await _handle("youtube")
            return {**out, "ok": True, "account": handle or "(ник не задан)",
                    "expires_at": "API-ключ бессрочный", "days_left": None,
                    "permissions": ["youtube.readonly"] + (["youtube.upload"] if has_oauth else []),
                    "can_publish": has_oauth,
                    "warning": "" if has_oauth else
                               "загрузка видео недоступна: нужен YOUTUBE_OAUTH_JSON "
                               "(публикация пойдёт через браузер)"}
        except Exception as e:
            return {**out, "ok": False, "error": str(e)[:200], "can_publish": has_oauth}

    async def read_profile(self) -> dict:
        from core.youtube_reader import analyze, is_configured
        from core.social_intel import _handle
        if not is_configured():
            return {"ok": False, "error": "не задан YOUTUBE_API_KEY"}
        handle = await _handle("youtube")
        if not handle:
            return {"ok": False, "error": "не задан YOUTUBE_HANDLE"}
        await self.limiter.acquire()
        return await analyze(handle)

    async def read_posts(self, limit: int = 10) -> dict:
        return await self.read_profile()

    async def publish(self, text: str, image_url: str = "", video_url: str = "") -> dict:
        if not os.getenv("YOUTUBE_OAUTH_JSON", "").strip():
            return self._blocked(
                "Data API v3 разрешает загрузку только по OAuth2; API-ключа недостаточно.",
                "Задайте YOUTUBE_OAUTH_JSON либо публикуйте через браузерный путь.")
        from publishers.youtube_pub import publish_youtube_short
        try:
            await self.limiter.acquire()
            res = await publish_youtube_short(text[:100], text, video_url=video_url or None)
            return {"ok": bool(res.get("ok")), "via": "youtube_api", **res}
        except Exception as e:
            return {"ok": False, "via": "youtube_api", "error": str(e)[:300]}
