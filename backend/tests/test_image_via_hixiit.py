"""Картинки должны идти через HIXIIT, а короткое слово — превращаться в кадр.

Симптом: пишешь в Telegram «создать изображение» и одно слово — приходит
картинка не по теме. Причин было две: HIXIIT в цепочке генерации изображений
не участвовал вовсе (только видео), а голое русское слово уходило прямо в
генератор, обученный на английских описаниях.
"""
import pytest

from core import media_generator as mg


@pytest.mark.asyncio
async def test_image_goes_through_hixiit_first(client, monkeypatch):
    called = {}

    async def fake_hixiit(prompt, kind=None, ratio=None, allow_free=True, image_url=None):
        called.update(prompt=prompt, kind=kind, ratio=ratio, allow_free=allow_free)
        return {"ok": True, "url": "https://cdn/hf.png"}

    monkeypatch.setattr("core.hixiit.generate", fake_hixiit)
    monkeypatch.setattr(mg, "enrich_image_prompt", lambda p: _same(p))

    url = await mg.generate_image("кофе на столе", platform="instagram")

    assert url == "https://cdn/hf.png"
    assert called["kind"] == "image"
    assert called["ratio"] == "9:16", "вертикальный формат для Instagram"
    assert called["allow_free"] is False, "бесплатная подмена здесь только запутает"


async def _same(p):
    return p


@pytest.mark.asyncio
async def test_falls_back_when_hixiit_unavailable(client, monkeypatch):
    """HIXIIT не настроен — картинка всё равно должна получиться."""
    async def fake_hixiit(prompt, **kw):
        return {"ok": False, "error": "не настроен"}

    monkeypatch.setattr("core.hixiit.generate", fake_hixiit)
    monkeypatch.setattr(mg, "enrich_image_prompt", _same)
    for var in ("GEMINI_API_KEY", "OPENAI_API_KEY", "STABILITY_API_KEY"):
        monkeypatch.delenv(var, raising=False)

    url = await mg.generate_image("кофе")

    assert url.startswith("https://image.pollinations.ai")


@pytest.mark.asyncio
async def test_explicit_hixiit_is_not_silently_replaced(client, monkeypatch):
    """Выбрали HIXIIT явно — подменять его другим провайдером нельзя."""
    async def fake_hixiit(prompt, **kw):
        return {"ok": False, "error": "нет ключа"}

    monkeypatch.setattr("core.hixiit.generate", fake_hixiit)
    monkeypatch.setattr(mg, "enrich_image_prompt", _same)

    with pytest.raises(RuntimeError, match="HIXIIT"):
        await mg.generate_image("кофе", provider="hixiit")


def test_russian_is_always_rewritten_whatever_its_length():
    """Развёрнутая фраза по-русски раньше уходила в генератор как есть.

    Из-за отсечки по длине человек, описавший кадр подробно, получал результат
    хуже, чем от одного слова: модели изображений обучены на английском.
    """
    assert mg._needs_enrichment("кофе")
    assert mg._needs_enrichment("доставка еды")
    assert mg._needs_enrichment(
        "мужчина в фартуке варит кофе в маленькой кофейне ранним утром, "
        "тёплый свет из окна, пар над чашкой, крупный план рук")


def test_detailed_english_prompt_is_left_alone():
    """Готовое английское описание не переписываем — это чужой замысел."""
    assert not mg._needs_enrichment(
        "cinematic close-up of a barista pouring milk into a latte, warm morning light, shallow depth of field")


def test_short_english_prompt_is_expanded():
    assert mg._needs_enrichment("coffee")


@pytest.mark.asyncio
async def test_enrichment_expands_the_word(client, monkeypatch):
    async def fake_smart_text(task, system, prompt):
        return "cinematic close-up of hot coffee on a wooden table, morning light"

    monkeypatch.setattr("core.skills.smart_text", fake_smart_text)

    out = await mg.enrich_image_prompt("кофе")

    assert "coffee" in out.lower()


@pytest.mark.asyncio
async def test_enrichment_keeps_original_when_model_rambles(client, monkeypatch):
    """Модель ответила рассуждением — доверять такому нельзя."""
    async def rambling(task, system, prompt):
        return "Конечно! " + "слово " * 200

    monkeypatch.setattr("core.skills.smart_text", rambling)

    assert await mg.enrich_image_prompt("кофе") == "кофе"


@pytest.mark.asyncio
async def test_long_russian_phrase_is_translated(client, monkeypatch):
    """Главный случай: человек пишет по-русски развёрнуто и ждёт свой кадр."""
    seen = {}

    async def fake_smart_text(task, system, prompt):
        seen["prompt"] = prompt
        return ("cinematic close-up of a barista brewing coffee in a small cafe at "
                "dawn, warm window light, steam above the cup")

    monkeypatch.setattr("core.skills.smart_text", fake_smart_text)

    out = await mg.enrich_image_prompt(
        "мужчина в фартуке варит кофе в маленькой кофейне ранним утром, "
        "тёплый свет из окна, пар над чашкой, крупный план рук")

    assert not mg.has_cyrillic(out), "в генератор должен уйти английский текст"
    assert "barista" in out.lower()
    assert "кофейне" in seen["prompt"], "модели передан исходный русский запрос"


@pytest.mark.asyncio
async def test_russian_answer_from_the_model_is_rejected(client, monkeypatch):
    """Модель ответила по-русски — такой «перевод» генератору не поможет."""
    async def still_russian(task, system, prompt):
        return "крупный план чашки кофе на деревянном столе, утренний свет"

    monkeypatch.setattr("core.skills.smart_text", still_russian)

    assert await mg.enrich_image_prompt("кофе") == "кофе"


@pytest.mark.asyncio
async def test_video_prompt_in_russian_is_translated_too(client, monkeypatch):
    """Видео идёт в те же модели — русский текст там та же проблема."""
    from core import hixiit

    sent = {}

    async def fake_smart_text(task, system, prompt):
        return "vertical cinematic shot of coffee being poured, slow motion"

    async def fake_mcp(tool, args, timeout=600.0):
        if tool == "models_explore":
            return {"items": [{"id": "seedance",
                               "parameters": [{"name": "prompt", "required": "required"}]}]}
        sent.update(args)
        return {"result": {"video_url": "https://cdn/x.mp4"}}

    monkeypatch.setattr("core.skills.smart_text", fake_smart_text)
    monkeypatch.setattr(hixiit, "_mcp_call", fake_mcp)
    monkeypatch.setenv("HIGGSFIELD_MCP_URL", "https://mcp.example/x")

    res = await hixiit.generate("сделай вертикальный ролик про кофе")

    assert res["ok"] and res["kind"] == "video", "тип задачи виден по русскому тексту"
    assert not hixiit_has_cyrillic(sent["prompt"]), "в модель должен уйти английский промпт"


def hixiit_has_cyrillic(text: str) -> bool:
    return any("Ѐ" <= c <= "ӿ" for c in text or "")
