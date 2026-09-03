"""
Базовый интерфейс социального коннектора.

Зачем: раньше площадки были набором свободных функций (`publishers/*.py`), чтение
жило отдельно от публикации, а состояние токена нигде не проверялось — про
протухший токен Instagram система узнавала только в момент падения публикации.

Теперь у каждой площадки один объект с предсказуемым контрактом:
    publish() · read_profile() · read_posts() · health() · refresh_token()

Соцсети подключаются НАПРЯМУЮ (официальные API/OAuth). AI не является транспортным
слоем: он может анализировать полученные данные, но не добывает их.
"""
import os
import time
import asyncio
from abc import ABC, abstractmethod


class RateLimiter:
    """Простой ограничитель: не чаще N вызовов в минуту на площадку.

    Площадки банят за всплески, а внятного backoff в проекте не было вовсе.
    """

    def __init__(self, per_minute: int = 30):
        self.per_minute = max(1, per_minute)
        self._calls: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = time.time()
            self._calls = [t for t in self._calls if now - t < 60]
            if len(self._calls) >= self.per_minute:
                sleep_for = 60 - (now - self._calls[0]) + 0.1
                await asyncio.sleep(max(0.0, sleep_for))
                self._calls = [t for t in self._calls if time.time() - t < 60]
            self._calls.append(time.time())


class SocialConnector(ABC):
    """Общий контракт площадки. Реализации — в connectors/<platform>.py."""

    platform: str = ""
    # Переменные окружения, без которых прямой API-путь невозможен.
    required_env: tuple[str, ...] = ()
    rate_per_minute: int = 30

    def __init__(self):
        self.limiter = RateLimiter(self.rate_per_minute)

    # ── состояние ──────────────────────────────────────────────────────────
    def configured(self) -> bool:
        """Заданы ли все обязательные ключи для прямого API."""
        return all(os.getenv(k, "").strip() for k in self.required_env)

    def missing_env(self) -> list[str]:
        return [k for k in self.required_env if not os.getenv(k, "").strip()]

    @abstractmethod
    async def health(self) -> dict:
        """Живой статус: валиден ли токен, до какой даты, какие права.

        Возврат: {ok, configured, account, expires_at, days_left, permissions, error}
        """

    # ── чтение ─────────────────────────────────────────────────────────────
    async def read_profile(self) -> dict:
        """Шапка аккаунта. По умолчанию — не поддерживается площадкой."""
        return {"ok": False, "error": f"{self.platform}: чтение профиля не реализовано"}

    async def read_posts(self, limit: int = 10) -> dict:
        """Последние посты с метриками."""
        return {"ok": False, "error": f"{self.platform}: чтение постов не реализовано"}

    # ── запись ─────────────────────────────────────────────────────────────
    @abstractmethod
    async def publish(self, text: str, image_url: str = "", video_url: str = "") -> dict:
        """Публикация. Возврат: {ok, post_id?, post_url?, via, error?, blocked_by_api?}"""

    # ── комментарии ────────────────────────────────────────────────────────
    async def read_comments(self, limit: int = 20) -> dict:
        """Свежие комментарии под последними постами.

        По умолчанию площадка этого не умеет — не выдаём отсутствие за ошибку.
        """
        return {"ok": False, "supported": False,
                "error": f"{self.platform}: чтение комментариев не поддерживается"}

    async def reply_comment(self, comment_id: str, text: str) -> dict:
        return {"ok": False, "supported": False,
                "error": f"{self.platform}: ответы на комментарии не поддерживаются"}

    # ── токены ─────────────────────────────────────────────────────────────
    async def refresh_token(self) -> dict:
        """Продление токена. По умолчанию площадка этого не требует."""
        return {"ok": True, "refreshed": False, "reason": "продление не требуется"}

    # ── общее ──────────────────────────────────────────────────────────────
    def _blocked(self, reason: str, action: str = "") -> dict:
        """Единый формат для ограничений платформы — не выдаём их за ошибку кода."""
        return {"ok": False, "blocked_by_api": True, "platform": self.platform,
                "reason": reason, "action": action}

    def describe(self) -> dict:
        return {"platform": self.platform, "configured": self.configured(),
                "missing_env": self.missing_env(), "rate_per_minute": self.rate_per_minute}
