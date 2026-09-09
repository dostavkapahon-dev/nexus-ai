"""
Безлимит на фото: им надо пользоваться, а не просто знать о нём.

Живая проверка каталога показала: безлимит выдаётся на конкретные фото-модели
(soul_2, gpt_image_2, nano_banana, nano_banana_pro, seedream, flux_2,
kling_omni_image). Наши штатные картиночные модели — z_image, cinematic_studio_2_5,
marketing_studio_image — в этот список НЕ входят. Значит при активном безлимите
роль подбиралась верно, а кадр всё равно оплачивался кредитами.

Здесь проверяется, что при доступном безлимите система берёт покрытую им модель
той же роли, но никогда не подменяет модель вслепую.
"""
import pytest

from core import hixiit


COVERED = ["soul_2", "soul_v2", "gpt_image_2", "nano_banana",
           "nano_banana_pro", "nano_banana_2", "seedream_v4_5", "flux_2"]


def test_draft_goes_to_the_budget_unlim_model():
    assert hixiit.unlim_swap("z_image", "draft", COVERED) == "nano_banana"


def test_product_goes_to_a_quality_unlim_model():
    assert hixiit.unlim_swap("marketing_studio_image", "product", COVERED) \
        == "nano_banana_pro"


def test_cinematic_goes_to_prompt_adherent_unlim_model():
    assert hixiit.unlim_swap("cinematic_studio_2_5", "cinematic", COVERED) == "flux_2"


def test_already_covered_model_is_left_alone():
    """soul_2 и так покрыт — менять его значит менять кадр без причины."""
    assert hixiit.unlim_swap("soul_2", "person", COVERED) == ""


def test_no_swap_when_nothing_is_covered():
    """Подменять вслепую нельзя: платформа откажет вместо генерации."""
    assert hixiit.unlim_swap("z_image", "draft", []) == ""
    assert hixiit.unlim_swap("z_image", "draft", ["some_other_model"]) == ""


def test_role_is_read_from_the_task():
    assert hixiit.role_for_task("реклама доставки шашлыка", "image") == "product"
    assert hixiit.role_for_task("портрет бариста", "image") == "person"
    assert hixiit.role_for_task("обложка с текстом", "image") == "text"
    assert hixiit.role_for_task("просто кадр кофейни", "image") == "draft"


@pytest.mark.asyncio
async def test_generation_uses_unlim_model_when_unlim_is_available(monkeypatch):
    sent = {}

    async def fake_call(tool, args, timeout=600.0):
        if tool == "models_explore":
            return {"items": [{"id": m} for m in COVERED],
                    "unlim": {"available": True, "remaining": 100}}
        sent.update(args.get("params") or {})
        return {"results": [{"id": "job-1", "status": "pending"}]}

    async def done(job_id, attempts=40):
        return "https://x/i.png"

    async def model(*a, **kw):
        return {"id": "marketing_studio_image"}

    monkeypatch.setattr(hixiit, "mcp_configured", lambda: True)
    monkeypatch.setattr(hixiit, "_mcp_call", fake_call)
    monkeypatch.setattr(hixiit, "_wait_job", done)
    monkeypatch.setattr(hixiit, "pick_model", model)

    res = await hixiit._generate_via_mcp("реклама доставки шашлыка", "image", "9:16")

    assert sent["model"] == "nano_banana_pro", "безлимит остался неиспользованным"
    assert sent["use_unlim"] is True
    assert res["swapped_from"] == "marketing_studio_image", "подмену нельзя прятать"


@pytest.mark.asyncio
async def test_no_unlim_means_no_swap(monkeypatch):
    """Безлимита нет — модель остаётся той, которую выбрала экспертиза."""
    sent = {}

    async def fake_call(tool, args, timeout=600.0):
        if tool == "models_explore":
            return {"items": [{"id": m} for m in COVERED],
                    "unlim": {"available": False}}
        sent.update(args.get("params") or {})
        return {"results": [{"id": "job-1", "status": "pending"}]}

    async def done(job_id, attempts=40):
        return "https://x/i.png"

    async def model(*a, **kw):
        return {"id": "marketing_studio_image"}

    monkeypatch.setattr(hixiit, "mcp_configured", lambda: True)
    monkeypatch.setattr(hixiit, "_mcp_call", fake_call)
    monkeypatch.setattr(hixiit, "_wait_job", done)
    monkeypatch.setattr(hixiit, "pick_model", model)

    res = await hixiit._generate_via_mcp("реклама доставки шашлыка", "image", "9:16")

    assert sent["model"] == "marketing_studio_image"
    assert sent["use_unlim"] is False
    assert "swapped_from" not in res


@pytest.mark.asyncio
async def test_prompt_is_rewritten_for_the_new_model(monkeypatch):
    """У каждой модели свой язык промпта — подмена без этого испортит кадр."""
    sent = {}

    async def fake_call(tool, args, timeout=600.0):
        if tool == "models_explore":
            return {"items": [{"id": m} for m in COVERED],
                    "unlim": {"available": True}}
        sent.update(args.get("params") or {})
        return {"results": [{"id": "job-1", "status": "pending"}]}

    async def done(job_id, attempts=40):
        return "https://x/i.png"

    async def model(*a, **kw):
        return {"id": "z_image"}

    monkeypatch.setattr(hixiit, "mcp_configured", lambda: True)
    monkeypatch.setattr(hixiit, "_mcp_call", fake_call)
    monkeypatch.setattr(hixiit, "_wait_job", done)
    monkeypatch.setattr(hixiit, "pick_model", model)

    await hixiit._generate_via_mcp("кадр кофейни утром", "image", "9:16")

    assert sent["model"] == "nano_banana"
    assert sent["prompt"] == hixiit.prompt_for("nano_banana", "кадр кофейни утром")
