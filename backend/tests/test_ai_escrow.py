"""
Запрос человека всегда находит мозг: своя модель — или Клод.

Смысл: если ни один провайдер не ответил, вопрос из Telegram или с сайта не
должен превращаться в отказ «ни один ИИ не подключён». Он уходит в очередь
Клоду и возвращается ответом туда же, откуда пришёл.
"""
import pytest
import pytest_asyncio
from sqlalchemy import delete

from core import ai_escrow, production_queue as pq
from core.ai_router import ai_router
from database.db import AsyncSessionLocal
from database.models import ProductionJob


@pytest_asyncio.fixture(autouse=True)
async def _relay_on(client):
    """Ручная передача выключена по умолчанию — здесь проверяется именно она."""
    await ai_escrow.set_enabled(True)
    yield
    await ai_escrow.set_enabled(False)


@pytest_asyncio.fixture(autouse=True)
async def _clean(client):
    async def wipe():
        async with AsyncSessionLocal() as db:
            await db.execute(delete(ProductionJob))
            await db.commit()
    await wipe()
    yield
    await wipe()


@pytest.fixture(autouse=True)
def _short_chain(monkeypatch):
    """Перебор укорачиваем: проверяем поведение в конце цепочки, а не её длину."""
    monkeypatch.setattr("core.ai_router.FALLBACK_CHAIN", ["gemini-2.0-flash"])


@pytest.fixture(autouse=True)
def _no_keys(monkeypatch):
    """Ни одного ключа — самый тяжёлый случай."""
    for env in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY",
                "DEEPSEEK_API_KEY", "PERPLEXITY_API_KEY", "GROQ_API_KEY",
                "NVIDIA_API_KEY", "CEREBRAS_API_KEY", "OPENROUTER_API_KEY",
                "MISTRAL_API_KEY", "GITHUB_MODELS_TOKEN"):
        monkeypatch.delenv(env, raising=False)


@pytest.mark.asyncio
async def test_failed_call_goes_to_claude_instead_of_raising(client, monkeypatch):
    told = []
    monkeypatch.setattr("core.notify.notify_owner",
                        lambda text: told.append(text) or _true())

    # Ключ есть, но провайдер отказал — вот когда очередь к Клоду и нужна.
    # Полное отсутствие ключей ведёт себя иначе: в сеть не идём вовсе.
    monkeypatch.setenv("GEMINI_API_KEY", "k")

    async def refuse(*a, **kw):
        raise RuntimeError("503 service unavailable")

    monkeypatch.setattr(ai_router, "_call_gemini", refuse)
    monkeypatch.setattr("core.ai_router.FALLBACK_CHAIN", ["gemini-2.0-flash"])
    monkeypatch.setattr("asyncio.sleep", lambda *_: _true())

    ai_escrow.interactive(source="telegram", chat_id="42")
    res = await ai_router.call("gemini-2.0-flash", "система", "сделай контент-план")

    assert res["escrow"] is True
    assert "Клоду" in res["text"], "человек должен понимать, куда ушёл его запрос"

    jobs = await pq.jobs()
    assert len(jobs) == 1 and jobs[0]["kind"] == ai_escrow.KIND
    assert jobs[0]["brief"]["prompt"] == "сделай контент-план"
    assert jobs[0]["brief"]["chat_id"] == "42", "ответ должен вернуться в тот же чат"
    assert told, "владелец не узнал, что нужен Клод"


async def _true():
    return True


@pytest.mark.asyncio
async def test_background_step_still_fails_loudly(client):
    """Фоновому шагу ждать человека бессмысленно — очередь не должна расти."""
    ai_escrow._interactive.set(False)

    with pytest.raises(RuntimeError):
        await ai_router.call("gemini-2.0-flash", "система", "фоновая работа")

    assert await pq.jobs() == []


@pytest.mark.asyncio
async def test_same_question_is_not_queued_twice(client, monkeypatch):
    monkeypatch.setattr("core.notify.notify_owner", lambda text: _true())
    ai_escrow.interactive(source="web")

    await ai_escrow.ask("сис", "один и тот же вопрос")
    await ai_escrow.ask("сис", "один и тот же вопрос")

    assert len(await pq.jobs()) == 1, "очередь заливает дубликатами"


@pytest.mark.asyncio
async def test_answer_comes_back_to_the_asker(auth_client, monkeypatch):
    sent = {}

    async def fake_send(chat_id, text, **kw):
        sent["chat"] = chat_id
        sent["text"] = text
        return {}

    monkeypatch.setattr("core.telegram_bot.send_message", fake_send)
    monkeypatch.setattr("core.notify.notify_owner", lambda text: _true())

    ai_escrow.interactive(source="telegram", chat_id="99")
    await ai_escrow.ask("сис", "что постить завтра?")
    job = (await pq.jobs())[0]

    r = await auth_client.post(f"/api/production/{job['id']}/result",
                               json={"text": "Три идеи: ..."})
    body = r.json()
    assert body["ok"] and body["next"]["status"] == "delivered"
    assert sent["chat"] == "99" and "Три идеи" in sent["text"]


@pytest.mark.asyncio
async def test_text_task_does_not_trigger_video_montage(auth_client, monkeypatch):
    """Ответ текстом монтировать нечего — конвейер роликов трогать нельзя."""
    montage = []

    async def fake_finalize(job):
        montage.append(job)
        return {"status": "awaiting_approval"}

    monkeypatch.setattr("core.content_factory.finalize_from_assets", fake_finalize)
    monkeypatch.setattr("core.telegram_bot.send_message",
                        lambda *a, **kw: _true())
    monkeypatch.setattr("core.notify.notify_owner", lambda text: _true())

    ai_escrow.interactive(source="web")
    await ai_escrow.ask("сис", "вопрос без чата")
    job = (await pq.jobs())[0]

    await auth_client.post(f"/api/production/{job['id']}/result", json={"text": "ответ"})
    assert not montage


@pytest.mark.asyncio
async def test_question_is_readable_for_claude(client, monkeypatch):
    monkeypatch.setattr("core.notify.notify_owner", lambda text: _true())
    ai_escrow.interactive(source="web")
    await ai_escrow.ask("Ты — дирижёр", "собери план на неделю",
                        errors="429 у всех провайдеров")

    job = (await pq.jobs())[0]
    text = pq.brief_as_text(job["brief"])
    assert "собери план на неделю" in text and "дирижёр" in text
    assert "429" in text, "почему позвали Клода — важно для ответа"
