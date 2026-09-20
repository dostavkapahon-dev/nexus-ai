"""Исчерпанная квота — переключение мгновенное, а не «запрос, ожидание, 429».

Фолбэк работал и раньше, но дохлый провайдер пробовался заново на каждом
вызове. В конвейере из десятка шагов это десяток потерянных сетевых ожиданий
подряд — и выглядит как «задача думает».
"""
import time

import pytest

from core import ai_router as ar


@pytest.fixture(autouse=True)
def clean():
    ar._EXHAUSTED.clear()
    yield
    ar._EXHAUSTED.clear()


def test_quota_errors_are_recognised():
    for text in ("429 You exceeded your current quota",
                 "RESOURCE_EXHAUSTED", "insufficient_quota",
                 "Rate limit exceeded"):
        assert ar._is_quota(text), text


def test_a_broken_model_is_not_a_dead_provider():
    """«Модели нет» — беда модели, у провайдера квота цела."""
    assert ar._is_dead_model("model not found") is True
    assert ar._is_quota("model not found") is False


def test_exhausted_provider_is_skipped_until_it_cools():
    ar.mark_exhausted("gemini", "429 quota")
    assert ar.exhausted_for("gemini") > 0
    assert "gemini" in ar.exhausted_providers()
    assert ar.exhausted_for("groq") == 0


def test_cooldown_expires(monkeypatch):
    ar.mark_exhausted("gemini", "429")
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + ar.QUOTA_COOLDOWN_SEC + 1)
    assert ar.exhausted_for("gemini") == 0
    assert ar.exhausted_providers() == {}


@pytest.mark.asyncio
async def test_quota_marks_the_provider_and_the_next_call_skips_it(monkeypatch):
    tried = []

    async def gemini(self, model, system, prompt):
        tried.append(("gemini", model))
        raise RuntimeError("429 You exceeded your current quota")

    async def free(self, model, system, prompt):
        tried.append(("free", model))
        return {"text": "ответ", "tokens": 1, "cost": 0.0, "model_used": model}

    monkeypatch.setattr(ar.AIRouter, "_call_gemini", gemini)
    monkeypatch.setattr(ar.AIRouter, "_call_free", free)
    monkeypatch.setattr(ar, "_has_key", lambda m: True)
    monkeypatch.setattr(ar, "AI_ROUTING", {"gemini-x": "gemini", "groq-x": "groq"})
    monkeypatch.setattr(ar, "FALLBACK_CHAIN", ["gemini-x", "groq-x"])
    monkeypatch.setattr(ar, "FREE_PROVIDERS", {"groq": {}})

    async def no_track(*a, **k):
        return None
    monkeypatch.setattr(ar, "_track", no_track)

    router = ar.AIRouter()
    first = await router.call("gemini-x", "sys", "hi")
    assert first["text"] == "ответ"
    # Вторая попытка гемини не делается: квота у провайдера, а не у модели.
    assert [p for p, _ in tried].count("gemini") == 1

    tried.clear()
    second = await router.call("gemini-x", "sys", "hi")
    assert second["text"] == "ответ"
    assert not [p for p, _ in tried if p == "gemini"], \
        "исчерпанный провайдер не должен пробоваться снова"


@pytest.mark.asyncio
async def test_when_everyone_is_exhausted_we_still_try(monkeypatch):
    """Память могла устареть: отказ лучше отдать от живого запроса."""
    calls = []

    async def gemini(self, model, system, prompt):
        calls.append(model)
        return {"text": "снова работает", "tokens": 1, "cost": 0.0,
                "model_used": model}

    monkeypatch.setattr(ar.AIRouter, "_call_gemini", gemini)
    monkeypatch.setattr(ar, "_has_key", lambda m: True)
    monkeypatch.setattr(ar, "AI_ROUTING", {"gemini-x": "gemini"})
    monkeypatch.setattr(ar, "FALLBACK_CHAIN", ["gemini-x"])

    async def no_track(*a, **k):
        return None
    monkeypatch.setattr(ar, "_track", no_track)

    ar.mark_exhausted("gemini", "429")
    res = await ar.AIRouter().call("gemini-x", "sys", "hi")
    assert res["text"] == "снова работает" and calls
