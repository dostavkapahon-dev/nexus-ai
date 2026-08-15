"""
Публикация в Instagram: Reels, карусель, сторис и честные отказы.

Проверяется то, из-за чего пользователь получал не то, что просил: видео молча
не публиковалось, а текст без картинки уходил со случайным изображением с
чужого сервиса — и всё это под видом успеха.
"""
import httpx
import pytest

from publishers import instagram_pub as ig
from connectors.instagram import InstagramConnector


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "IGAAtest123")
    monkeypatch.setenv("INSTAGRAM_TOKEN_TYPE", "instagram")
    monkeypatch.setattr(ig, "READY_STEP", 0)          # тесты не спят
    yield


def _fake_meta(monkeypatch, *, status_seq=("FINISHED",), quota_used=0, fail=None):
    """Подменяет Meta: контейнер → статус → публикация. Пишет вызовы в calls."""
    calls = []
    statuses = list(status_seq)

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        params = dict(request.url.params)
        calls.append({"path": path, "params": params, "method": request.method})

        if fail and fail in path:
            return httpx.Response(200, json={"error": {"message": "Meta отказала"}})
        if "content_publishing_limit" in path:
            return httpx.Response(200, json={"data": [
                {"quota_usage": quota_used, "config": {"quota_total": 25}}]})
        if path.endswith("/media_publish"):
            return httpx.Response(200, json={"id": "POST-1"})
        if path.endswith("/media"):
            return httpx.Response(200, json={"id": f"CONT-{len(calls)}"})
        # Запрос статуса контейнера
        return httpx.Response(200, json={
            "status_code": statuses.pop(0) if len(statuses) > 1 else statuses[0]})

    transport = httpx.MockTransport(handler)
    real = httpx.AsyncClient
    monkeypatch.setattr(ig.httpx, "AsyncClient",
                        lambda *a, **kw: real(*a, **{**kw, "transport": transport}))
    return calls


@pytest.mark.asyncio
async def test_text_without_media_is_refused_not_faked(monkeypatch):
    """Раньше сюда подставлялась случайная картинка с pollinations.ai."""
    _fake_meta(monkeypatch)
    with pytest.raises(ig.InstagramError) as e:
        await ig.publish_instagram("просто текст")
    assert "без медиа" in str(e.value)


@pytest.mark.asyncio
async def test_reel_is_published_as_reels_and_waits_for_processing(monkeypatch):
    calls = _fake_meta(monkeypatch, status_seq=["IN_PROGRESS", "FINISHED"])
    res = await ig.publish_instagram("подпись", video_url="https://cdn/x.mp4")

    assert res["post_id"] == "POST-1" and res["kind"] == "reel"
    container = next(c for c in calls if c["path"].endswith("/media"))
    assert container["params"]["media_type"] == "REELS"
    assert container["params"]["video_url"] == "https://cdn/x.mp4"
    # Публикация — только после проверки готовности, иначе Meta вернёт ошибку.
    order = [c["path"] for c in calls]
    assert order.index("/v21.0/me/media") < order.index("/v21.0/media_publish") \
        if "/v21.0/media_publish" in order else True
    assert any("status_code" in (c["params"].get("fields") or "") for c in calls)


@pytest.mark.asyncio
async def test_video_processing_error_is_reported(monkeypatch):
    _fake_meta(monkeypatch, status_seq=["ERROR"])
    with pytest.raises(ig.InstagramError) as e:
        await ig.publish_instagram("подпись", video_url="https://cdn/x.mp4")
    assert "не смог обработать" in str(e.value)


@pytest.mark.asyncio
async def test_carousel_collects_children(monkeypatch):
    calls = _fake_meta(monkeypatch)
    res = await ig.publish_instagram("подпись", images=["https://a/1.jpg",
                                                        "https://a/2.jpg"])
    assert res["kind"] == "carousel" and res["items"] == 2
    kids = [c for c in calls if c["params"].get("is_carousel_item") == "true"]
    assert len(kids) == 2
    wrapper = next(c for c in calls if c["params"].get("media_type") == "CAROUSEL")
    assert "," in wrapper["params"]["children"]


@pytest.mark.asyncio
async def test_story_uses_stories_type(monkeypatch):
    calls = _fake_meta(monkeypatch)
    res = await ig.publish_instagram("", image_url="https://a/1.jpg", as_story=True)
    assert res["kind"] == "story"
    container = next(c for c in calls if c["path"].endswith("/media"))
    assert container["params"]["media_type"] == "STORIES"
    # У сторис нет подписи — Meta отвергает caption для этого типа.
    assert "caption" not in container["params"]


@pytest.mark.asyncio
async def test_daily_quota_stops_publishing(monkeypatch):
    _fake_meta(monkeypatch, quota_used=25)
    with pytest.raises(ig.InstagramError) as e:
        await ig.publish_instagram("текст", image_url="https://a/1.jpg")
    assert "квота" in str(e.value)


@pytest.mark.asyncio
async def test_connector_passes_video_through(monkeypatch):
    """Главная потеря была здесь: коннектор не прокидывал video_url дальше."""
    seen = {}

    async def fake_publish(text, image_url=None, video_url=None, images=None,
                           as_story=False):
        seen.update({"text": text, "image": image_url, "video": video_url})
        return {"post_id": "P1", "kind": "reel"}

    monkeypatch.setattr("publishers.instagram_pub.publish_instagram", fake_publish)
    res = await InstagramConnector().publish("подпись", video_url="https://cdn/x.mp4")
    assert res["ok"] and seen["video"] == "https://cdn/x.mp4"


@pytest.mark.asyncio
async def test_connector_marks_quota_refusal_as_permanent(monkeypatch):
    async def fake_publish(*a, **kw):
        raise ig.InstagramError("исчерпана суточная квота Instagram (25/25 публикаций)")

    monkeypatch.setattr("publishers.instagram_pub.publish_instagram", fake_publish)
    res = await InstagramConnector().publish("текст", image_url="https://a/1.jpg")
    # Повторять такое бессмысленно — очередь не должна долбить Meta.
    assert res["ok"] is False and res["blocked_by_api"] is True


@pytest.mark.asyncio
async def test_health_does_not_promise_publishing_to_personal_account(monkeypatch):
    """`can_publish` раньше был захардкожен в True для любого аккаунта."""
    async def fake_get(self, path, params=None):
        return {"username": "user", "account_type": "PERSONAL", "followers_count": 10}

    monkeypatch.setattr(InstagramConnector, "_get", fake_get)
    st = await InstagramConnector().health()
    assert st["ok"] is True and st["can_publish"] is False
    assert "бизнес" in st["warning"]

    async def business(self, path, params=None):
        return {"username": "user", "account_type": "BUSINESS"}

    monkeypatch.setattr(InstagramConnector, "_get", business)
    st = await InstagramConnector().health()
    assert st["can_publish"] is True
