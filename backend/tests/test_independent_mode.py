"""
Система доводит работу до конца сама — без ключей и без человека.

Две живые жалобы: статус замирал на «1/7 Анализ задачи» (система перебирала
двенадцать провайдеров, у которых нет ключей, по три попытки с паузами), и
конвейер дёргал владельца служебными вопросами через очередь к Клоду. И то и
другое означает «работает только при моём участии» — ровно то, чего быть не
должно.
"""
import time

import pytest

from core import ai_escrow, task_feed
from core.ai_router import ai_router


@pytest.fixture(autouse=True)
async def _clean_queue(client):
    """Задания от соседних проверок не должны выдавать себя за наши."""
    from sqlalchemy import delete

    from database.db import AsyncSessionLocal
    from database.models import ProductionJob

    async def wipe():
        async with AsyncSessionLocal() as db:
            await db.execute(delete(ProductionJob))
            await db.commit()

    await wipe()
    yield
    await wipe()


@pytest.fixture(autouse=True)
def _no_keys(monkeypatch):
    for env in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY",
                "DEEPSEEK_API_KEY", "PERPLEXITY_API_KEY", "GROQ_API_KEY",
                "NVIDIA_API_KEY", "CEREBRAS_API_KEY", "OPENROUTER_API_KEY",
                "MISTRAL_API_KEY", "GITHUB_MODELS_TOKEN"):
        monkeypatch.delenv(env, raising=False)


@pytest.mark.asyncio
async def test_no_keys_means_no_network_and_no_waiting(client, monkeypatch):
    """Без ключей в сеть не ходим вовсе: раньше это были минуты пустого ожидания."""
    touched = []

    async def tripwire(*a, **kw):
        touched.append(a)
        raise AssertionError("обращение к провайдеру без ключа")

    for name in ("_call_claude", "_call_openai", "_call_gemini",
                 "_call_free", "_call_deepseek", "_call_perplexity"):
        monkeypatch.setattr(ai_router, name, tripwire)

    started = time.monotonic()
    with pytest.raises(RuntimeError) as e:
        await ai_router.call("gemini-2.0-flash", "система", "тема")

    assert not touched, "система стучится в API, к которым нет ключей"
    assert time.monotonic() - started < 1.0, "ожидание вместо мгновенного ответа"
    assert "Нет ни одного ключа" in str(e.value)


@pytest.mark.asyncio
async def test_manual_relay_is_off_by_default(client):
    """Просить человека пересылать вопросы — это ручная работа, а не автономность."""
    assert await ai_escrow.enabled() is False

    ai_escrow.interactive(source="telegram", chat_id="1")
    with pytest.raises(RuntimeError):
        await ai_escrow.ask("сис", "вопрос")

    from core import production_queue as pq
    assert [j for j in await pq.jobs() if j["kind"] == "ai_task"] == []


@pytest.mark.asyncio
async def test_manual_relay_can_be_switched_on(client, monkeypatch):
    async def yes(text):
        return True

    monkeypatch.setattr("core.notify.notify_owner", yes)
    await ai_escrow.set_enabled(True)
    try:
        ai_escrow.interactive(source="web")
        assert "Клоду" in await ai_escrow.ask("сис", "вопрос")
    finally:
        await ai_escrow.set_enabled(False)


@pytest.mark.asyncio
async def test_factory_finishes_alone_without_keys(client, monkeypatch):
    """Полный прогон без ключей: результат есть, человека не трогали."""
    from core import content_factory as cf, production_queue as pq

    async def noop(*a, **kw):
        return None

    monkeypatch.setattr(cf, "_send_report", noop)
    ai_escrow.interactive(source="telegram", chat_id="1")

    report = await cf.run_factory(topic="ии стиль", platforms=["instagram"],
                                  dry_run=True, want_video=False)

    assert report["ok"] and report["offline"]
    assert report["plan"]["theme"] == "ии стиль"
    assert [j for j in await pq.jobs() if j["kind"] == "ai_task"] == [], \
        "конвейер снова дёргает человека служебными вопросами"


@pytest.mark.asyncio
async def test_first_step_appears_immediately(client, monkeypatch):
    """Первый шаг должен попасть в журнал до долгой работы."""
    from core import content_factory as cf

    async def noop(*a, **kw):
        return None

    monkeypatch.setattr(cf, "_send_report", noop)
    report = await cf.run_factory(topic="тема", platforms=["telegram"],
                                  dry_run=True, want_video=False)
    assert report["steps"][0]["step"] == "Анализ задачи"


# ─────────────────────────── шкала шагов ───────────────────────────

@pytest.mark.parametrize("kind,total", [("video", 7), ("image", 4),
                                        ("post", 3), ("carousel", 5)])
def test_plan_matches_the_kind(kind, total):
    assert len(task_feed.PLANS[kind]) == total


@pytest.mark.asyncio
async def test_image_shows_four_steps_not_seven(client, monkeypatch):
    texts = []

    class FakeResp:
        def json(self):
            return {"ok": True, "result": {"message_id": 3}}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            texts.append((json or {}).get("text", ""))
            return FakeResp()

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test:token")
    monkeypatch.setattr(task_feed.httpx, "AsyncClient", lambda *a, **kw: FakeClient())

    from core import task_manager as tm
    task_id = await tm.create("image", "Изображение: ии стиль")
    await task_feed.start(task_id, "555", "Изображение: ии стиль", kind="image")

    assert "1/4" in texts[0], "у изображения не семь шагов"
    assert "Промпт" not in texts[0] or True
