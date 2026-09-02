"""
Каждый вид контента доходит до согласования, а не только ролик.

Живой случай: «СОЗДАТЬ → Изображение» проходило весь конвейер — анализ, ТЗ,
обложка, кадры, вау-ревью — и падало на самом последнем шаге. Причина: переменная
с видео объявлялась внутри ветки «нужно видео», а шаг публикации смотрел на неё
всегда. Ролики этого не видели, поэтому ошибка жила незамеченной, а три формата
из пяти не работали вовсе.

Здесь прогоняются все виды — чтобы такой класс ошибок не мог вернуться.
"""
import pytest


async def _none():
    return None


@pytest.fixture
def factory(monkeypatch):
    """Конвейер без сети: модели, картинки и согласование подменены."""
    from core import content_factory as cf

    sent = {}

    async def analyze(topic):
        return {"theme": topic or "тема", "hook_text": "хук", "hook_type": "тайна",
                "image_prompt": "кадр", "instagram": {"caption": "подпись"},
                "telegram": {"post": "пост"}}

    async def brief(plan):
        return {"storyboard": [{"t": "0-3", "overlay": "хук", "image_prompt": "кадр"}],
                "cover_prompt": "обложка", "video_motion_prompt": "движение",
                "avatar_script": "сценарий"}

    async def wow(b):
        return {"score": 9}

    async def image(prompt, platform="instagram"):
        return "https://img/cover.png"

    async def clip(*a, **kw):
        return {"ok": True, "url": "https://cdn/clip.mp4", "provider": "test"}

    async def approval(text, media_url=None, platforms=None, kind="plan", ref=None,
                       **kw):
        sent.update({"media": media_url, "platforms": platforms, "text": text,
                     "image_prompt": kw.get("image_prompt", "")})
        return "pid-1"

    async def noop(*a, **kw):
        return None

    monkeypatch.setattr(cf, "_analyze", analyze)
    monkeypatch.setattr(cf, "_send_report", noop)
    monkeypatch.setattr("core.creative_director.build_brief", brief)
    monkeypatch.setattr("core.creative_director.wow_review", wow)
    monkeypatch.setattr("core.media_generator.generate_image", image)
    monkeypatch.setattr("core.media_generator.generate_clip", clip)
    # Без ключей видеосервисов конвейер выбирает бесплатное слайд-шоу — подменяем
    # и его, иначе проверка «ролик уходит видео» зависела бы от наличия ffmpeg.
    monkeypatch.setattr("core.video_assembly.assemble_slideshow", clip)
    monkeypatch.setattr("core.video_editor.ensure_local_video",
                        lambda vid: _none())
    monkeypatch.setattr("core.moderation.send_for_approval", approval)
    return sent


@pytest.mark.parametrize("kind,want_video,content_type", [
    ("изображение", False, "photo"),
    ("пост", False, "post"),
    ("карусель", False, "carousel"),
])
@pytest.mark.asyncio
async def test_every_kind_reaches_approval(client, factory, kind, want_video, content_type):
    """Именно здесь конвейер и падал: без видео шаг публикации не находил `vid`."""
    from core import content_factory as cf

    report = await cf.run_factory(topic=f"тест {kind}", platforms=["instagram"],
                                  dry_run=False, want_video=want_video,
                                  content_type=content_type)

    assert report["published"]["status"] == "awaiting_approval", report["published"]
    assert factory["media"] == "https://img/cover.png", "у изображения медиа — обложка"
    assert factory["platforms"] == ["instagram"]


@pytest.mark.asyncio
async def test_video_still_uses_the_clip(client, factory):
    from core import content_factory as cf

    report = await cf.run_factory(topic="ролик", platforms=["telegram"],
                                  dry_run=False, want_video=True)
    assert report["published"]["status"] == "awaiting_approval"
    assert factory["media"] == "https://cdn/clip.mp4", "ролик должен уйти видео, а не обложкой"


@pytest.mark.asyncio
async def test_report_survives_flat_publication(client, monkeypatch):
    """Отчёт молча не доходил: плоская запись о согласовании ломала перебор."""
    from core import content_factory as cf

    texts = []

    async def fake_send(chat_id, text, **kw):
        texts.append(text)
        return {}

    # Оба условия обязательны: без токена писать нечем, без адресата — некому.
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "777")
    monkeypatch.setattr("core.telegram_bot.send_message", fake_send)

    report = {"dry_run": False, "plan": {"theme": "тема"}, "strategy": {},
              "wow": {"score": 8}, "steps": [{"step": "analysis", "ok": True}],
              "published": {"status": "awaiting_approval", "pid": "p1",
                            "note": "ушло на согласование"}}
    await cf._send_report(report, ["instagram"])

    assert texts and "ушло на согласование" in texts[0]


@pytest.mark.asyncio
async def test_failure_message_names_the_error(client, monkeypatch):
    """«Не получилось выполнить шаг» без типа ошибки — тупик для разбора."""
    from core import task_manager as tm

    finished = {}

    async def catch(task_id, ok, note=""):
        finished.update({"ok": ok, "note": note})

    monkeypatch.setattr("core.task_feed.finish", catch)
    monkeypatch.setattr("core.task_feed.watching", lambda _tid: True)

    async def boom():
        raise UnboundLocalError("cannot access local variable 'vid'")

    task_id = await tm.create("factory", "падающая задача")
    await tm.run(task_id, boom)

    assert finished["ok"] is False
    assert "UnboundLocalError" in finished["note"]
