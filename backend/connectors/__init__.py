"""
Реестр социальных коннекторов.

Единая точка получения площадки: `get_connector("instagram")`.
Каждый коннектор реализует один и тот же контракт (см. `connectors/base.py`),
поэтому оркестратор, health-проверки и UI работают с ними одинаково.
"""
from connectors.base import SocialConnector
from connectors.instagram import InstagramConnector
from connectors.threads import ThreadsConnector
from connectors.telegram import TelegramConnector
from connectors.tiktok import TikTokConnector
from connectors.youtube import YouTubeConnector
from connectors.vk import VKConnector

_REGISTRY: dict[str, SocialConnector] = {}

_CLASSES = (InstagramConnector, ThreadsConnector, TelegramConnector,
            TikTokConnector, YouTubeConnector, VKConnector)

PLATFORMS = tuple(c.platform for c in _CLASSES)


def get_connector(platform: str) -> SocialConnector | None:
    """Коннектор площадки (синглтон на процесс — у него внутри свой rate-limiter)."""
    key = (platform or "").lower().strip()
    if key in _REGISTRY:
        return _REGISTRY[key]
    for cls in _CLASSES:
        if cls.platform == key:
            _REGISTRY[key] = cls()
            return _REGISTRY[key]
    return None


def all_connectors() -> list[SocialConnector]:
    return [get_connector(p) for p in PLATFORMS]


async def health_all() -> list[dict]:
    """Живой статус всех площадок — для дашборда и /diag."""
    import asyncio
    results = await asyncio.gather(*(c.health() for c in all_connectors()),
                                   return_exceptions=True)
    out = []
    for platform, res in zip(PLATFORMS, results):
        if isinstance(res, Exception):
            out.append({"platform": platform, "ok": False, "error": str(res)[:200]})
        else:
            out.append(res)
    return out


__all__ = ["SocialConnector", "get_connector", "all_connectors", "health_all", "PLATFORMS"]
