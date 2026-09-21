"""Чужой бесплатный генератор не выдаётся за Higgsfield.

Из Telegram: «✅ cover», «✅ storyboard_frames x4» — при том что Higgsfield
отказал, а у Gemini кончилась квота. Рисовал бесплатный Pollinations, и его
картинка с водяным знаком шла как результат. При этом в статусе честно стояло
«черновик бесплатным генератором: выключен»: настройка была, а этот путь её
не смотрел.
"""
import pytest

from core import media_generator as mg


@pytest.fixture(autouse=True)
def no_side_providers(monkeypatch):
    for key in ("GEMINI_API_KEY", "OPENAI_API_KEY", "STABILITY_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    async def hixiit_fails(*a, **k):
        return {"ok": False, "error": "400 Unavailable model"}

    monkeypatch.setattr("core.hixiit.generate", hixiit_fails)

    async def same(text):
        return text
    monkeypatch.setattr(mg, "enrich_image_prompt", same)

    async def no_track(*a, **k):
        return None
    monkeypatch.setattr(mg, "_track_media", no_track)


@pytest.mark.asyncio
async def test_free_generator_is_not_substituted_when_disabled(monkeypatch):
    monkeypatch.setattr("core.hixiit.free_draft_allowed", lambda: False)
    with pytest.raises(RuntimeError) as e:
        await mg.generate_image_ex("шашлык", platform="instagram")
    text = str(e.value)
    assert "водяной знак" in text
    assert "Unavailable model" in text, "причина отказа Higgsfield обязана быть в тексте"
    assert "NEXUS_FREE_DRAFT" in text, "как разрешить — тоже"


@pytest.mark.asyncio
async def test_free_generator_works_when_explicitly_allowed(monkeypatch):
    monkeypatch.setattr("core.hixiit.free_draft_allowed", lambda: True)
    monkeypatch.setattr(mg, "_pollinations", lambda p, size="": "https://free/i.png")
    out = await mg.generate_image_ex("шашлык", platform="instagram")
    assert out["provider"] == "pollinations"
    assert out["fallback"] is True
    # Подмену не прячем: причина ухода от Higgsfield остаётся в ответе.
    assert "Unavailable model" in out["why"]


@pytest.mark.asyncio
async def test_higgsfield_result_is_labelled_by_its_real_provider(monkeypatch):
    async def hixiit_ok(*a, **k):
        return {"ok": True, "url": "https://hf/i.png", "provider": "higgsfield_mcp",
                "model": "soul_2"}

    monkeypatch.setattr("core.hixiit.generate", hixiit_ok)
    out = await mg.generate_image_ex("шашлык", platform="instagram")
    assert out["provider"] == "higgsfield_mcp"
    assert out["fallback"] is False


def test_journal_shows_who_drew_the_frame():
    """«cover» и «cover · pollinations» — разный результат."""
    from core import content_factory as cf
    import inspect
    src = inspect.getsource(cf._flush_steps)
    assert "provider" in src, "в журнал должен попадать исполнитель шага"
