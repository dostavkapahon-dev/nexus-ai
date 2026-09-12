"""
Меню моделей не должно предлагать выбор, которого нет.

Жалоба с сервера: «картинки очень страшные», хотя в /model выбрана другая
модель. Причина: REST-путь ходит на единственный адрес /v1/text2image/soul, и
любой другой выбор молча превращался в Soul — портретную модель, которая на
теме вроде «ИИ тренды» даёт негодный кадр. Меню показывало шесть моделей,
работала всегда одна.
"""
import pytest

from core import hixiit


@pytest.mark.asyncio
async def test_without_mcp_only_executable_image_model_is_offered(monkeypatch):
    monkeypatch.setattr(hixiit, "mcp_configured", lambda: False)
    monkeypatch.setattr("core.higgsfield.credentials", lambda: "k:s")

    models = await hixiit.available_models("image")

    assert [m["value"] for m in models] == [hixiit.REST_IMAGE_MODEL], \
        "остальные модели REST-путь запустить не может"


@pytest.mark.asyncio
async def test_without_mcp_video_offers_only_dop_models(monkeypatch):
    from core.higgsfield import DOP_MODELS
    monkeypatch.setattr(hixiit, "mcp_configured", lambda: False)
    monkeypatch.setattr("core.higgsfield.credentials", lambda: "k:s")

    models = await hixiit.available_models("video")

    assert [m["value"] for m in models] == list(DOP_MODELS)


@pytest.mark.asyncio
async def test_mcp_catalog_wins_when_available(monkeypatch):
    """С MCP доступен весь каталог аккаунта — урезать его нельзя."""
    async def catalog(tool, args, timeout=60):
        return {"items": [{"id": "nano_banana_pro", "name": "Nano Banana Pro"},
                          {"id": "seedream_v4_5", "name": "Seedream 4.5"}]}

    monkeypatch.setattr(hixiit, "mcp_configured", lambda: True)
    monkeypatch.setattr(hixiit, "_mcp_call", catalog)

    values = [m["value"] for m in await hixiit.available_models("image")]

    assert "nano_banana_pro" in values and "seedream_v4_5" in values


@pytest.mark.asyncio
async def test_substituted_model_is_reported(monkeypatch):
    """Выбрал одну, сделала другая — человек должен это узнать."""
    monkeypatch.setattr(hixiit, "mcp_configured", lambda: False)
    monkeypatch.setattr("core.higgsfield.credentials", lambda: "k:s")

    async def chosen(kind):
        return "nano_banana_pro"

    async def made(prompt, ratio="9:16"):
        return {"ok": True, "url": "https://x/i.png"}

    monkeypatch.setattr(hixiit, "preferred_model", chosen)
    monkeypatch.setattr("core.higgsfield.generate_image", made)

    res = await hixiit._generate_once("кадр", "image", "9:16")

    assert res["model"] == hixiit.REST_IMAGE_MODEL
    assert "nano_banana_pro" in res["warning"]
    assert "HIGGSFIELD_MCP_URL" in res["warning"], "сказать, чем это лечится"


@pytest.mark.asyncio
async def test_no_warning_when_the_chosen_model_is_the_one_used(monkeypatch):
    monkeypatch.setattr(hixiit, "mcp_configured", lambda: False)
    monkeypatch.setattr("core.higgsfield.credentials", lambda: "k:s")

    async def chosen(kind):
        return hixiit.REST_IMAGE_MODEL

    async def made(prompt, ratio="9:16"):
        return {"ok": True, "url": "https://x/i.png"}

    monkeypatch.setattr(hixiit, "preferred_model", chosen)
    monkeypatch.setattr("core.higgsfield.generate_image", made)

    res = await hixiit._generate_once("кадр", "image", "9:16")

    assert "warning" not in res


@pytest.mark.asyncio
async def test_auto_choice_is_not_treated_as_substitution(monkeypatch):
    """AUTO — это «выбирай сам», а не «я хотел другую»."""
    monkeypatch.setattr(hixiit, "mcp_configured", lambda: False)
    monkeypatch.setattr("core.higgsfield.credentials", lambda: "k:s")

    async def chosen(kind):
        return ""

    async def made(prompt, ratio="9:16"):
        return {"ok": True, "url": "https://x/i.png"}

    monkeypatch.setattr(hixiit, "preferred_model", chosen)
    monkeypatch.setattr("core.higgsfield.generate_image", made)

    res = await hixiit._generate_once("кадр", "image", "9:16")

    assert "warning" not in res
