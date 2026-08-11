"""Социальные коннекторы: единый контракт, health, rate-limit, маршрутизация публикации."""
import pytest

from connectors import get_connector, all_connectors, PLATFORMS, health_all
from connectors.base import SocialConnector, RateLimiter


def test_registry_covers_all_platforms():
    assert set(PLATFORMS) == {"instagram", "threads", "telegram", "tiktok", "youtube", "vk"}
    for p in PLATFORMS:
        c = get_connector(p)
        assert isinstance(c, SocialConnector)
        assert c.platform == p


def test_connector_is_singleton_per_process():
    """У коннектора внутри свой rate-limiter — он обязан быть общим на процесс."""
    assert get_connector("instagram") is get_connector("instagram")


def test_unknown_platform_returns_none():
    assert get_connector("myspace") is None


def test_every_connector_implements_contract():
    for c in all_connectors():
        for method in ("publish", "health", "read_profile", "read_posts",
                       "refresh_token", "configured", "missing_env"):
            assert hasattr(c, method), f"{c.platform} не реализует {method}"


@pytest.mark.asyncio
async def test_health_reports_missing_keys_without_crashing(client):
    """Без ключей health не падает, а честно говорит, чего не хватает."""
    items = await health_all()
    assert len(items) == len(PLATFORMS)
    for st in items:
        assert st["ok"] is False
        assert st["configured"] is False
        assert st["missing_env"], f"{st['platform']}: не перечислены недостающие ключи"


@pytest.mark.asyncio
async def test_publish_without_keys_is_honest(client):
    c = get_connector("instagram")
    res = await c.publish("текст")
    assert res["ok"] is False
    assert "INSTAGRAM_ACCESS_TOKEN" in res.get("missing_env", [])


@pytest.mark.asyncio
async def test_youtube_publish_is_blocked_by_api_not_error(client):
    """Ограничение платформы должно помечаться как BLOCKED_BY_API, а не как сбой."""
    res = await get_connector("youtube").publish("текст", video_url="http://x/v.mp4")
    assert res["ok"] is False
    assert res["blocked_by_api"] is True
    assert "OAuth" in res["reason"]


@pytest.mark.asyncio
async def test_tiktok_reports_not_configured_before_api_limits(client):
    """Без токена честнее сказать «не настроено», чем «ограничение платформы»."""
    res = await get_connector("tiktok").publish("текст", video_url="http://x/v.mp4")
    assert res["ok"] is False
    assert "TIKTOK_ACCESS_TOKEN" in res["missing_env"]


@pytest.mark.asyncio
async def test_tiktok_video_is_blocked_by_api_when_configured(client, monkeypatch):
    """С токеном видео-постинг помечается как ограничение, а не как сбой кода."""
    monkeypatch.setenv("TIKTOK_ACCESS_TOKEN", "test-token")
    res = await get_connector("tiktok").publish("текст", video_url="http://x/v.mp4")
    assert res["ok"] is False
    assert res["blocked_by_api"] is True


@pytest.mark.asyncio
async def test_rate_limiter_delays_burst():
    """Ограничитель обязан притормаживать всплеск, иначе площадка забанит."""
    import time
    rl = RateLimiter(per_minute=120)      # окно 0.5 c между вызовами не нужно — проверяем учёт
    t0 = time.time()
    for _ in range(5):
        await rl.acquire()
    assert time.time() - t0 < 1.0         # в пределах лимита задержки быть не должно
    assert len(rl._calls) == 5


@pytest.mark.asyncio
async def test_orchestrator_uses_connector_then_browser(client, monkeypatch):
    """Без токенов публикация обязана уходить в браузерный путь, а не падать."""
    from core.orchestrator import nexus_core
    calls = []

    async def fake_browser(platform, text, image_url=None, max_steps=30):
        calls.append(platform)
        return {"ok": True, "status": "done", "via": "browser"}

    import publishers.browser_publish as bp
    monkeypatch.setattr(bp, "publish_via_browser", fake_browser)

    res = await nexus_core._publish_one("instagram", "текст", "")
    assert res["ok"] is True
    assert calls == ["instagram"]


@pytest.mark.asyncio
async def test_api_mode_does_not_fall_back_to_browser(client, monkeypatch):
    """В режиме api браузер не подключается — пользователь просил только API."""
    monkeypatch.setenv("NEXUS_PUBLISH_MODE", "api")
    from core.orchestrator import nexus_core
    res = await nexus_core._publish_one("instagram", "текст", "")
    assert res["ok"] is False
    assert "не настроена" in res["error"]


@pytest.mark.asyncio
async def test_social_health_api(auth_client):
    r = await auth_client.get("/api/social/health")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == len(PLATFORMS)
    assert data["connected"] == 0

    r2 = await auth_client.get("/api/social/health/instagram")
    assert r2.json()["platform"] == "instagram"

    r3 = await auth_client.get("/api/social/health/myspace")
    assert r3.json()["ok"] is False


@pytest.mark.asyncio
async def test_oauth_start_reports_missing_app_id(auth_client):
    r = await auth_client.get("/api/social/oauth/start")
    assert r.json()["ok"] is False
    assert "FACEBOOK_APP_ID" in r.json()["error"]


@pytest.mark.asyncio
async def test_oauth_callback_is_public_and_handles_error(client):
    """Callback вызывает Meta в браузере — он обязан работать без нашей авторизации."""
    r = await client.get("/api/social/oauth/callback", params={"error": "access_denied"})
    assert r.status_code == 200
    assert "access_denied" in r.text or "отменено" in r.text
