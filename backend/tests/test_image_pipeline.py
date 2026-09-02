"""Картинка соответствует заданию, правится по замечанию и делается в HiggsField.

Три жалобы пользователя:
  1) «делает картинки, но не совсем то, что я сказал» — слова человека затирались
     пересказом дешёвой модели, а промпт анализа велел «придумай тему»;
  2) «не редактируется после» — правка дописывала текст и переприсылала ту же
     самую картинку, замечание по визуалу не делало ничего;
  3) генерация должна идти в HiggsField с выбором модели под задачу.
"""
import pytest

from core import content_factory as cf
from core import higgsfield, media_generator, moderation
from database.db import init_db


# ─────────── 1. задание человека доживает до промпта картинки ───────────

@pytest.mark.asyncio
async def test_user_words_are_not_replaced_by_the_rewrite(monkeypatch):
    """Уточнение дописывается, а не подменяет собой сказанное. Иначе дальше по
    конвейеру едет пересказ пересказа."""
    seen = {}

    async def fake_pre_check(agent, task, context="", model=None):
        return {"checked": True, "ready": True,
                "improved_task": "Сделать креатив про технологии"}

    async def fake_analyze(topic):
        seen["topic"] = topic
        return {"theme": "t", "hook_text": "h", "image_prompt": "p"}

    async def fake_brief(plan):
        return {"storyboard": [], "cover_prompt": "c", "avatar_script": "s"}

    async def fake_wow(b):
        return {"score": 9}

    async def fake_image(prompt, platform="instagram", **kw):
        return "https://img/x.png"

    async def fake_clip(*a, **kw):
        return {"ok": True, "url": "https://cdn/c.mp4"}

    monkeypatch.setattr("core.self_critique.pre_check", fake_pre_check)
    monkeypatch.setattr(cf, "_analyze", fake_analyze)
    # Остальной конвейер глушим: проверяем путь ЗАДАНИЯ, а не всю фабрику.
    # Без этого тест дёргает настоящие модели — на CI это минуты ожидания
    # и зависимость прогона от чужих сервисов.
    monkeypatch.setattr("core.creative_director.build_brief", fake_brief)
    monkeypatch.setattr("core.creative_director.wow_review", fake_wow)
    monkeypatch.setattr("core.media_generator.generate_image", fake_image)
    monkeypatch.setattr("core.media_generator.generate_clip", fake_clip)
    await init_db()
    await cf.run_factory(topic="красный самокат у подъезда, ночь", dry_run=True)

    assert "красный самокат у подъезда, ночь" in seen["topic"], "слова человека потеряны"
    assert "Уточнение" in seen["topic"], "уточнение должно дописываться"


@pytest.mark.asyncio
async def test_prompt_makes_the_request_binding():
    """Модели должно быть сказано работать с заданием, а не придумывать своё."""
    text = cf._ANALYSIS_PROMPT
    assert "Подготовь" in text and "Придумай ОДНУ тему" not in text
    assert "ИМЕННО ТО, что просил человек" in text.replace("\n", " "), \
        "промпт обложки не привязан к заданию"


# ─────────────── 2. правка перерисовывает картинку ───────────────

def test_visual_remarks_are_recognised():
    assert moderation._about_image("поменяй фон на ночной")
    assert moderation._about_image("другой ракурс")
    assert moderation._about_image("change the background")


def test_text_remarks_do_not_trigger_redraw():
    """Перерисовывать кадр из-за правки подписи — жечь деньги впустую."""
    assert not moderation._about_image("убери последний абзац")
    assert not moderation._about_image("добавь призыв подписаться")


@pytest.mark.asyncio
async def test_visual_correction_redraws_from_the_original(monkeypatch):
    """Ключевое: правка идёт image-to-image от исходного кадра. Раньше сюда
    переприсылался тот же media_url, то есть не менялось ничего."""
    await init_db()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")

    async def fake_tg(method, payload):
        return {"ok": True}

    monkeypatch.setattr(moderation, "_tg", fake_tg)

    called = {}

    async def fake_revise(image_url, correction, base_prompt="", platform="instagram"):
        called.update({"src": image_url, "correction": correction,
                       "base": base_prompt})
        return {"ok": True, "url": "https://cdn/fixed.png", "model": "nano_banana_2"}

    monkeypatch.setattr("core.media_generator.revise_image", fake_revise)

    pid = await moderation.send_for_approval(
        "текст поста", media_url="https://cdn/first.png", kind="factory",
        image_prompt="scooter at night")
    await moderation.request_fix(pid)
    answer = await moderation.apply_fix("поменяй фон на дневной")

    assert called["src"] == "https://cdn/first.png", "правка не от исходного кадра"
    assert called["base"] == "scooter at night", "замысел сцены потерян"
    assert "перерисовал" in answer

    queue = await moderation.kv.get(moderation.QUEUE_KEY, {})
    assert any(i["media_url"] == "https://cdn/fixed.png" for i in queue.values())


@pytest.mark.asyncio
async def test_failed_redraw_is_said_out_loud(monkeypatch):
    await init_db()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    monkeypatch.setattr(moderation, "_tg", lambda m, p: _ok())

    async def failing(image_url, correction, base_prompt="", platform="instagram"):
        return {"ok": False, "error": "нужен HIGGSFIELD_API_KEY"}

    monkeypatch.setattr("core.media_generator.revise_image", failing)

    pid = await moderation.send_for_approval("текст", media_url="https://cdn/a.png",
                                             kind="factory")
    await moderation.request_fix(pid)
    answer = await moderation.apply_fix("смени цвет фона")

    assert "не вышло" in answer and "HIGGSFIELD_API_KEY" in answer


async def _ok():
    return {"ok": True}


@pytest.mark.asyncio
async def test_revision_without_higgsfield_refuses_honestly(monkeypatch):
    """Бесплатный генератор умеет рисовать заново, но не править. Молчать об
    этом нельзя: человек решит, что правку применили."""
    monkeypatch.delenv("HIGGSFIELD_API_KEY", raising=False)
    res = await media_generator.revise_image("https://cdn/a.png", "поменяй фон")
    assert res["ok"] is False and "HIGGSFIELD_API_KEY" in res["error"]


# ─────────────── 3. модель подбирается под задачу ───────────────

def test_model_matches_the_task():
    assert higgsfield.pick_image_model("постер с крупной надписью СКИДКА") == "nano_banana_2"
    assert higgsfield.pick_image_model("упаковка продукта на столе") == "marketing_studio_image"
    assert higgsfield.pick_image_model("кинематографичный кадр города") == "cinematic_studio_2_5"


def test_draft_goes_to_the_cheap_model():
    """Смысл первой генерации — проверить композицию, а не получить финал."""
    assert higgsfield.pick_image_model("любая сцена", draft=True) == "nano_banana_flash"


def test_trained_character_wins_over_everything():
    assert higgsfield.pick_image_model("постер с надписью", soul_id="abc") == "soul_2"


def test_every_chosen_model_is_in_the_catalogue():
    """Подсказка, ведущая на несуществующую модель, — совет, который не исполнится."""
    for prompt in ("надпись", "продукт", "cinematic", "обычная сцена"):
        assert higgsfield.pick_image_model(prompt) in higgsfield.IMAGE_MODELS


@pytest.mark.asyncio
async def test_higgsfield_is_first_in_the_chain(monkeypatch):
    """Ключ есть — значит картинку делает он, а не бесплатный запасной путь."""
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "k")
    for k in ("GEMINI_API_KEY", "OPENAI_API_KEY", "STABILITY_API_KEY"):
        monkeypatch.delenv(k, raising=False)

    async def fake_image(prompt, ratio="9:16", **kw):
        return {"ok": True, "url": "https://hf/out.png", "model": "nano_banana_2"}

    monkeypatch.setattr(higgsfield, "image", fake_image)

    async def noop_track(*a, **kw):
        return None

    monkeypatch.setattr(media_generator, "_track_media", noop_track)
    url = await media_generator.generate_image("сцена", platform="instagram")
    assert url == "https://hf/out.png"
