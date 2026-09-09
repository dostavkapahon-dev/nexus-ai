"""Агент должен владеть Higgsfield, а не просто «дёргать генерацию».

Всё в этом файле сверено живым вызовом платформы: каталог моделей (models_explore),
формат запроса (params вложенный), асинхронный ответ (заявка со статусом), безлимит
(поле use_unlim и блок unlim). Прежний код слал плоские аргументы и ждал готовую
ссылку — на реальном протоколе это не сработало бы ни разу.
"""
import pytest

from core import hixiit


# ─────────────────────────── выбор модели под задачу ───────────────────────────

def test_catalog_uses_real_model_ids():
    """Раньше здесь были `soul` и `dop-*` из README старого SDK — таких моделей
    в каталоге аккаунта нет, и выбор закончился бы отказом."""
    images = {m["value"] for m in hixiit.IMAGE_MODELS}
    videos = {m["value"] for m in hixiit.VIDEO_MODELS}

    assert {"z_image", "soul_2", "gpt_image_2"} <= images
    assert {"minimax_hailuo", "cinematic_studio_3_0", "flux_3_video"} <= videos
    assert not (images | videos) & {"soul", "dop-turbo", "dop-lite", "dop-standard"}


def test_product_task_goes_to_marketing_model():
    assert hixiit.pick_by_task("реклама доставки еды", "image") == "marketing_studio_image"
    assert hixiit.pick_by_task("ролик про товар", "video") == "marketing_studio_video"


def test_text_in_frame_goes_to_text_capable_model():
    """Обложка с текстом на модели без текста — гарантированный брак."""
    assert hixiit.pick_by_task("обложка с надписью «скидка 30%»", "image") == "gpt_image_2"


def test_person_task_goes_to_soul():
    assert hixiit.pick_by_task("портрет девушки в кафе", "image") == "soul_2"


def test_video_without_reference_needs_text_to_video():
    """Не все видео-модели умеют стартовать без кадра — выбор должен это учитывать."""
    assert hixiit.pick_by_task("динамичный ролик", "video", has_reference=False) == "flux_3_video"
    assert hixiit.pick_by_task("динамичный ролик", "video", has_reference=True) == "minimax_hailuo"


def test_plain_image_defaults_to_cheap_draft():
    """Черновик дорогой моделью — выброшенные кредиты."""
    assert hixiit.pick_by_task("что-нибудь красивое", "image") == "z_image"


# ─────────────────────────── промпт под модель ───────────────────────────

def test_prompt_is_adapted_per_model():
    """Один универсальный промпт всем моделям — худший результат у всех сразу."""
    soul = hixiit.prompt_for("soul_2", "girl in a cafe")
    text = hixiit.prompt_for("gpt_image_2", "cover with a headline")

    assert "do not re-describe the face" in soul
    assert "on-image text" in text
    assert soul != text


def test_unknown_model_keeps_prompt_intact():
    assert hixiit.prompt_for("whatever", "простой промпт") == "простой промпт"


# ─────────────────────────── реальный протокол генерации ───────────────────────────

class _MCP:
    """Подменяет MCP и записывает, что именно ушло на платформу."""

    def __init__(self, unlim=False, unlim_models=None):
        self.calls = []
        self.unlim = unlim
        self.unlim_models = unlim_models or []

    async def __call__(self, tool, args, timeout=600.0):
        self.calls.append((tool, args))
        if tool == "models_explore":
            if args.get("unlim"):
                return {"items": [{"id": m} for m in self.unlim_models],
                        "unlim": {"available": self.unlim, "remaining": 7}}
            return {"items": []}
        if tool == "media_import_url":
            return {"media_id": "media-1"}
        if tool in ("generate_image", "generate_video"):
            return {"results": [{"id": "job-1", "status": "pending"}]}
        if tool == "jobs_wait":
            return {"jobs": [{"index": 0, "job_id": "job-1", "status": "completed",
                              "result_url": "https://cdn/result.png"}],
                    "all_terminal": True}
        raise AssertionError(f"неожиданный инструмент {tool}")


@pytest.fixture
def mcp(monkeypatch):
    monkeypatch.setenv("HIGGSFIELD_MCP_URL", "https://mcp.example/mcp")
    fake = _MCP()
    monkeypatch.setattr(hixiit, "_mcp_call", fake)
    return fake


@pytest.mark.asyncio
async def test_request_is_nested_in_params(client, mcp):
    """Платформа принимает вложенный `params`; плоские аргументы она не понимает."""
    res = await hixiit.generate("портрет в кафе", kind="image")

    assert res["ok"] and res["url"] == "https://cdn/result.png"
    tool, args = [c for c in mcp.calls if c[0] == "generate_image"][0]
    assert set(args) == {"params"}, "аргументы должны идти внутри params"
    assert args["params"]["model"] == "soul_2"
    assert args["params"]["count"] == 1, "черновик всегда одной штукой"


@pytest.mark.asyncio
async def test_pending_job_is_awaited(client, mcp):
    """Ответ на запрос — заявка со статусом pending, а не готовое медиа.
    Раньше код ждал ссылку сразу и падал бы на каждой генерации."""
    await hixiit.generate("кадр", kind="image")

    assert any(c[0] == "jobs_wait" for c in mcp.calls), "задачу надо дождаться"


@pytest.mark.asyncio
async def test_reference_image_is_imported_as_media_id(client, mcp):
    """MCP принимает media_id, а не ссылку."""
    await hixiit.generate("оживи кадр", kind="video", image_url="https://x/y.png")

    assert any(c[0] == "media_import_url" for c in mcp.calls)
    args = [c[1] for c in mcp.calls if c[0] == "generate_video"][0]
    assert args["params"]["medias"] == [{"value": "media-1", "role": "start_image"}]


@pytest.mark.asyncio
async def test_failed_job_does_not_look_like_success(client, mcp, monkeypatch):
    async def failing(tool, args, timeout=600.0):
        if tool == "jobs_wait":
            return {"jobs": [{"index": 0, "job_id": "job-1", "status": "failed"}],
                    "all_terminal": True}
        return await mcp(tool, args, timeout)

    monkeypatch.setattr(hixiit, "_mcp_call", failing)
    res = await hixiit.generate("кадр", kind="video")

    assert res["ok"] is False
    assert any("failed" in t for t in res["tried"])


# ─────────────────────────── безлимит ───────────────────────────

@pytest.mark.asyncio
async def test_unlim_is_used_when_available_for_the_model(client, monkeypatch):
    """Не использовать безлимит, когда он есть, — значит зря списывать кредиты."""
    monkeypatch.setenv("HIGGSFIELD_MCP_URL", "https://mcp.example/mcp")
    fake = _MCP(unlim=True, unlim_models=["soul_2", "z_image"])
    monkeypatch.setattr(hixiit, "_mcp_call", fake)

    res = await hixiit.generate("портрет в кафе", kind="image")

    args = [c[1] for c in fake.calls if c[0] == "generate_image"][0]
    assert args["params"]["use_unlim"] is True
    assert res["unlim"] is True


@pytest.mark.asyncio
async def test_unlim_not_used_for_model_it_does_not_cover(client, monkeypatch):
    """Запрос с безлимитом на непокрытую модель платформа отклонит — вместо
    генерации получим отказ."""
    monkeypatch.setenv("HIGGSFIELD_MCP_URL", "https://mcp.example/mcp")
    fake = _MCP(unlim=True, unlim_models=["gpt_image_2"])
    monkeypatch.setattr(hixiit, "_mcp_call", fake)

    await hixiit.generate("портрет в кафе", kind="image")

    args = [c[1] for c in fake.calls if c[0] == "generate_image"][0]
    assert args["params"]["use_unlim"] is False


@pytest.mark.asyncio
async def test_unlim_status_without_mcp_says_why(client, monkeypatch):
    monkeypatch.delenv("HIGGSFIELD_MCP_URL", raising=False)
    st = await hixiit.unlim_status()
    assert st["available"] is False and "MCP" in st["reason"]
