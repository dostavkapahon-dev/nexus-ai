"""ВКонтакте — VK API. Публикация на стену сообщества."""
import os
import httpx

from connectors.base import SocialConnector

VK_API = "https://api.vk.com/method"
VK_VERSION = "5.199"


class VKConnector(SocialConnector):
    platform = "vk"
    required_env = ("VK_ACCESS_TOKEN", "VK_GROUP_ID")
    rate_per_minute = 20

    async def health(self) -> dict:
        out = {"platform": self.platform, "configured": self.configured(),
               "missing_env": self.missing_env()}
        if not self.configured():
            return {**out, "ok": False, "error": "не заданы " + ", ".join(self.missing_env())}
        try:
            await self.limiter.acquire()
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.get(f"{VK_API}/groups.getById", params={
                    "group_id": os.getenv("VK_GROUP_ID", ""),
                    "access_token": os.getenv("VK_ACCESS_TOKEN", ""),
                    "v": VK_VERSION})
                d = r.json()
            if "error" in d:
                return {**out, "ok": False,
                        "error": str(d["error"].get("error_msg"))[:200]}
            groups = (d.get("response") or {}).get("groups") or d.get("response") or []
            name = groups[0].get("name") if isinstance(groups, list) and groups else ""
            return {**out, "ok": True, "account": name,
                    "expires_at": "зависит от типа токена", "days_left": None,
                    "permissions": ["wall", "photos"], "can_publish": True}
        except Exception as e:
            return {**out, "ok": False, "error": str(e)[:200]}

    async def publish(self, text: str, image_url: str = "", video_url: str = "") -> dict:
        if not self.configured():
            return {"ok": False, "error": "не заданы ключи VK",
                    "missing_env": self.missing_env()}
        from publishers.vk_pub import publish_vk
        try:
            await self.limiter.acquire()
            res = await publish_vk(text, image_url or None)
            return {"ok": True, "via": "vk_api", **res}
        except Exception as e:
            return {"ok": False, "via": "vk_api", "error": str(e)[:300]}
