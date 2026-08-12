"""Instagram User Access Token (IGAA…): весь путь работает через graph.instagram.com.

Раньше код был жёстко зашит на graph.facebook.com и числовой Account ID. С токеном
Instagram Login это означало, что публикация, чтение, комментарии и проверка
не работали вовсе — Meta не знает таких адресов для этого токена.
"""
import pytest

from connectors import ig_api
from connectors.instagram import InstagramConnector

IG_TOKEN = "IGAA" + "x" * 100
FB_TOKEN = "EAA" + "y" * 100


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, routes, seen):
        self._routes, self._seen = routes, seen

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def _call(self, url, params=None, **kw):
        self._seen.append(url)
        for fragment, payload in self._routes.items():
            if fragment in url:
                return FakeResponse(payload)
        return FakeResponse({"error": {"message": f"нет маршрута: {url}"}})

    get = _call
    post = _call


@pytest.fixture
def calls(monkeypatch):
    state = {"routes": {}, "seen": []}
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda *a, **kw: FakeClient(state["routes"], state["seen"]))
    return state


@pytest.fixture
def ig_login(monkeypatch):
    """Аккаунт подключён токеном Instagram Login — числового id нет намеренно."""
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", IG_TOKEN)
    monkeypatch.setenv("INSTAGRAM_TOKEN_TYPE", "instagram")
    monkeypatch.delenv("INSTAGRAM_ACCOUNT_ID", raising=False)


@pytest.fixture
def fb_login(monkeypatch):
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", FB_TOKEN)
    monkeypatch.setenv("INSTAGRAM_TOKEN_TYPE", "facebook")
    monkeypatch.setenv("INSTAGRAM_ACCOUNT_ID", "17841400999")


# ─────────────────────── выбор API по типу токена ───────────────────────

def test_type_detected_by_prefix_without_saved_setting(monkeypatch):
    """Даже если тип не сохранён, префикс IGAA однозначно указывает на ветку."""
    monkeypatch.delenv("INSTAGRAM_TOKEN_TYPE", raising=False)
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", IG_TOKEN)
    assert ig_api.is_instagram_login() is True

    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", FB_TOKEN)
    assert ig_api.is_instagram_login() is False


def test_instagram_login_uses_graph_instagram(ig_login):
    assert ig_api.base() == ig_api.GRAPH_IG
    assert ig_api.node() == "me"
    assert ig_api.me_path("media") == "me/media"


def test_facebook_uses_graph_facebook_and_numeric_id(fb_login):
    assert ig_api.base() == ig_api.GRAPH_FB
    assert ig_api.node() == "17841400999"
    assert ig_api.me_path("media") == "17841400999/media"


def test_account_id_not_required_for_instagram_login(ig_login):
    """Числовой id для этой ветки не нужен: раньше система считала её ненастроенной."""
    assert ig_api.configured() is True
    assert ig_api.missing() == []
    assert InstagramConnector().configured() is True


def test_account_id_still_required_for_facebook(monkeypatch):
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", FB_TOKEN)
    monkeypatch.setenv("INSTAGRAM_TOKEN_TYPE", "facebook")
    monkeypatch.delenv("INSTAGRAM_ACCOUNT_ID", raising=False)
    assert ig_api.configured() is False
    assert "INSTAGRAM_ACCOUNT_ID" in ig_api.missing()


# ─────────────────────────── проверка токена ───────────────────────────

@pytest.mark.asyncio
async def test_health_uses_me_not_debug_token(client, calls, ig_login):
    """`debug_token` — эндпоинт приложения Facebook, для IGAA его нет."""
    calls["routes"] = {"graph.instagram.com": {"id": "17841400999",
                                               "username": "pahon_ai",
                                               "followers_count": 1200,
                                               "media_count": 48}}
    res = await InstagramConnector().health()

    assert res["ok"] is True
    assert res["account"] == "pahon_ai"
    assert res["followers"] == 1200
    assert res["can_publish"] is True
    assert all("debug_token" not in u for u in calls["seen"])
    assert any("graph.instagram.com" in u for u in calls["seen"])


@pytest.mark.asyncio
async def test_health_reports_dead_token_plainly(client, calls, ig_login):
    calls["routes"] = {"graph.instagram.com": {"error": {"message": "Invalid token"}}}
    res = await InstagramConnector().health()
    assert res["ok"] is False
    assert "вставьте новый" in res["hint"]


# ──────────────────────────── чтение ────────────────────────────

@pytest.mark.asyncio
async def test_profile_read_goes_to_me(client, calls, ig_login):
    calls["routes"] = {"graph.instagram.com": {"username": "pahon_ai",
                                               "followers_count": 10}}
    from core.instagram_reader import my_profile
    await my_profile()
    assert any(u.endswith("/me") for u in calls["seen"]), calls["seen"]


@pytest.mark.asyncio
async def test_media_read_goes_to_me_media(client, calls, ig_login):
    calls["routes"] = {"graph.instagram.com": {"data": [{"id": "m1"}]}}
    from core.instagram_reader import my_media
    posts = await my_media(5)
    assert posts and posts[0]["id"] == "m1"
    assert any("/me/media" in u for u in calls["seen"])


@pytest.mark.asyncio
async def test_comments_read_goes_to_instagram_api(client, calls, ig_login):
    calls["routes"] = {
        "me/media": {"data": [{"id": "m1", "permalink": "https://ig/p/1"}]},
        "m1/comments": {"data": [{"id": "c1", "text": "почём?", "username": "klient"}]},
    }
    res = await InstagramConnector().read_comments()
    assert res["ok"] is True
    assert res["comments"][0]["text"] == "почём?"
    assert all("graph.facebook.com" not in u for u in calls["seen"])


# ──────────────────────────── публикация ────────────────────────────

@pytest.mark.asyncio
async def test_publish_uses_me_media_endpoints(client, calls, ig_login):
    """Главное: публикация обязана идти на graph.instagram.com/me/media."""
    calls["routes"] = {"me/media_publish": {"id": "post_1"},
                       "me/media": {"id": "container_1"}}
    from publishers.instagram_pub import publish_instagram
    res = await publish_instagram("текст поста", "https://img/1.png")

    assert res.get("id") == "post_1" or res.get("post_id") == "post_1"
    assert any("graph.instagram.com/v21.0/me/media" in u for u in calls["seen"])
    assert all("graph.facebook.com" not in u for u in calls["seen"])


@pytest.mark.asyncio
async def test_publish_without_token_says_what_is_missing(client, monkeypatch):
    monkeypatch.delenv("INSTAGRAM_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("INSTAGRAM_ACCOUNT_ID", raising=False)
    from publishers.instagram_pub import publish_instagram
    with pytest.raises(ValueError) as e:
        await publish_instagram("текст")
    assert "INSTAGRAM_ACCESS_TOKEN" in str(e.value)


@pytest.mark.asyncio
async def test_reply_comment_uses_instagram_api(client, calls, ig_login):
    calls["routes"] = {"c1/replies": {"id": "r1"}}
    res = await InstagramConnector().reply_comment("c1", "ответим в директ")
    assert res["ok"] is True and res["reply_id"] == "r1"
    assert any("graph.instagram.com" in u for u in calls["seen"])


# ──────────────────────────── ограничения ────────────────────────────

@pytest.mark.asyncio
async def test_business_discovery_is_honestly_blocked(client, ig_login):
    """Business Discovery живёт только в ветке Facebook — это ограничение платформы."""
    from core.instagram_reader import analyze_competitor
    res = await analyze_competitor("rival")
    assert res["ok"] is False
    assert res["blocked_by_api"] is True
    assert "Instagram Login" in res["error"]


@pytest.mark.asyncio
async def test_facebook_branch_still_uses_business_discovery(client, calls, fb_login):
    """Старый путь не сломан — им пользуются подключённые через Страницу."""
    calls["routes"] = {"graph.facebook.com": {"business_discovery": {
        "username": "rival", "followers_count": 500, "media_count": 12,
        "media": {"data": []}}}}
    from core.instagram_reader import analyze_competitor
    res = await analyze_competitor("rival")
    assert res["ok"] is True
    assert res["followers"] == 500
