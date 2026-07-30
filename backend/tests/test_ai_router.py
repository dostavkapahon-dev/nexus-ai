import pytest

from core import ai_router as ar


@pytest.fixture
def no_backoff(monkeypatch):
    """Паузы между повторами не нужны в тестах."""
    async def instant(_seconds):
        return None

    monkeypatch.setattr(ar.asyncio, "sleep", instant)


@pytest.fixture
def router(monkeypatch):
    for env in ar.PROVIDER_KEY_ENV.values():
        monkeypatch.delenv(env, raising=False)
    monkeypatch.setattr(ar, "_GEMINI_RESOLVED", None)
    return ar.AIRouter()


def _stub_calls(monkeypatch, behaviour):
    """behaviour: model -> либо текст ответа, либо Exception."""
    seen = []

    async def fake(self, model, system, prompt):
        seen.append(model)
        out = behaviour.get(model, RuntimeError("not stubbed"))
        if isinstance(out, Exception):
            raise out
        return {"text": out, "tokens": 10, "cost": 0.0, "model_used": model}

    for name in ("_call_claude", "_call_openai", "_call_gemini",
                 "_call_perplexity", "_call_deepseek"):
        monkeypatch.setattr(ar.AIRouter, name, fake)
    return seen


async def test_requested_model_used_first(router, monkeypatch):
    seen = _stub_calls(monkeypatch, {"gpt-4o": "ok"})
    r = await router.call("gpt-4o", "sys", "hi")
    assert r["text"] == "ok"
    assert r["model_used"] == "gpt-4o"
    assert seen == ["gpt-4o"]
    assert "duration_sec" in r


async def test_429_switches_to_next_model_without_retries(router, monkeypatch):
    """Квота исчерпана — повторять ту же модель бессмысленно, идём дальше."""
    seen = _stub_calls(monkeypatch, {
        "gemini-2.0-flash-lite": Exception("429 RESOURCE_EXHAUSTED quota"),
        "gemini-2.0-flash": "fallback ok",
    })
    r = await router.call("gemini-2.0-flash-lite", "sys", "hi")
    assert r["text"] == "fallback ok"
    assert seen.count("gemini-2.0-flash-lite") == 1  # без трёх попыток


async def test_deprecated_model_skipped(router, monkeypatch):
    seen = _stub_calls(monkeypatch, {
        "gpt-4o": Exception("model not found"),
        "gemini-2.0-flash-lite": "ok",
    })
    r = await router.call("gpt-4o", "sys", "hi")
    assert r["text"] == "ok"
    assert seen.count("gpt-4o") == 1


async def test_transient_error_is_retried(router, monkeypatch, no_backoff):
    attempts = {"n": 0}

    async def flaky(self, model, system, prompt):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise Exception("connection reset")
        return {"text": "recovered", "tokens": 1, "cost": 0, "model_used": model}

    monkeypatch.setattr(ar.AIRouter, "_call_openai", flaky)
    r = await router.call("gpt-4o", "sys", "hi")
    assert r["text"] == "recovered"
    assert attempts["n"] == 3


async def test_all_providers_failed_message_lists_each_error(router, monkeypatch, no_backoff):
    _stub_calls(monkeypatch, {})  # всё падает "not stubbed"
    with pytest.raises(RuntimeError) as e:
        await router.call("gpt-4o", "sys", "hi")
    msg = str(e.value)
    assert "All AI providers failed" in msg
    assert "gpt-4o →" in msg  # видно ошибку каждого провайдера


async def test_models_without_key_are_skipped(router, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    seen = _stub_calls(monkeypatch, {"gemini-2.0-flash-lite": "ok"})
    await router.call("gpt-4o", "sys", "hi")
    assert "gpt-4o" not in seen  # нет OPENAI_API_KEY — не тратим время
    assert seen == ["gemini-2.0-flash-lite"]


def test_fallback_chain_is_cheap_first():
    costs = [ar.COST_PER_1K[m] for m in ar.FALLBACK_CHAIN]
    assert costs == sorted(costs), ar.FALLBACK_CHAIN
    assert ar.FALLBACK_CHAIN[0] == "nvidia-free"   # бесплатный — раньше платных


def test_no_disabled_gemini_15_models():
    """gemini-1.5 отключены Google — их не должно быть ни в одном списке."""
    pools = [ar.AI_ROUTING, ar.COST_PER_1K, ar.PREMIUM_MODELS, ar.ECONOMY_MODELS]
    names = set(ar.FALLBACK_CHAIN)
    for p in pools:
        names |= set(p.keys()) | set(map(str, p.values()))
    assert not [n for n in names if "gemini-1.5" in n]


def test_every_routed_model_has_key_env():
    for model, provider in ar.AI_ROUTING.items():
        assert provider in ar.PROVIDER_KEY_ENV, model


def test_every_agent_model_is_routable():
    for role, model in {**ar.PREMIUM_MODELS, **ar.ECONOMY_MODELS}.items():
        assert model in ar.AI_ROUTING, f"{role} → {model}"
        assert model in ar.COST_PER_1K, f"{role} → {model}"


def test_economy_cheaper_than_premium():
    args = (1, 30)
    assert ar.estimate_cost("economy", *args) < ar.estimate_cost("premium", *args)


def test_resolve_gemini_model_without_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(ar, "_GEMINI_RESOLVED", None)
    assert ar.resolve_gemini_model() is None


def test_resolve_gemini_prefers_lite_and_caches(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(ar, "_GEMINI_RESOLVED", None)
    calls = {"n": 0}

    class Resp:
        def json(self):
            calls["n"] += 1
            return {"models": [
                {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemini-2.0-flash-lite", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemini-2.0-flash-exp", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/embedding-001", "supportedGenerationMethods": ["embedContent"]},
            ]}

    monkeypatch.setattr(ar.httpx if hasattr(ar, "httpx") else __import__("httpx"),
                        "get", lambda *a, **k: Resp())
    assert ar.resolve_gemini_model() == "gemini-2.0-flash-lite"
    ar.resolve_gemini_model()
    assert calls["n"] == 1  # закэшировано


def test_resolve_gemini_survives_network_error(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(ar, "_GEMINI_RESOLVED", None)

    def boom(*a, **k):
        raise OSError("network down")

    monkeypatch.setattr(__import__("httpx"), "get", boom)
    assert ar.resolve_gemini_model() is None
