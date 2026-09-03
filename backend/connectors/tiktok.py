"""
TikTok — Content Posting API v2.

Ограничение платформы: неаудированное приложение постит только приватно, а
Research API (аналитика) доступен ограниченному кругу — это BLOCKED_BY_API.
"""
import os
import httpx

from connectors.base import SocialConnector

API = "https://open.tiktokapis.com/v2"


class TikTokConnector(SocialConnector):
    platform = "tiktok"
    required_env = ("TIKTOK_ACCESS_TOKEN",)
    rate_per_minute = 10

    async def health(self) -> dict:
        out = {"platform": self.platform, "configured": self.configured(),
               "missing_env": self.missing_env()}
        if not self.configured():
            return {**out, "ok": False, "error": "не задан TIKTOK_ACCESS_TOKEN"}
        try:
            await self.limiter.acquire()
            token = os.getenv("TIKTOK_ACCESS_TOKEN", "")
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.post(f"{API}/post/publish/creator_info/query/",
                                 headers={"Authorization": f"Bearer {token}",
                                          "Content-Type": "application/json; charset=UTF-8"},
                                 json={})
                d = r.json()
            err = (d.get("error") or {})
            if err and err.get("code") not in ("ok", None):
                return {**out, "ok": False, "error": str(err.get("message"))[:200]}
            data = d.get("data") or {}
            return {**out, "ok": True,
                    "account": data.get("creator_nickname") or data.get("creator_username", ""),
                    "expires_at": "требует периодического продления", "days_left": None,
                    "permissions": ["video.publish", "video.upload"],
                    "can_publish": True,
                    "warning": "видео-постинг не реализован — сейчас только фото"}
        except Exception as e:
            return {**out, "ok": False, "error": str(e)[:200]}

    async def read_posts(self, limit: int = 10) -> dict:
        """Публичные метрики берём не из API (он закрыт), а бесплатно — yt-dlp/браузер."""
        from core.social_intel import _fetch_channel, _handle
        handle = await _handle("tiktok")
        if not handle:
            return {"ok": False, "error": "не задан TIKTOK_HANDLE"}
        return await _fetch_channel("tiktok", handle, limit)

    async def publish(self, text: str, image_url: str = "", video_url: str = "") -> dict:
        if not self.configured():
            return {"ok": False, "error": "не задан TIKTOK_ACCESS_TOKEN",
                    "missing_env": self.missing_env()}
        if video_url:
            return self._blocked(
                "Загрузка видео через Content Posting API не реализована в проекте.",
                "Публикация видео пойдёт через браузерный путь.")
        if not image_url:
            return {"ok": False, "error": "TikTok требует медиа (фото или видео)"}
        from publishers.tiktok_pub import publish_tiktok_photo
        try:
            await self.limiter.acquire()
            res = await publish_tiktok_photo(text, image_url)
            return {"ok": True, "via": "tiktok_api", **res}
        except Exception as e:
            return {"ok": False, "via": "tiktok_api", "error": str(e)[:300]}
