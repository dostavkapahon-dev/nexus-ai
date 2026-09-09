"""Карусель — история, а не набор картинок (ТЗ §20 первого ТЗ, §19 второго).

Раньше «сделай карусель» шло по конвейеру Reels: четыре кадра раскадровки без
хука, структуры и призыва. Это не карусель, а обрезанный ролик.
"""
import json

import pytest

from core import creative_director as cd
from core.telegram_bot import slides_wanted


DECK = {
    "title": "5 ошибок в доставке",
    "visual_style": "тёплый свет, крупная типографика",
    "caption": "подпись",
    "slides": [
        {"n": 1, "role": "value", "text": "Ошибка 1", "image_prompt": "kitchen"},
        {"n": 2, "role": "value", "text": "Ошибка 2", "image_prompt": "courier"},
        {"n": 3, "role": "value", "text": "Пишите нам", "image_prompt": "phone"},
    ],
}


@pytest.fixture
def model(monkeypatch):
    def _set(payload):
        async def call(model, system, prompt):
            _set.prompt = prompt
            return {"text": json.dumps(payload, ensure_ascii=False)}
        monkeypatch.setattr("core.ai_router.ai_router.call", call)
    return _set


@pytest.mark.asyncio
async def test_first_slide_hooks_and_last_calls_to_action(client, model):
    """Модель путает роли, а от них зависит смысл: хук держит, CTA продаёт."""
    model(DECK)

    deck = await cd.build_carousel({"topic": "доставка"}, slides=3)

    assert deck["ok"]
    assert [s["role"] for s in deck["slides"]] == ["hook", "value", "cta"]
    assert [s["n"] for s in deck["slides"]] == [1, 2, 3]


@pytest.mark.asyncio
async def test_slide_count_is_respected(client, model):
    model(DECK)
    deck = await cd.build_carousel({"topic": "x"}, slides=2)
    assert len(deck["slides"]) == 2


@pytest.mark.asyncio
async def test_absurd_count_is_clamped(client, model):
    """«Карусель на 40 слайдов» — это счёт за генерацию, а не контент."""
    model({**DECK, "slides": DECK["slides"] * 20})
    deck = await cd.build_carousel({"topic": "x"}, slides=99)
    assert len(deck["slides"]) <= 10


@pytest.mark.asyncio
async def test_series_has_one_visual_style(client, model):
    model(DECK)
    deck = await cd.build_carousel({"topic": "x"}, slides=3)
    assert deck["visual_style"] == "тёплый свет, крупная типографика"


@pytest.mark.asyncio
async def test_without_model_carousel_is_not_invented(client, monkeypatch):
    """Пустой каркас честнее случайных картинок, которые примут за результат."""
    async def broken(*a, **k):
        raise RuntimeError("нет модели")

    monkeypatch.setattr("core.ai_router.ai_router.call", broken)

    deck = await cd.build_carousel({"topic": "x"}, slides=5)
    assert deck["ok"] is False and deck["slides"] == []


@pytest.mark.asyncio
async def test_slides_without_prompt_are_dropped(client, model):
    """Слайд без промпта — это пустая картинка в готовой карусели."""
    model({**DECK, "slides": [{"n": 1, "text": "без промпта"},
                              {"n": 2, "text": "есть", "image_prompt": "kitchen"}]})

    deck = await cd.build_carousel({"topic": "x"}, slides=5)
    assert len(deck["slides"]) == 1


def test_slide_count_is_read_from_the_phrase():
    """«На 7 слайдов» раньше просто игнорировалось."""
    assert slides_wanted("карусель на 7 слайдов") == 7
    assert slides_wanted("сделай карусель") == 7
    assert slides_wanted("карусель из 12 слайдов") == 10, "верхний предел"
    assert slides_wanted("3 слайда про кофе") == 3


@pytest.mark.asyncio
async def test_factory_uses_carousel_brief_not_reel_storyboard(client):
    """Ветка карусели должна брать свой бриф, а не раскадровку ролика."""
    import inspect
    from core import content_factory

    body = inspect.getsource(content_factory.run_factory)
    block = body[body.index("# 3b."):body.index("# 3c.")]

    assert "build_carousel" in block
    assert 'content_type == "carousel"' in block
