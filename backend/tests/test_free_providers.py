"""Бесплатные OpenAI-совместимые провайдеры: NVIDIA, Groq, Cerebras,
OpenRouter, Mistral, GitHub Models — один механизм на всех."""
import httpx
import pytest

from core import ai_router as ar
from core import dispatch

ALL = list(ar.FREE_PROVIDERS)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    ar._FREE_RESOLVED.clear()
    for env in ar.PROVIDER_KEY_ENV.values():
        monkeypatch.delenv(env, raising=False)
    yield
    ar._FREE_RESOLVED.clear()


def _catalog(monkeypatch, ids, status=200, wrap="data"):
    class Resp:
        status_code = status

        def json(self):
            items = [{"id": i} for i in ids]
            return {wrap: items} if wrap else items

    monkeypatch.setattr(httpx, "get", lambda *a, **k: Resp())


# ── реестр ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("provider", ALL)
def test_provider_registered_in_router(provider):
    spec = ar.FREE_PROVIDERS[provider]
    alias = spec["alias"]
    assert ar.AI_ROUTING[alias] == provider
    assert ar.PROVIDER_KEY_ENV[provider] == spec["key_env"]
    assert ar.COST_PER_1K[alias] == 0.0          # тратятся квоты, не деньги
    assert spec["base_url"].startswith("https://")
    assert spec["prefs"]


def test_all_free_providers_come_before_paid():
    free = [s["alias"] for s in ar.FREE_PROVIDERS.values()]
    assert ar.FALLBACK_CHAIN[:len(free)] == free
    assert ar.FALLBACK_CHAIN[len(free)] == "gemini-2.0-flash-lite"


def test_fallback_chain_still_cheap_first():
    costs = [ar.COST_PER_1K[m] for m in ar.FALLBACK_CHAIN]
    assert costs == sorted(costs)


def test_aliases_are_unique():
    aliases = [s["alias"] for s in ar.FREE_PROVIDERS.values()]
    assert len(aliases) == len(set(aliases))


def test_free_provider_of():
    assert ar.free_provider_of("groq-free") == "groq"
    assert ar.free_provider_of("gpt-4o") is None


# ── подбор модели ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("provider", ALL)
def test_resolve_without_key(provider):
    assert ar.resolve_free_model(provider) is None


def test_resolve_unknown_provider():
    assert ar.resolve_free_model("skynet") is None


def test_groq_prefers_llama_33(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_x")
    _catalog(monkeypatch, ["llama-3.1-8b-instant", "llama-3.3-70b-versatile", "whisper-large"])
    assert ar.resolve_free_model("groq") == "llama-3.3-70b-versatile"


def test_openrouter_takes_only_free_models(monkeypatch):
    """Платная модель у OpenRouter спишет деньги — берём только «:free»."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-x")
    _catalog(monkeypatch, ["openai/gpt-4o", "meta-llama/llama-3.3-70b-instruct:free"])
    assert ar.resolve_free_model("openrouter") == "meta-llama/llama-3.3-70b-instruct:free"


def test_openrouter_refuses_when_no_free_model(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-x")
    _catalog(monkeypatch, ["openai/gpt-4o", "anthropic/claude-sonnet-4"])
    assert ar.resolve_free_model("openrouter") is None   # лучше отказ, чем платный вызов


def test_other_providers_fall_back_to_any_model(monkeypatch):
    """Каталоги меняются — незнакомые имена не должны ронять подбор."""
    monkeypatch.setenv("CEREBRAS_API_KEY", "csk-x")
    _catalog(monkeypatch, ["vendor/brand-new-model-2027"])
    assert ar.resolve_free_model("cerebras") == "vendor/brand-new-model-2027"


@pytest.mark.parametrize("provider", ALL)
def test_resolve_skips_embeddings(monkeypatch, provider):
    spec = ar.FREE_PROVIDERS[provider]
    monkeypatch.setenv(spec["key_env"], "k")
    good = "meta-llama/llama-3.3-70b-instruct:free" if provider == "openrouter" else "meta/llama-3.3-70b-instruct"
    _catalog(monkeypatch, ["nv-embedqa-e5-v5", "rerank-qa-mistral-4b", good])
    assert ar.resolve_free_model(provider) == good


def test_github_uses_catalog_path(monkeypatch):
    """У GitHub Models каталог лежит не на /models."""
    monkeypatch.setenv("GITHUB_MODELS_TOKEN", "ghp_x")
    seen = {}

    class Resp:
        def json(self):
            return [{"id": "openai/gpt-4o-mini"}]      # у GitHub список без обёртки data

    def spy(url, **kw):
        seen["url"] = url
        return Resp()

    monkeypatch.setattr(httpx, "get", spy)
    assert ar.resolve_free_model("github") == "openai/gpt-4o-mini"
    assert seen["url"].endswith("/catalog/models")


def test_resolve_caches_per_provider(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_x")
    monkeypatch.setenv("CEREBRAS_API_KEY", "csk-x")
    calls = {"n": 0}

    class Resp:
        def json(self):
            calls["n"] += 1
            return {"data": [{"id": "llama-3.3-70b-versatile"}]}

    monkeypatch.setattr(httpx, "get", lambda *a, **k: Resp())
    ar.resolve_free_model("groq")
    ar.resolve_free_model("groq")
    assert calls["n"] == 1                       # закэшировано
    ar.resolve_free_model("cerebras")
    assert calls["n"] == 2                       # кэш раздельный


@pytest.mark.parametrize("provider", ALL)
def test_resolve_survives_network_error(monkeypatch, provider):
    monkeypatch.setenv(ar.FREE_PROVIDERS[provider]["key_env"], "k")

    def boom(*a, **k):
        raise OSError("dns fail")

    monkeypatch.setattr(httpx, "get", boom)
    assert ar.resolve_free_model(provider) is None


# ── вызов ─────────────────────────────────────────────────────────────────────

def _fake_openai(monkeypatch, seen):
    class FakeClient:
        def __init__(self, api_key, base_url):
            seen["base_url"] = base_url
            seen["api_key"] = api_key
            self.chat = self

        @property
        def completions(self):
            return self

        async def create(self, model, max_tokens, messages):
            seen["model"] = model

            class U:
                total_tokens = 77

            class M:
                content = "ответ"

            class C:
                message = M()

            class R:
                choices = [C()]
                usage = U()

            return R()

    monkeypatch.setattr(ar.openai, "AsyncOpenAI", FakeClient)


@pytest.mark.parametrize("provider", ALL)
async def test_call_free_uses_provider_endpoint(monkeypatch, provider):
    spec = ar.FREE_PROVIDERS[provider]
    monkeypatch.setenv(spec["key_env"], "secret-key")
    monkeypatch.setattr(ar, "resolve_free_model", lambda p: "some/model")
    seen = {}
    _fake_openai(monkeypatch, seen)

    res = await ar.AIRouter()._call_free(spec["alias"], "sys", "hi")

    assert seen["base_url"] == spec["base_url"]
    assert seen["api_key"] == "secret-key"
    assert seen["model"] == "some/model"
    assert res["text"] == "ответ"
    assert res["tokens"] == 77
    assert res["cost"] == 0.0
    assert res["model_used"] == f"{provider}:some/model"


async def test_call_free_without_catalog_names_the_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_x")
    monkeypatch.setattr(ar, "resolve_free_model", lambda p: None)
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        await ar.AIRouter()._call_free("groq-free", "sys", "hi")


async def test_router_dispatches_every_free_provider(monkeypatch):
    """Роутер должен уметь позвать любого из реестра, а не только NVIDIA."""
    for spec in ar.FREE_PROVIDERS.values():
        monkeypatch.setenv(spec["key_env"], "k")
    called = []

    async def fake(self, model, system, prompt):
        called.append(model)
        if len(called) < 3:                       # первые два «кончились»
            raise Exception("429 rate limit")
        return {"text": "ok", "tokens": 1, "cost": 0.0, "model_used": f"x:{model}"}

    monkeypatch.setattr(ar.AIRouter, "_call_free", fake)
    r = await ar.AIRouter().call("nvidia-free", "sys", "hi")
    assert called[:3] == ["nvidia-free", "groq-free", "cerebras-free"]
    assert r["cost"] == 0.0


async def test_nvidia_wrapper_still_works(monkeypatch):
    """Старое имя осталось — на него завязан код, написанный раньше."""
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-x")
    monkeypatch.setattr(ar, "resolve_free_model", lambda p: "meta/llama")
    _fake_openai(monkeypatch, {})
    res = await ar.AIRouter()._call_nvidia("nvidia-free", "sys", "hi")
    assert res["model_used"] == "nvidia:meta/llama"
    assert ar.resolve_nvidia_model() == "meta/llama"


# ── исполнители у дирижёра ────────────────────────────────────────────────────

@pytest.mark.parametrize("provider", ALL)
def test_every_free_provider_is_an_executor(provider):
    spec = dispatch.EXECUTORS[provider]
    assert spec["model"] == ar.FREE_PROVIDERS[provider]["alias"]
    assert spec["provider"] == provider


def test_free_executors_come_first_in_listing():
    assert list(dispatch.EXECUTORS)[:len(ALL)] == ALL


@pytest.mark.parametrize("provider", ALL)
def test_free_executor_beats_paid_by_price(monkeypatch, provider):
    monkeypatch.setenv(ar.FREE_PROVIDERS[provider]["key_env"], "k")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    assert dispatch.cheapest_available() == provider


def test_director_sees_free_provider_limits(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    doc = dispatch.executors_doc()
    assert "groq" in doc and "30 запросов/мин" in doc


@pytest.mark.parametrize("provider", ALL)
async def test_delegate_to_free_is_not_reported_as_fallback(monkeypatch, provider):
    monkeypatch.setenv(ar.FREE_PROVIDERS[provider]["key_env"], "k")

    async def fake(model, system, prompt):
        return {"text": "готово", "tokens": 5, "cost": 0.0,
                "model_used": f"{provider}:some/model"}

    monkeypatch.setattr(dispatch.ai_router, "call", fake)
    r = await dispatch.delegate(provider, "напиши пост")
    assert r["ok"] is True and "note" not in r
    assert r["cost"] == 0.0


async def test_delegate_still_flags_real_fallback(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "k")

    async def fake(model, system, prompt):
        return {"text": "ok", "tokens": 1, "cost": 0.0, "model_used": "nvidia:meta/llama"}

    monkeypatch.setattr(dispatch.ai_router, "call", fake)
    r = await dispatch.delegate("groq", "задача")
    assert "фолбэком" in r["note"]      # ушло не к тому, кого просили


def test_connections_body_accepts_every_free_key():
    """Ключ каждого провайдера должен сохраняться через UI."""
    from api.routes_settings import ConnectionsBody
    fields = set(ConnectionsBody.model_fields)
    for spec in ar.FREE_PROVIDERS.values():
        assert spec["key_env"].lower() in fields, spec["key_env"]
