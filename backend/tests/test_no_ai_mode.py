"""Работа без единого ИИ-провайдера: управление обязано остаться живым.

Требование заказчика: внешние ИИ — второстепенны, система должна работать и без
них. Публикация, очередь, задачи и отчёты не используют модели вообще; генерация
без ключей честно недоступна, но сообщает, что делать, а не падает «All AI providers failed».
"""
import pytest

from core import ai_router as ar
from core import intent
from core import command_center as cc

_AI_KEYS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY",
            "PERPLEXITY_API_KEY", "DEEPSEEK_API_KEY", "NVIDIA_API_KEY",
            "GROQ_API_KEY", "CEREBRAS_API_KEY", "OPENROUTER_API_KEY",
            "MISTRAL_API_KEY", "GITHUB_MODELS_TOKEN")


@pytest.fixture
def no_ai(monkeypatch):
    for k in _AI_KEYS:
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def with_ai(monkeypatch, no_ai):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")


def test_ai_available_reflects_keys(no_ai, monkeypatch):
    assert ar.ai_available() is False
    assert ar.available_providers() == []

    monkeypatch.setenv("GROQ_API_KEY", "k")
    assert ar.ai_available() is True
    assert "groq" in ar.available_providers()


@pytest.mark.asyncio
async def test_chat_without_ai_lists_working_commands(client, no_ai):
    """Ответ должен объяснять, что делать, а не сообщать о внутреннем сбое."""
    reply = await intent.chat_reply("привет, что ты умеешь")
    assert "/queue" in reply and "/tasks" in reply
    assert "Groq" in reply           # куда идти за бесплатным ключом
    assert "failed" not in reply.lower()


@pytest.mark.asyncio
async def test_direct_commands_still_route_without_ai(client, no_ai):
    """Правила маршрутизации работают без модели — это и есть «пульт без ИИ»."""
    assert await intent.route("сделай рилс про доставку") == "/factory доставку"
    assert intent.quick_route("покажи статус") is not None


@pytest.mark.asyncio
async def test_command_center_hands_the_task_to_claude(client, no_ai, monkeypatch):
    """Своих моделей нет — задачу ведёт Клод. Заводить задачу, которая
    гарантированно упадёт, всё так же нельзя: это мусор в журнале."""
    from core.task_manager import list_tasks
    from core import production_queue as pq

    async def yes(text):
        return True

    monkeypatch.setattr("core.notify.notify_owner", yes)
    before = len(await list_tasks(limit=200))

    res = await cc.run_command("сделай рилс про доставку", source="dashboard", mirror=False)

    assert res["reason"] == "escrow_claude"
    assert "Клоду" in res["reply"]
    assert "Groq" in res["reply"], "подсказка про бесплатный ключ никуда не делась"
    assert len(await list_tasks(limit=200)) == before      # задача не заведена

    queued = [j for j in await pq.jobs() if j["kind"] == "ai_task"]
    assert queued, "вопрос пропал: ни модели, ни очереди"


@pytest.mark.asyncio
async def test_router_error_says_no_keys_not_generic_failure(client, no_ai):
    with pytest.raises(RuntimeError) as e:
        await ar.ai_router.call("gpt-4o", "sys", "hi")
    msg = str(e.value)
    assert "Нет ни одного ключа" in msg
    assert "Groq" in msg


@pytest.mark.asyncio
async def test_publishing_works_without_ai(client, no_ai, monkeypatch):
    """Публикация — это API площадки, ИИ там не участвует вообще."""
    from core import publish_queue as pq
    from core.orchestrator import nexus_core

    async def ok(platform, text, image_url, video_url=""):
        return {"ok": True, "post_id": "p1", "post_url": "https://x/p1"}

    monkeypatch.setattr(nexus_core, "_publish_one", ok)
    pub_id = await pq.enqueue("telegram", "пост без ИИ")
    res = await pq.attempt(pub_id)
    assert res["ok"] is True


@pytest.mark.asyncio
async def test_health_reports_control_only_mode(client, no_ai):
    from core.health import overview
    ov = await overview()
    assert ov["ai"]["available"] is False
    assert ov["ai"]["mode"] == "control_only"


@pytest.mark.asyncio
async def test_health_reports_full_mode_with_key(client, with_ai):
    from core.health import overview
    ov = await overview()
    assert ov["ai"]["mode"] == "full"
    assert "groq" in ov["ai"]["providers"]
