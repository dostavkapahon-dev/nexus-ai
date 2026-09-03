"""
Контент создаётся всегда: с моделями — умно, без моделей — по шаблону.

Живая жалоба: «создаю креатив — он не генерирует». Причина была в том, что без
ключа ИИ конвейер отдавал пустую заглушку («AI для бизнеса», нулевая
раскадровка) и считал это провалом, а человеку не говорил ничего. Теперь без
моделей собирается осмысленная заготовка по заданной теме, а система заранее
предупреждает, чего ей не хватает.
"""
import pytest

from core import offline_content, preflight


@pytest.fixture(autouse=True)
def _no_ai(monkeypatch):
    monkeypatch.setattr("core.ai_router.available_providers", lambda: [])


# ─────────────────────────── заготовка ───────────────────────────

def test_draft_is_about_the_topic_not_about_ai_in_general():
    d = offline_content.draft("шашлык на углях")
    assert "шашлык на углях" in d["hook_text"] or "шашлык на углях" in d["caption"]
    assert d["theme"] == "шашлык на углях"
    assert len(d["storyboard"]) == 4, "без раскадровки не будет ни кадров, ни видео"
    assert all(s["image_prompt"] for s in d["storyboard"])


def test_draft_admits_it_is_a_draft():
    assert "без моделей" in offline_content.draft("кофейня")["note"].lower()


@pytest.mark.asyncio
async def test_build_makes_pictures_without_any_key(monkeypatch):
    async def no_video(frames, cta_text=""):
        return {"ok": False, "error": "ffmpeg недоступен"}

    monkeypatch.setattr("core.video_assembly.assemble_slideshow", no_video)

    out = await offline_content.build("доставка за 15 минут")
    assert out["ok"] and out["offline"]
    assert out["assets"]["cover"].startswith("http")
    assert len(out["assets"]["frames"]) == 4
    assert "ffmpeg" in out["plan"]["note"], "неудачу монтажа нельзя выдавать за ролик"


# ─────────────────────────── конвейер без ключей ───────────────────────────

@pytest.mark.asyncio
async def test_factory_without_ai_returns_usable_content(client, monkeypatch):
    """Раньше здесь была заглушка «AI для бизнеса» и ok=false."""
    from core import content_factory as cf

    async def dead_model(*a, **kw):
        raise RuntimeError("Нет ни одного ключа ИИ")

    monkeypatch.setattr("core.ai_router.ai_router.call", dead_model)

    report = await cf.run_factory(topic="кофейня у дома", platforms=["telegram"],
                                  dry_run=True, want_video=False)

    assert report["ok"] is True, "конвейер обязан довести до результата"
    assert report["offline"] is True
    assert report["plan"]["theme"] == "кофейня у дома"
    assert "кофейня у дома" in report["plan"]["instagram"]["caption"]
    assert report["brief"]["storyboard"], "пустая раскадровка = нет кадров"
    assert "бесплатный ключ" in report["hint"], "человек должен знать, как улучшить"


# ─────────────────────────── проверка готовности ───────────────────────────

@pytest.mark.asyncio
async def test_preflight_warns_but_does_not_block(client):
    rep = await preflight.check("video")
    assert rep["ok"] is True, "отсутствие ключей больше не повод отказывать"
    assert any("модели ИИ" in w for w in rep["warnings"])
    assert any("Изображения" in r for r in rep["ready"])


@pytest.mark.asyncio
async def test_preflight_text_is_readable(client):
    text = preflight.as_text(await preflight.check("video"))
    assert "Готово к работе" in text and "оговорками" in text


@pytest.mark.asyncio
async def test_preflight_endpoint(auth_client):
    body = (await auth_client.get("/api/system/preflight")).json()
    assert "warnings" in body and "ready" in body


@pytest.mark.asyncio
async def test_create_tells_about_limits_before_starting(client, monkeypatch):
    """Предупреждение должно прийти до запуска, а не вместо результата."""
    from core import telegram_bot as tb

    sent = []

    async def fake_send(chat_id, text, **kw):
        sent.append(text)
        return {}

    async def fake_spawn(kind, goal, fn, **kw):
        sent.append("SPAWNED")
        return "t1"

    async def fake_feed(task_id, chat_id, title, kind="video"):
        return None

    monkeypatch.setattr(tb, "send_message", fake_send)
    monkeypatch.setattr("core.task_manager.spawn", fake_spawn)
    monkeypatch.setattr("core.task_feed.start", fake_feed)

    await tb._start_creation("900", "video", "instagram", "кофейня")

    assert any("оговорками" in s for s in sent), "человек не предупреждён"
    assert "SPAWNED" in sent, "предупреждение не должно отменять работу"
    assert sent.index(next(s for s in sent if "оговорками" in s)) < sent.index("SPAWNED")
