"""
Threads — прямое подключение через Meta Threads API (graph.threads.net).

Публикация есть; чтения профиля и статистики в проекте не было вовсе — добавлено здесь.
"""
import os
import httpx

from connectors.base import SocialConnector

GRAPH = "https://graph.threads.net/v1.0"


class ThreadsConnector(SocialConnector):
    platform = "threads"
    required_env = ("THREADS_ACCESS_TOKEN", "THREADS_USER_ID")
    rate_per_minute = 20

    def _token(self) -> str:
        return os.getenv("THREADS_ACCESS_TOKEN", "").strip()

    def _user_id(self) -> str:
        return os.getenv("THREADS_USER_ID", "").strip()

    async def _get(self, path: str, params: dict) -> dict:
        await self.limiter.acquire()
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(f"{GRAPH}/{path}", params={**params, "access_token": self._token()})
            return r.json()

    async def health(self) -> dict:
        out = {"platform": self.platform, "configured": self.configured(),
               "missing_env": self.missing_env()}
        if not self.configured():
            return {**out, "ok": False, "error": "не заданы " + ", ".join(self.missing_env())}
        try:
            data = await self._get(self._user_id(), {"fields": "id,username"})
            if data.get("error"):
                return {**out, "ok": False, "error": data["error"].get("message", "")[:200]}
            return {**out, "ok": True, "account": data.get("username", ""),
                    "expires_at": "неизвестно (Threads не отдаёт срок)", "days_left": None,
                    "permissions": ["threads_basic", "threads_content_publish"],
                    "can_publish": True}
        except Exception as e:
            return {**out, "ok": False, "error": str(e)[:200]}

    async def read_profile(self) -> dict:
        if not self.configured():
            return {"ok": False, "error": "не задан токен Threads"}
        try:
            d = await self._get(self._user_id(),
                                {"fields": "id,username,threads_profile_picture_url,threads_biography"})
            if d.get("error"):
                return {"ok": False, "error": d["error"].get("message", "")[:200]}
            return {"ok": True, "platform": "threads", "handle": d.get("username"),
                    "bio": d.get("threads_biography"), "source": "threads_api"}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def read_posts(self, limit: int = 10) -> dict:
        if not self.configured():
            return {"ok": False, "error": "не задан токен Threads"}
        try:
            d = await self._get(f"{self._user_id()}/threads",
                                {"fields": "id,text,timestamp,permalink", "limit": limit})
            if d.get("error"):
                return {"ok": False, "error": d["error"].get("message", "")[:200]}
            posts = [{"title": (p.get("text") or "")[:120], "url": p.get("permalink"),
                      "ts": p.get("timestamp")} for p in (d.get("data") or [])]
            return {"ok": True, "platform": "threads", "top_posts": posts,
                    "posts_count": len(posts), "source": "threads_api"}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def publish(self, text: str, image_url: str = "", video_url: str = "") -> dict:
        if not self.configured():
            return {"ok": False, "error": "не задан токен Threads",
                    "missing_env": self.missing_env()}
        from publishers.threads_pub import publish_threads
        try:
            await self.limiter.acquire()
            res = await publish_threads(text, image_url or None)
            return {"ok": True, "via": "threads_api", **res}
        except Exception as e:
            return {"ok": False, "via": "threads_api", "error": str(e)[:300]}
