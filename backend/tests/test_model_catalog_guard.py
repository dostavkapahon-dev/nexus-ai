"""Несуществующая модель — это отказ вместо кадра, а не «кадр похуже».

Сверено живым вызовом Higgsfield 17.09.2026: в каталоге аккаунта есть soul_2,
gpt_image_2, image_auto, cinematic_studio_*, marketing_studio_*. Моделей
z_image, flux_3_video, minimax_hailuo, nano_banana и seedream там нет вовсе —
а именно они стояли в запасном списке и уходили в запрос.
"""
import pytest

from core import hixiit

LIVE = [
    {"id": "soul_2", "output_type": "image"},
    {"id": "gpt_image_2", "output_type": "image"},
    {"id": "image_auto", "output_type": "image"},
    {"id": "cinematic_studio_3_0", "output_type": "video"},
    {"id": "cinematic_studio_video_v2", "output_type": "video"},
]


@pytest.fixture(autouse=True)
def _clean():
    hixiit._CATALOG_CACHE.clear()
    yield
    hixiit._CATALOG_CACHE.clear()


@pytest.fixture
def live(monkeypatch):
    async def fake_call(tool, args, timeout=600.0):
        if tool == "models_explore":
            return {"items": LIVE, "unlim": {"available": False}}
        return {}
    monkeypatch.setattr(hixiit, "mcp_configured", lambda: True)
    monkeypatch.setattr(hixiit, "_mcp_call", fake_call)


@pytest.mark.asyncio
async def test_catalog_is_split_by_kind(live):
    assert "soul_2" in await hixiit.catalog_ids("image")
    assert "soul_2" not in await hixiit.catalog_ids("video")
    assert "cinematic_studio_3_0" in await hixiit.catalog_ids("video")


@pytest.mark.asyncio
async def test_known_model_is_left_alone(live):
    model, note = await hixiit.ensure_known_model("soul_2", "image")
    assert model == "soul_2" and note == ""


@pytest.mark.asyncio
async def test_unknown_model_is_replaced_and_explained(live):
    model, note = await hixiit.ensure_known_model("z_image", "image")
    assert model == "image_auto"
    assert "z_image" in note, "подмену нельзя прятать"


@pytest.mark.asyncio
async def test_unknown_video_model_is_replaced(live):
    model, _ = await hixiit.ensure_known_model("flux_3_video", "video")
    assert model == "cinematic_studio_3_0"


@pytest.mark.asyncio
async def test_no_catalog_means_no_guessing(monkeypatch):
    """Каталог не ответил — менять выбор не на чем, отправляем как есть."""
    async def fails(tool, args, timeout=600.0):
        raise RuntimeError("сеть недоступна")
    monkeypatch.setattr(hixiit, "mcp_configured", lambda: True)
    monkeypatch.setattr(hixiit, "_mcp_call", fails)
    model, note = await hixiit.ensure_known_model("soul_2", "image")
    assert model == "soul_2" and note == ""


@pytest.mark.asyncio
async def test_generation_sends_only_a_known_model(live, monkeypatch):
    sent = {}

    async def fake_call(tool, args, timeout=600.0):
        if tool == "models_explore":
            return {"items": LIVE, "unlim": {"available": False}}
        sent.update(dict(args.get("params") or {}))
        return {"results": [{"id": "job-1", "status": "pending"}]}

    async def done(job_id, attempts=40):
        return "https://x/i.png"

    async def picked(*a, **kw):
        return {"id": "z_image"}          # чем система соблазнилась бы раньше

    monkeypatch.setattr(hixiit, "_mcp_call", fake_call)
    monkeypatch.setattr(hixiit, "_wait_job", done)
    monkeypatch.setattr(hixiit, "pick_model", picked)

    res = await hixiit._generate_via_mcp("кадр кофейни утром", "image", "9:16")

    assert sent["model"] == "image_auto"
    assert res["model"] == "image_auto"
    assert "z_image" in res.get("note", "")
