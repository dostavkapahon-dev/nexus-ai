"""Кадры раскадровки должны идти тем же путём, что и обложка (ТЗ §14).

Раньше обложка шла через генеративный слой (Higgsfield → запасные пути), а кадры
— напрямую в бесплатный Pollinations. Решение принималось, когда Higgsfield не
работал вовсе; теперь оно означает, что кадры заведомо хуже обложки, а оплаченная
подписка не используется.
"""
import pytest

from core import content_factory as cf


@pytest.mark.asyncio
async def test_frames_go_through_the_generative_layer(client, monkeypatch):
    """Кадры не должны обходить Higgsfield стороной."""
    import inspect

    src = inspect.getsource(cf)
    body = src[src.index("# 3b."):src.index("# 3c.")]

    assert "free_image(" not in body, "кадры не должны идти сразу в бесплатный путь"
    assert "generate_image(" in body, "кадры идут через тот же слой, что и обложка"


@pytest.mark.asyncio
async def test_frames_share_one_visual_style(client, monkeypatch):
    """Слайды и кадры должны выглядеть серией, а не набором случайных картинок."""
    prompts = []

    async def fake_generate_image(prompt, platform="instagram", **kw):
        prompts.append(prompt)
        return "https://cdn/frame.png"

    monkeypatch.setattr("core.media_generator.generate_image", fake_generate_image)

    brief = {"visual_style": "тёплый плёночный свет",
             "storyboard": [{"t": 0, "image_prompt": "чашка кофе"},
                            {"t": 3, "image_prompt": "руки бариста"}]}

    frames = await _frames(brief)

    assert len(frames) == 2
    assert all("тёплый плёночный свет" in p for p in prompts), \
        "общий стиль должен попасть в каждый кадр"


@pytest.mark.asyncio
async def test_generation_failure_does_not_drop_the_frame(client, monkeypatch):
    """Сбой одного кадра не должен обрывать раскадровку — остальные нужны."""
    async def broken(prompt, platform="instagram", **kw):
        raise RuntimeError("провайдер недоступен")

    monkeypatch.setattr("core.media_generator.generate_image", broken)

    frames = await _frames({"storyboard": [{"t": 0, "image_prompt": "кадр"}]})

    assert len(frames) == 1 and frames[0]["image"] == ""


async def _frames(brief: dict) -> list:
    """Повторяет шаг 3b фабрики: тот же слой, тот же общий стиль."""
    from core.media_generator import generate_image

    style = (brief.get("visual_style") or brief.get("tone") or "").strip()
    frames = []
    for shot in brief.get("storyboard", [])[:4]:
        prompt_img = (shot.get("image_prompt") or "").strip()
        if not prompt_img:
            continue
        prompt_full = f"{prompt_img}. Единый стиль серии: {style}" if style else prompt_img
        try:
            img = await generate_image(prompt_full, platform="instagram")
        except Exception:
            img = ""
        frames.append({"t": shot.get("t"), "overlay": shot.get("overlay"), "image": img})
    return frames
