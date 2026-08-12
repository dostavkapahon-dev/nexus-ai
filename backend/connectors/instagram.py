"""
Instagram — прямое подключение через Meta Graph API.

Требования Meta: аккаунт Business или Creator, привязанный к Facebook Page.
Personal-аккаунты Graph API не отдаёт — это ограничение платформы (BLOCKED_BY_API).

Главное, чего не хватало: короткоживущий токен умирал через ~60 дней МОЛЧА, и
система узнавала об этом в момент падения публикации. Теперь есть обмен на
long-lived токен, продление и `health()` с числом оставшихся дней.
"""
import os
from datetime import datetime, timedelta

import httpx

from connectors.base import SocialConnector
from connectors import ig_api

# Права, без которых работать не получится.
NEEDED_SCOPES = ("instagram_basic", "instagram_manage_insights",
                 "pages_read_engagement", "pages_show_list")
PUBLISH_SCOPES = ("instagram_content_publish", "pages_manage_posts")


class InstagramConnector(SocialConnector):
    platform = "instagram"
    required_env = ("INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_ACCOUNT_ID")
    rate_per_minute = 20          # Meta считает вызовы по часовому окну, держим запас

    # ── служебное ──────────────────────────────────────────────────────────
    def _token(self) -> str:
        return ig_api.token()

    def _account_id(self) -> str:
        return ig_api.account_id()

    def configured(self) -> bool:
        """У Instagram Login числовой id не нужен — аккаунт адресуется как `me`."""
        return ig_api.configured()

    def missing_env(self) -> list:
        return ig_api.missing()

    async def _get(self, path: str, params: dict) -> dict:
        await self.limiter.acquire()
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(ig_api.url(path), params={**params, "access_token": self._token()})
            return r.json()

    # ── состояние токена ───────────────────────────────────────────────────
    async def health(self) -> dict:
        """Проверяет токен вживую: валиден ли, когда истекает, какие права выданы."""
        out = {"platform": self.platform, "configured": self.configured(),
               "missing_env": self.missing_env()}
        if not self.configured():
            return {**out, "ok": False,
                    "error": "не заданы " + ", ".join(self.missing_env())}
        if ig_api.is_instagram_login():
            return await self._health_instagram_login(out)

        try:
            data = await self._get("debug_token", {"input_token": self._token()})
            info = (data or {}).get("data") or {}
            if data.get("error"):
                return {**out, "ok": False, "error": data["error"].get("message", "")[:200]}
            if not info.get("is_valid", False):
                return {**out, "ok": False, "error": "токен недействителен — нужно переподключить"}

            expires_at = int(info.get("expires_at") or 0)
            days_left = None
            if expires_at:
                days_left = round((datetime.utcfromtimestamp(expires_at)
                                   - datetime.utcnow()).total_seconds() / 86400, 1)
            scopes = info.get("scopes") or []
            missing_scopes = [s for s in NEEDED_SCOPES if s not in scopes]

            account = ""
            try:
                prof = await self._get(self._account_id(), {"fields": "username"})
                account = prof.get("username", "")
            except Exception:
                pass

            return {**out, "ok": True, "account": account,
                    # expires_at = 0 у long-lived токенов страницы: они бессрочные
                    "expires_at": (datetime.utcfromtimestamp(expires_at).isoformat()
                                   if expires_at else "бессрочный"),
                    "days_left": days_left,
                    "permissions": scopes,
                    "missing_permissions": missing_scopes,
                    "can_publish": all(s in scopes for s in PUBLISH_SCOPES),
                    "warning": ("токен истекает менее чем через 7 дней"
                                if days_left is not None and days_left < 7 else "")}
        except Exception as e:
            return {**out, "ok": False, "error": str(e)[:200]}

    async def refresh_token(self) -> dict:
        """Продлевает токен. Способ зависит от того, какого он семейства.

        У Meta два несовместимых вида токенов, и продлеваются они по-разному:
        токен Instagram Login — запросом `refresh_access_token` на graph.instagram.com,
        токен Facebook — обменом `fb_exchange_token`. Применить не тот способ —
        значит не продлить вовсе: через 60 дней публикация встанет без внятной
        причины. Тип запоминается при подключении (`core/ig_connect.py`).
        """
        if ig_api.is_instagram_login():
            return await self._refresh_instagram_login()

        app_id = os.getenv("FACEBOOK_APP_ID", "").strip()
        app_secret = os.getenv("FACEBOOK_APP_SECRET", "").strip()
        if not (app_id and app_secret):
            return {"ok": False, "refreshed": False,
                    "error": "нужны FACEBOOK_APP_ID и FACEBOOK_APP_SECRET, "
                             "чтобы обменять токен на долгоживущий"}
        if not self._token():
            return {"ok": False, "refreshed": False, "error": "нет текущего токена"}
        try:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.get(f"{ig_api.GRAPH_FB}/oauth/access_token", params={
                    "grant_type": "fb_exchange_token",
                    "client_id": app_id,
                    "client_secret": app_secret,
                    "fb_exchange_token": self._token(),
                })
                data = r.json()
            if data.get("error"):
                return {"ok": False, "refreshed": False,
                        "error": data["error"].get("message", "")[:200]}
            new_token = data.get("access_token")
            if not new_token:
                return {"ok": False, "refreshed": False, "error": "Meta не вернула токен"}

            await _save_key("instagram_access_token", new_token)
            expires_in = int(data.get("expires_in") or 0)
            return {"ok": True, "refreshed": True,
                    "expires_in_days": round(expires_in / 86400, 1) if expires_in else None,
                    "valid_until": (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat()
                    if expires_in else "бессрочный"}
        except Exception as e:
            return {"ok": False, "refreshed": False, "error": str(e)[:200]}

    async def _health_instagram_login(self, out: dict) -> dict:
        """Проверка токена Instagram Login.

        `debug_token` для него недоступен — это эндпоинт приложения Facebook.
        Поэтому проверяем самым надёжным способом: спрашиваем аккаунт о себе.
        Ответил — токен живой; права проверить нечем, они заданы при выдаче.
        """
        try:
            data = await self._get("me", {"fields": ig_api.profile_fields()})
            if data.get("error"):
                msg = (data["error"].get("message") or "")[:200]
                return {**out, "ok": False, "error": msg,
                        "hint": "токен недействителен или истёк — вставьте новый"}
            return {**out, "ok": True,
                    "account": data.get("username", ""),
                    "followers": data.get("followers_count"),
                    "media_count": data.get("media_count"),
                    "token_type": "instagram_login",
                    # Срок не отдаётся в этом ответе; продление идёт джобом в 08:00.
                    "expires_at": "около 60 дней с момента выдачи",
                    "days_left": None,
                    "permissions": [], "missing_permissions": [],
                    "can_publish": True,
                    "warning": ""}
        except Exception as e:
            return {**out, "ok": False, "error": str(e)[:200]}

    async def _refresh_instagram_login(self) -> dict:
        """Продление токена Instagram Login: App Secret не нужен, но есть условия.

        Meta продлевает только токен, которому уже больше 24 часов и который ещё
        не истёк. Просроченный не восстановить — нужен новый из панели, и лучше
        сказать это прямо, чем отдать невнятную ошибку Meta.
        """
        token = self._token()
        if not token:
            return {"ok": False, "refreshed": False, "error": "нет текущего токена"}
        try:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.get("https://graph.instagram.com/refresh_access_token",
                                params={"grant_type": "ig_refresh_token",
                                        "access_token": token})
                data = r.json()
            if data.get("error"):
                msg = (data["error"].get("message") or "")[:200]
                return {"ok": False, "refreshed": False, "error": msg,
                        "hint": "если токен уже истёк, продлить его нельзя — "
                                "сгенерируйте новый в панели Meta и вставьте заново"}
            new_token = data.get("access_token")
            if not new_token:
                return {"ok": False, "refreshed": False, "error": "Meta не вернула токен"}

            await _save_key("instagram_access_token", new_token)
            expires_in = int(data.get("expires_in") or 0)
            return {"ok": True, "refreshed": True, "method": "ig_refresh_token",
                    "expires_in_days": round(expires_in / 86400, 1) if expires_in else None,
                    "valid_until": (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat()
                    if expires_in else None}
        except Exception as e:
            return {"ok": False, "refreshed": False, "error": str(e)[:200]}

    # ── чтение ─────────────────────────────────────────────────────────────
    async def read_profile(self) -> dict:
        if not self.configured():
            return {"ok": False, "error": "не задан токен Instagram"}
        from core.instagram_reader import my_profile
        try:
            await self.limiter.acquire()
            return {"ok": True, **(await my_profile())}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def read_posts(self, limit: int = 10) -> dict:
        if not self.configured():
            return {"ok": False, "error": "не задан токен Instagram"}
        from core.instagram_reader import analyze_own
        try:
            await self.limiter.acquire()
            return await analyze_own(top=limit)
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    # ── комментарии ────────────────────────────────────────────────────────
    async def read_comments(self, limit: int = 20) -> dict:
        """Комментарии под последними постами — вход для воронки продаж.

        Нужно право instagram_manage_comments; без него Meta вернёт ошибку прав.
        """
        if not self.configured():
            return {"ok": False, "error": "не задан токен Instagram"}
        try:
            media = await self._get(ig_api.me_path("media"),
                                    {"fields": "id,permalink,caption", "limit": 5})
            if media.get("error"):
                return {"ok": False, "error": media["error"].get("message", "")[:200]}

            out = []
            for m in (media.get("data") or [])[:5]:
                res = await self._get(f"{m['id']}/comments",
                                      {"fields": "id,text,username,timestamp,like_count",
                                       "limit": limit})
                if res.get("error"):
                    continue
                for c in (res.get("data") or []):
                    out.append({"id": c.get("id"), "text": c.get("text", ""),
                                "author": c.get("username", ""),
                                "created_at": c.get("timestamp"),
                                "likes": c.get("like_count", 0),
                                "post_id": m["id"], "post_url": m.get("permalink")})
            return {"ok": True, "platform": self.platform, "comments": out[:limit]}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def reply_comment(self, comment_id: str, text: str) -> dict:
        """Ответ на комментарий. Публикуется только после согласования."""
        if not self.configured():
            return {"ok": False, "error": "не задан токен Instagram"}
        try:
            await self.limiter.acquire()
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.post(ig_api.url(f"{comment_id}/replies"),
                                 params={"message": text[:1000],
                                         "access_token": self._token()})
                d = r.json()
            if d.get("error"):
                return {"ok": False, "error": d["error"].get("message", "")[:200]}
            return {"ok": True, "reply_id": d.get("id")}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    # ── публикация ─────────────────────────────────────────────────────────
    async def publish(self, text: str, image_url: str = "", video_url: str = "") -> dict:
        if not self.configured():
            return {"ok": False, "error": "не задан токен Instagram",
                    "missing_env": self.missing_env()}
        from publishers.instagram_pub import publish_instagram
        try:
            await self.limiter.acquire()
            res = await publish_instagram(text, image_url or None)
            return {"ok": True, "via": "graph_api", **res}
        except Exception as e:
            return {"ok": False, "via": "graph_api", "error": str(e)[:300]}


async def _save_key(key_name: str, value: str):
    """Сохраняет обновлённый токен в БД и в окружение процесса."""
    from sqlalchemy import select
    from database.db import AsyncSessionLocal
    from database.models import Connection
    try:
        async with AsyncSessionLocal() as db:
            r = await db.execute(select(Connection).where(Connection.key_name == key_name))
            c = r.scalar_one_or_none()
            if c:
                c.key_value = value
            else:
                db.add(Connection(key_name=key_name, key_value=value))
            await db.commit()
    except Exception:
        pass
    os.environ[key_name.upper()] = value
