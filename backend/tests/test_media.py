"""Генерация медиа: учёт стоимости, фолбэк провайдеров, честные причины отказа."""
import pytest

from core import media_generator as mg
from core import cost_tracker as ct


@pytest.mark.asyncio
async def test_free_provider_is_always_last_resort(client, monkeypatch):
    """Картинка должна получиться всегда — Pollinations бесплатен и без лимитов."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("STABILITY_API_KEY", raising=False)

    url = await mg.generate_image("тестовый промпт", platform="instagram")
    assert url.startswith("https://image.pollinations.ai")


@pytest.mark.asyncio
async def test_image_generation_is_charged(client, monkeypatch):
    """Раньше генерация картинок шла мимо кассы — теперь попадает в неё."""
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("STABILITY_API_KEY", raising=False)

    async def fake_dalle(prompt, size):
        return "https://img/ok.png"

    monkeypatch.setattr(mg, "_dalle3", fake_dalle)
    before = (await ct.spend(24))["cost_usd"]

    url = await mg.generate_image("промпт")
    assert url == "https://img/ok.png"

    after = (await ct.spend(24))["cost_usd"]
    assert after == pytest.approx(before + mg.MEDIA_COST["dalle3"])


@pytest.mark.asyncio
async def test_failed_provider_falls_through_without_charge(client, monkeypatch):
    """За неудачную генерацию платить не за что, но след в журнале остаться должен."""
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("STABILITY_API_KEY", raising=False)

    async def broken(prompt, size):
        raise RuntimeError("квота исчерпана")

    monkeypatch.setattr(mg, "_dalle3", broken)
    before = await ct.spend(24)

    url = await mg.generate_image("промпт")
    assert "pollinations" in url          # ушли на бесплатный путь

    after = await ct.spend(24)
    assert after["calls"] > before["calls"]                 # попытка зафиксирована
    assert after["cost_usd"] == pytest.approx(before["cost_usd"])  # но не оплачена


@pytest.mark.asyncio
async def test_video_failure_keeps_provider_reasons(client, monkeypatch):
    """Раньше причина отказа каждого провайдера терялась — чинить было нечего."""
    monkeypatch.setenv("HEYGEN_API_KEY", "test")
    monkeypatch.delenv("HIGGSFIELD_API_KEY", raising=False)
    monkeypatch.delenv("RUNWAY_API_KEY", raising=False)

    async def fake_create(script, ratio="9:16"):
        return {"ok": False, "error": "лимит аккаунта HeyGen исчерпан"}

    import core.heygen as hg
    monkeypatch.setattr(hg, "create_avatar_video", fake_create)

    res = await mg.generate_clip("промпт", script="текст")
    assert res["ok"] is False
    assert "HeyGen" in res["error"]
    assert res["attempts"]["heygen"].startswith("лимит")


@pytest.mark.asyncio
async def test_no_keys_says_so_plainly(client, monkeypatch):
    for k in ("HEYGEN_API_KEY", "HIGGSFIELD_API_KEY", "RUNWAY_API_KEY"):
        monkeypatch.delenv(k, raising=False)

    res = await mg.generate_clip("промпт")
    assert res["ok"] is False
    assert "Нет доступного видео-провайдера" in res["error"]


@pytest.mark.asyncio
async def test_successful_video_is_charged(client, monkeypatch):
    monkeypatch.setenv("HEYGEN_API_KEY", "test")
    monkeypatch.delenv("HIGGSFIELD_API_KEY", raising=False)
    monkeypatch.delenv("RUNWAY_API_KEY", raising=False)

    async def fake_create(script, ratio="9:16"):
        return {"ok": True, "video_id": "v1"}

    async def fake_poll(video_id):
        return {"ok": True, "url": "https://video/ok.mp4"}

    import core.heygen as hg
    monkeypatch.setattr(hg, "create_avatar_video", fake_create)
    monkeypatch.setattr(hg, "poll_avatar_video", fake_poll)

    before = (await ct.spend(24))["cost_usd"]
    res = await mg.generate_clip("промпт", script="текст")
    assert res["ok"] is True

    after = (await ct.spend(24))["cost_usd"]
    assert after == pytest.approx(before + mg.MEDIA_COST["heygen"])


@pytest.mark.asyncio
async def test_cost_split_between_text_and_media(client):
    """Видео дороже текста в разы — смешивать их в одной цифре бессмысленно."""
    await ct.record(model="deepseek-chat", tokens=1000, cost=0.001, agent="copywriter")
    await ct.record(model="heygen:video", tokens=0, cost=0.30, agent="media")

    kinds = await ct.by_kind(24)
    assert kinds["media"]["cost_usd"] >= 0.30
    assert kinds["text"]["cost_usd"] >= 0.001
    assert kinds["media"]["cost_usd"] > kinds["text"]["cost_usd"]


@pytest.mark.asyncio
async def test_cost_api_includes_media_split(auth_client):
    await ct.record(model="runway:video", tokens=0, cost=0.25, agent="media")
    r = await auth_client.get("/api/cost")
    assert "by_kind" in r.json()
    assert r.json()["by_kind"]["media"]["calls"] >= 1
