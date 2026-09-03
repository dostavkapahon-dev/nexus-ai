"""Telegram — свой бот, самый надёжный канал: без ревью и без ограничений площадки."""
import os
import httpx

from connectors.base import SocialConnector


class TelegramConnector(SocialConnector):
    platform = "telegram"
    required_env = ("TELEGRAM_BOT_TOKEN",)
    rate_per_minute = 30

    def _chat(self) -> str:
        return (os.getenv("TELEGRAM_POST_CHAT_ID", "")
                or os.getenv("TELEGRAM_CHAT_ID", "")).strip()

    async def _target(self) -> str:
        """Канал для публикации: подключённый через мастер — приоритетнее
        переменной окружения, иначе выбор канала в вебе ни на что не влиял бы."""
        try:
            from core.telegram_channels import default_channel
            chat = await default_channel()
            if chat:
                return chat
        except Exception:
            pass
        return self._chat()

    async def health(self) -> dict:
        out = {"platform": self.platform, "configured": self.configured(),
               "missing_env": self.missing_env()}
        if not self.configured():
            return {**out, "ok": False, "error": "не задан TELEGRAM_BOT_TOKEN"}
        try:
            await self.limiter.acquire()
            token = os.getenv("TELEGRAM_BOT_TOKEN", "")
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(f"https://api.telegram.org/bot{token}/getMe")
                d = r.json()
            if not d.get("ok"):
                return {**out, "ok": False, "error": d.get("description", "неверный токен")}
            chat = await self._target()
            return {**out, "ok": True, "account": "@" + d["result"].get("username", ""),
                    "expires_at": "бессрочный", "days_left": None,
                    "permissions": ["bot"], "can_publish": bool(chat), "channel": chat,
                    "warning": "" if chat else "не подключён канал для публикации"}
        except Exception as e:
            return {**out, "ok": False, "error": str(e)[:200]}

    async def publish(self, text: str, image_url: str = "", video_url: str = "") -> dict:
        chat = await self._target()
        if not self.configured() or not chat:
            return {"ok": False, "error": "Telegram не настроен (токен или канал)"}
        from publishers.telegram_pub import publish_telegram
        try:
            await self.limiter.acquire()
            res = await publish_telegram(chat, text, image_url or None, video_url or None)
            return {"ok": True, "via": "telegram", "post_id": res.get("message_id"), **res}
        except Exception as e:
            return {"ok": False, "via": "telegram", "error": str(e)[:300]}
