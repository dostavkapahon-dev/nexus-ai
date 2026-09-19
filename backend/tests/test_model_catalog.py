"""Каталог моделей: весь, постранично, с выбором прямо из Telegram.

Сверено живым вызовом платформы 17.09.2026. Важная деталь протокола: общий
список (`action=list` без типа) приходит страницами и его постраничная
навигация возвращает ту же страницу — полный каталог отдаёт только запрос
с фильтром по типу. Из-за этого неполного списка легко сделать обратную
ошибку: решить, что исправной модели «нет», и подменить её без причины.
"""
import pytest

from core import hixiit, telegram_bot as tb

IMAGE_ITEMS = [
    {"id": "z_image", "name": "Z Image", "provider_name": "Tongyi-MAI",
     "description": "Super fast, stylized text-to-image", "output_type": "image"},
    {"id": "soul_2", "name": "Soul 2.0", "provider_name": "Higgsfield",
     "output_type": "image", "supports_unlim": True},
    {"id": "nano_banana", "name": "Nano Banana", "provider_name": "Google",
     "output_type": "image", "supports_unlim": True},
    {"id": "ms_image", "name": "DTC Ads", "provider_name": "Higgsfield",
     "output_type": "image",
     "parameters": [{"name": "style_id", "required": "required"}]},
] + [{"id": f"img_{i}", "name": f"Model {i}", "output_type": "image"}
     for i in range(10)]


@pytest.fixture(autouse=True)
def _clean():
    hixiit._CATALOG_CACHE.clear()
    yield
    hixiit._CATALOG_CACHE.clear()


@pytest.fixture
def live(monkeypatch):
    asked = []

    async def fake_call(tool, args, timeout=600.0):
        asked.append(args)
        return {"items": IMAGE_ITEMS if args.get("type") == "image" else [],
                "has_more": False}

    monkeypatch.setattr(hixiit, "mcp_configured", lambda: True)
    monkeypatch.setattr(hixiit, "_mcp_call", fake_call)
    return asked


@pytest.mark.asyncio
async def test_catalog_is_requested_by_type(live):
    await hixiit.catalog_full("image")
    assert live[0]["type"] == "image", "без фильтра платформа отдаёт список частями"
    assert live[0]["limit"] >= 100


@pytest.mark.asyncio
async def test_catalog_keeps_real_models(live):
    ids = await hixiit.catalog_ids("image")
    # Эти модели у аккаунта есть — подменять их нельзя.
    assert {"z_image", "soul_2", "nano_banana"} <= ids
    model, note = await hixiit.ensure_known_model("z_image", "image")
    assert model == "z_image" and note == ""


@pytest.mark.asyncio
async def test_unknown_model_is_replaced_and_explained(live):
    model, note = await hixiit.ensure_known_model("выдуманная_модель", "image")
    assert model == "image_auto" or model in await hixiit.catalog_ids("image")
    assert "выдуманная_модель" in note


@pytest.mark.asyncio
async def test_model_needing_input_we_cannot_give_is_marked(live):
    rows = {m["value"]: m for m in await hixiit.catalog_full("image")}
    assert rows["ms_image"]["usable"] is False   # требует style_id
    assert rows["soul_2"]["usable"] is True
    assert rows["soul_2"]["unlim"] is True


@pytest.mark.asyncio
async def test_panel_shows_every_model_across_pages(live, monkeypatch):
    sent = []

    async def fake_send(chat_id, text, *a, **k):
        sent.append((text, k.get("reply_markup") or {}))

    async def no_pref(kind):
        return ""

    monkeypatch.setattr(tb, "send_message", fake_send)
    monkeypatch.setattr(hixiit, "preferred_model", no_pref)

    seen = set()
    pages = (len(IMAGE_ITEMS) + tb.PAGE_SIZE - 1) // tb.PAGE_SIZE
    for page in range(pages):
        await tb._show_catalog("1", "image", page)
        for row in sent[-1][1].get("inline_keyboard", []):
            for btn in row:
                if btn["callback_data"].startswith("setimg_"):
                    seen.add(btn["callback_data"][len("setimg_"):])

    assert {m["id"] for m in IMAGE_ITEMS} <= seen, "каталог показан не целиком"
    assert f"всего {len(IMAGE_ITEMS)}" in sent[0][0]


@pytest.mark.asyncio
async def test_panel_without_mcp_says_what_to_do(monkeypatch):
    sent = []

    async def fake_send(chat_id, text, *a, **k):
        sent.append(text)

    monkeypatch.setattr(tb, "send_message", fake_send)
    monkeypatch.setattr(hixiit, "mcp_configured", lambda: False)
    await tb._show_catalog("1", "image")
    assert "/hfconnect" in sent[0]
